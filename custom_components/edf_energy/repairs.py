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
)

_LOGGER = logging.getLogger(__name__)


class ManualTariffRatesRepairFlow(RepairsFlow):
  def __init__(self, data: dict):
    self._account_id = data.get("account_id")
    self._tariff_code = data.get("tariff_code")

  async def async_step_init(self, user_input=None):
    if user_input is not None:
      entry = next(
        (e for e in self.hass.config_entries.async_entries(DOMAIN)
         if e.data.get(CONFIG_KIND) == CONFIG_KIND_ACCOUNT
         and e.data.get(CONFIG_ACCOUNT_ID) == self._account_id),
        None
      )
      if entry is None:
        return self.async_abort(reason="account_not_found")

      existing = dict(entry.data.get(CONFIG_MAIN_MANUAL_TARIFF_RATES, {}))
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

    return self.async_show_form(
      step_id="init",
      data_schema=vol.Schema({
        vol.Required(CONFIG_MANUAL_TARIFF_PEAK_RATE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/kWh")
        ),
        vol.Required(CONFIG_MANUAL_TARIFF_OFF_PEAK_RATE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/kWh")
        ),
        vol.Required(CONFIG_MANUAL_TARIFF_STANDING_CHARGE): selector.NumberSelector(
          selector.NumberSelectorConfig(min=0, step=0.01, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p/day")
        ),
      }),
      description_placeholders={"tariff_code": self._tariff_code},
    )


async def async_create_fix_flow(hass, issue_id: str, data: dict | None):
  return ManualTariffRatesRepairFlow(data or {})
