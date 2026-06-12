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
    free_electricity_sessions_coordinator = hass.data[DOMAIN][account_id].get(DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id))
    if free_electricity_sessions_coordinator is not None:
      entities.append(EDFEnergyFreeElectricitySessionsCalendar(hass, free_electricity_sessions_coordinator, account_id))

    async_add_entities(entities)

  return True
