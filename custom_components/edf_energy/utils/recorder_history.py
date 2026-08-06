import logging

_LOGGER = logging.getLogger(__name__)


async def async_count_recorded_states(hass, entity_id: str) -> int | None:
  """Count the recorder rows held for an entity.

  Used to decide whether it's worth telling someone about the free electricity event history
  left behind by the pre-18.9.8 write rate. Reaches into the recorder's schema, so anything
  going wrong (recorder disabled, schema moved under us) returns None and the caller stays quiet
  rather than raising a repair it can't substantiate.
  """
  try:
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.db_schema import States, StatesMeta
    from homeassistant.components.recorder.util import session_scope
  except ImportError:
    return None

  def _count() -> int:
    with session_scope(hass=hass, read_only=True) as session:
      return (
        session.query(States)
        .join(StatesMeta, States.metadata_id == StatesMeta.metadata_id)
        .filter(StatesMeta.entity_id == entity_id)
        .count()
      )

  try:
    return await get_instance(hass).async_add_executor_job(_count)
  except Exception as e:
    _LOGGER.debug(f"Could not count recorded states for {entity_id}: {e}")
    return None
