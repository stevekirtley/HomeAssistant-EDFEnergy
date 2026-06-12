import logging

from .free_electricity.free_electricity_sessions_calendar import EDFEnergyFreeElectricitySessionsCalendar

from .const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR,
  DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
  """Setup calendar entities based on our entry"""

  if entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    account_id = entry.data[CONFIG_ACCOUNT_ID]
    entities = []

    coordinator = hass.data[DOMAIN][account_id].get(DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id))
    if coordinator is not None:
      entities.append(EDFEnergyFreeElectricitySessionsCalendar(hass, coordinator, account_id))

    async_add_entities(entities)

  return True
