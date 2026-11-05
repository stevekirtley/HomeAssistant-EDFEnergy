import logging
from homeassistant.helpers import storage

from ..const import DOMAIN, PREDECESSOR_DOMAIN
from ..predecessor import accounts_shared_with_other_integration

_LOGGER = logging.getLogger(__name__)

# The account cache used to be kept under the old domain's prefix, like every other store.
# Unlike the others it has a name another EDF integration on that domain uses too, for the
# same account and in a shape of its own, so it now lives under this domain. The old one is
# still read once, so an update starts with what it had, but only when nothing else could
# have written it.
def _store(hass, account_id: str):
  return storage.Store(hass, "1", f"{DOMAIN}.{account_id}_account")

def _old_store(hass, account_id: str):
  return storage.Store(hass, "1", f"{PREDECESSOR_DOMAIN}.{account_id}_account")

async def async_load_cached_account(hass, account_id: str):
  try:
    data = await _store(hass, account_id).async_load()
    if data is None and account_id not in accounts_shared_with_other_integration(hass):
      data = await _old_store(hass, account_id).async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded cached account data for {account_id}")
    return data
  except:
    return None
  
async def async_save_cached_account(hass, account_id: str, account_data):
  if account_data is not None:
    await _store(hass, account_id).async_save(account_data)
    _LOGGER.debug(f"Saved account data for ({account_id})")
