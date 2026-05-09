import logging

from homeassistant.util.dt import (utcnow)

from .const import (
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
  """Setup calendar entities based on our entry"""

  if entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    async_add_entities([])

  return True
