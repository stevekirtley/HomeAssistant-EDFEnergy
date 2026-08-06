import logging
import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_MANUAL_TARIFF_RATES,
  CONFIG_MANUAL_TARIFF_PEAK_RATE,
  CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE,
  CONFIG_MANUAL_TARIFF_STANDING_CHARGE,
  DOMAIN,
  SERVICE_PURGE_FREE_ELECTRICITY_EVENT_HISTORY,
)

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


async def async_create_fix_flow(hass, issue_id: str, data: dict | None):
  if issue_id.startswith("free_electricity_event_history"):
    return FreeElectricityEventHistoryRepairFlow(data or {})

  return ManualTariffRatesRepairFlow(data or {})
