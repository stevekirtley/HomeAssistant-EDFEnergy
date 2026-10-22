import json
import logging
import os
import shutil

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.helpers import issue_registry as ir, selector
import homeassistant.helpers.config_validation as cv

from .api_client import EDFEnergyApiClient
from .const import (
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_MANUAL_TARIFF_RATES,
  CONFIG_MAIN_REFRESH_EXPIRES_IN,
  CONFIG_MAIN_REFRESH_TOKEN,
  CONFIG_MANUAL_TARIFF_PEAK_RATE,
  CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE,
  CONFIG_MANUAL_TARIFF_STANDING_CHARGE,
  DOMAIN,
  PREDECESSOR_DOMAIN,
  REPAIR_API_KEY_NEEDED,
  REPAIR_OLD_FOLDER_PRESENT,
  SERVICE_PURGE_FREE_ELECTRICITY_EVENT_HISTORY,
)
from .utils.repairs import safe_repair_key

_LOGGER = logging.getLogger(__name__)


class ManualTariffRatesRepairFlow(RepairsFlow):
  def __init__(self, data: dict):
    self._account_id = data.get("account_id")
    self._tariff_code = data.get("tariff_code")
    self._is_export = data.get("is_export") == "True"

  async def async_step_init(self, user_input=None):
    if user_input is not None and CONFIG_MANUAL_TARIFF_PEAK_RATE in user_input:
      entry = next(
        (e for e in self.hass.config_entries.async_entries(DOMAIN)
         if e.data.get(CONFIG_KIND) == CONFIG_KIND_ACCOUNT
         and e.data.get(CONFIG_ACCOUNT_ID) == self._account_id),
        None
      )
      if entry is None:
        return self.async_abort(reason="account_not_found")

      existing = dict(entry.data.get(CONFIG_MAIN_MANUAL_TARIFF_RATES, {}))
      if self._is_export:
        existing[self._tariff_code] = {
          CONFIG_MANUAL_TARIFF_PEAK_RATE: user_input[CONFIG_MANUAL_TARIFF_PEAK_RATE],
          CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE: 0,
          CONFIG_MANUAL_TARIFF_STANDING_CHARGE: 0,
        }
      else:
        existing[self._tariff_code] = {
          CONFIG_MANUAL_TARIFF_PEAK_RATE: user_input[CONFIG_MANUAL_TARIFF_PEAK_RATE],
          CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE: user_input[CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE],
          CONFIG_MANUAL_TARIFF_STANDING_CHARGE: user_input[CONFIG_MANUAL_TARIFF_STANDING_CHARGE],
        }

      self.hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONFIG_MAIN_MANUAL_TARIFF_RATES: existing}
      )
      await self.hass.config_entries.async_reload(entry.entry_id)
      return self.async_create_entry(title="", data={})

    if self._is_export:
      schema = vol.Schema({
        vol.Required(CONFIG_MANUAL_TARIFF_PEAK_RATE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/kWh")
        ),
      })
    else:
      schema = vol.Schema({
        vol.Required(CONFIG_MANUAL_TARIFF_PEAK_RATE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/kWh")
        ),
        vol.Required(CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/kWh")
        ),
        vol.Required(CONFIG_MANUAL_TARIFF_STANDING_CHARGE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/day")
        ),
      })

    return self.async_show_form(
      step_id="init",
      data_schema=schema,
      description_placeholders={"tariff_code": self._tariff_code},
    )


class FreeElectricityEventHistoryRepairFlow(RepairsFlow):
  """Offers to clear the recorder history left behind by the pre-18.9.8 write rate."""

  def __init__(self, data: dict):
    self._account_id = data.get("account_id")
    self._entity_id = data.get("entity_id")

  async def async_step_init(self, user_input=None):
    return await self.async_step_confirm()

  async def async_step_confirm(self, user_input=None):
    if user_input is not None:
      await self.hass.services.async_call(
        DOMAIN,
        SERVICE_PURGE_FREE_ELECTRICITY_EVENT_HISTORY,
        {
          "account_id": self._account_id,
          "repack": user_input.get("repack", False),
        },
        blocking=True,
      )
      return self.async_create_entry(title="", data={})

    return self.async_show_form(
      step_id="confirm",
      data_schema=vol.Schema({
        vol.Required("repack", default=False): cv.boolean,
      }),
      description_placeholders={
        "account_id": self._account_id or "",
        "entity_id": self._entity_id or "",
      },
    )


class ApiKeyNeededRepairFlow(RepairsFlow):
  """Swaps an older refresh-token session for a durable API key, once the user has agreed.

  Minting is the only way to get a usable key out of EDF and it invalidates any key already
  issued on the account, so it is never done on somebody's behalf. The new key is verified
  before the refresh token is let go, so a key that turns out not to work cannot strand the
  entry with no credential at all.
  """

  def __init__(self, data: dict):
    self._account_id = data.get("account_id")

  async def async_step_init(self, user_input=None):
    return await self.async_step_confirm()

  async def async_step_confirm(self, user_input=None):
    if user_input is None:
      return self.async_show_form(
        step_id="confirm",
        data_schema=vol.Schema({}),
        description_placeholders={"account_id": self._account_id or ""},
      )

    entry = next(
      (e for e in self.hass.config_entries.async_entries(DOMAIN)
       if e.data.get(CONFIG_KIND) == CONFIG_KIND_ACCOUNT
       and e.data.get(CONFIG_ACCOUNT_ID) == self._account_id),
      None
    )
    if entry is None:
      return self.async_abort(reason="account_not_found")

    repair_key = safe_repair_key(REPAIR_API_KEY_NEEDED, self._account_id)
    refresh_token = entry.data.get(CONFIG_MAIN_REFRESH_TOKEN)
    if not refresh_token:
      # Already has a key, or was re-authenticated while the prompt sat there.
      ir.async_delete_issue(self.hass, DOMAIN, repair_key)
      return self.async_create_entry(title="", data={})

    client = EDFEnergyApiClient(refresh_token)
    try:
      api_key = await client.async_ensure_api_key()
    except Exception as e:
      _LOGGER.warning("Could not create an API key for account %s: %s", self._account_id, e)
      return self.async_abort(reason="api_key_failed")
    finally:
      await client.async_close()

    verify_client = EDFEnergyApiClient(api_key=api_key)
    try:
      await verify_client.async_refresh_token()
    except Exception as e:
      _LOGGER.warning("New API key for account %s failed verification; keeping the existing session: %s", self._account_id, e)
      return self.async_abort(reason="api_key_failed")
    finally:
      await verify_client.async_close()

    data = {**entry.data, CONFIG_MAIN_API_KEY: api_key}
    data.pop(CONFIG_MAIN_REFRESH_TOKEN, None)
    data.pop(CONFIG_MAIN_REFRESH_EXPIRES_IN, None)
    self.hass.config_entries.async_update_entry(entry, data=data)
    ir.async_delete_issue(self.hass, DOMAIN, repair_key)
    await self.hass.config_entries.async_reload(entry.entry_id)
    return self.async_create_entry(title="", data={})


class OldFolderRepairFlow(RepairsFlow):
  """Deletes the folder this integration used to live in.

  The hand-over has already happened by the time this can be raised, so the old folder holds
  no config entries and is running nothing. Removing it is housekeeping, but it is still a
  delete, so it is confirmed first and checked before it happens: the manifest inside has to
  say it is the folder this integration replaced. Deleting the wrong directory under
  custom_components would take somebody else's integration with it.

  Home Assistant keeps the module it already imported, so the folder goes but the listing
  does not until a restart. Restarting is left to the user - taking the house down without
  being asked is a bigger thing than tidying a directory.
  """

  def _folder(self) -> str:
    return os.path.join(
      self.hass.config.config_dir, "custom_components", PREDECESSOR_DOMAIN
    )

  def _delete(self) -> str | None:
    """Delete it, in the executor. Returns a reason if it would not be safe to."""
    folder = self._folder()
    if not os.path.isdir(folder):
      return "already_gone"

    manifest = os.path.join(folder, "manifest.json")
    try:
      with open(manifest, encoding="utf-8") as handle:
        domain = json.load(handle).get("domain")
    except Exception as err:
      _LOGGER.warning("Could not read %s before deleting it: %s", manifest, err)
      return "not_the_old_folder"

    if domain != PREDECESSOR_DOMAIN:
      # Something else is living in that directory. Leave it alone.
      _LOGGER.warning(
        "%s holds the integration %s, not %s - not deleting it", folder, domain,
        PREDECESSOR_DOMAIN,
      )
      return "not_the_old_folder"

    shutil.rmtree(folder)
    return None

  async def async_step_init(self, user_input=None):
    return await self.async_step_confirm()

  async def async_step_confirm(self, user_input=None):
    if user_input is None:
      return self.async_show_form(
        step_id="confirm",
        data_schema=vol.Schema({}),
        description_placeholders={"old_domain": PREDECESSOR_DOMAIN},
      )

    try:
      refused = await self.hass.async_add_executor_job(self._delete)
    except Exception as err:
      _LOGGER.error("Could not delete custom_components/%s: %s", PREDECESSOR_DOMAIN, err)
      return self.async_abort(reason="delete_failed")

    if refused == "already_gone":
      ir.async_delete_issue(self.hass, DOMAIN, REPAIR_OLD_FOLDER_PRESENT)
      return self.async_abort(reason="already_gone")
    if refused is not None:
      return self.async_abort(reason=refused)

    _LOGGER.info("Deleted custom_components/%s", PREDECESSOR_DOMAIN)
    ir.async_delete_issue(self.hass, DOMAIN, REPAIR_OLD_FOLDER_PRESENT)
    return self.async_create_entry(title="", data={})


async def async_create_fix_flow(hass, issue_id: str, data: dict | None):
  if issue_id == REPAIR_OLD_FOLDER_PRESENT:
    return OldFolderRepairFlow()

  if issue_id.startswith("api_key_needed"):
    return ApiKeyNeededRepairFlow(data or {})

  if issue_id.startswith("free_electricity_event_history"):
    return FreeElectricityEventHistoryRepairFlow(data or {})

  return ManualTariffRatesRepairFlow(data or {})
