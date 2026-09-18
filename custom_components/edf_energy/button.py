import logging

from .flextras import async_remove_ineligible_entity
from .flextras.button import (
  EDFEnergyFlextrasRegisterPowerPerks,
  EDFEnergyFlextrasClaimBonusHours,
  EDFEnergyFlextrasJoin,
)

from .const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DATA_CLIENT,
  DATA_FLEXTRAS_COORDINATOR,
  DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
  """Setup buttons based on our entry"""
  config = dict(entry.data)

  if CONFIG_KIND in config and config[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    account_id = config[CONFIG_ACCOUNT_ID]
    coordinator = hass.data[DOMAIN][account_id].get(DATA_FLEXTRAS_COORDINATOR.format(account_id))
    client = hass.data[DOMAIN][account_id].get(DATA_CLIENT)

    if coordinator is not None and client is not None:
      entities = [
        EDFEnergyFlextrasJoin(hass, coordinator, client, account_id),
        EDFEnergyFlextrasClaimBonusHours(hass, coordinator, client, account_id),
      ]

      # No Power Perks button for tariffs that cannot join (e.g. FreePhase, where
      # free electricity events are already part of the tariff).
      result = coordinator.data
      if result is None or not result.power_perks_excluded:
        entities.insert(0, EDFEnergyFlextrasRegisterPowerPerks(hass, coordinator, client, account_id))
      else:
        async_remove_ineligible_entity(
          hass, "button", f"edf_energy_{account_id}_flextras_register_power_perks"
        )

      async_add_entities(entities, True)

  return True
