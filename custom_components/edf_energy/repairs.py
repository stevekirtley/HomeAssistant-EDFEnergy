import importlib
import logging
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
  REPAIR_API_KEY_NEEDED,
  REPAIR_FINISH_THE_MOVE,
  SERVICE_PURGE_FREE_ELECTRICITY_EVENT_HISTORY,
  SUCCESSOR_DOMAIN,
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


class FinishTheMoveRepairFlow(RepairsFlow):
  """Hands this account over to the folder the integration moved to.

  The work itself belongs to the new folder and lives there - this only presses the button,
  because the new one cannot raise a repair of its own. Home Assistant only sets a domain up
  when something already refers to it, and until the hand-over happens nothing does, so the
  new folder is inert and the prompt has to come from here.

  Doing it from the new folder's own module rather than repeating it here is deliberate: it
  is the version that gets tested with the entries it is creating, and this folder is meant
  to be deleted straight afterwards.
  """

  async def async_step_init(self, user_input=None):
    return await self.async_step_confirm()

  async def async_step_confirm(self, user_input=None):
    if user_input is None:
      return self.async_show_form(
        step_id="confirm",
        data_schema=vol.Schema({}),
        description_placeholders={
          "old_domain": DOMAIN,
          "new_domain": SUCCESSOR_DOMAIN,
        },
      )

    try:
      # Imported here rather than at the top: this folder ships before the new one exists,
      # and an import in the event loop blocks it.
      migration = await self.hass.async_add_import_executor_job(
        importlib.import_module, f"custom_components.{SUCCESSOR_DOMAIN}.migration"
      )
    except Exception as err:
      _LOGGER.warning("Could not load %s to hand over to: %s", SUCCESSOR_DOMAIN, err)
      return self.async_abort(reason="new_folder_not_ready")

    try:
      taken = await migration.async_take_over_old_entries(self.hass)
    except Exception as err:
      # The hand-over removes the old entries before creating the new ones, so a failure
      # part way through is worth being loud about - the account may be on neither side.
      _LOGGER.error("Handing over to %s failed: %s", SUCCESSOR_DOMAIN, err)
      return self.async_abort(reason="take_over_failed")

    if not taken:
      # Nothing left to move: somebody did it from Add integration while this sat open.
      ir.async_delete_issue(self.hass, DOMAIN, REPAIR_FINISH_THE_MOVE)
      return self.async_abort(reason="nothing_to_take_over")

    _LOGGER.info("Handed %d config entry(s) over to %s", taken, SUCCESSOR_DOMAIN)
    ir.async_delete_issue(self.hass, DOMAIN, REPAIR_FINISH_THE_MOVE)
    return self.async_create_entry(title="", data={})


async def async_create_fix_flow(hass, issue_id: str, data: dict | None):
  if issue_id == REPAIR_FINISH_THE_MOVE:
    return FinishTheMoveRepairFlow()

  if issue_id.startswith("api_key_needed"):
    return ApiKeyNeededRepairFlow(data or {})

  if issue_id.startswith("free_electricity_event_history"):
    return FreeElectricityEventHistoryRepairFlow(data or {})

  return ManualTariffRatesRepairFlow(data or {})
