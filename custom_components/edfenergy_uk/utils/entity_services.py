"""Registering an entity action under this domain and the one we used to live in.

An entity action is normally registered through `platform.async_register_entity_service`,
which takes the domain from the platform and so follows the integration wherever it moves.
That is a problem across a rename: the blueprints shipped with this integration call
`edf_energy.refresh_intelligent_dispatches` and `edf_energy.update_cost_tracker`, and a
blueprint becomes a real automation in somebody's system. Worse, the dispatch refresh is
not optional - with manual refreshing turned on, nothing updates the dispatches unless that
action is called, so losing it quietly breaks the off-peak sensor.

The platform method hardcodes its own domain, but the helper underneath it takes whichever
domain it is given, so the same action can be registered twice over the same entities. That
is all this does: the second registration shares the first one's entity lookup, schema and
handler, so there is no separate code path to drift or to re-implement targeting in.

The aliases are deprecated and meant to come out a couple of releases after 21.0.0.
"""
from homeassistant.helpers import service

from ..const import PREDECESSOR_DOMAIN


def register_entity_service(platform, name, schema, func, **kwargs) -> None:
  """Register an entity action, and the same action under the old domain."""
  platform.async_register_entity_service(name, schema, func, **kwargs)

  if platform.hass.services.has_service(PREDECESSOR_DOMAIN, name):
    return

  service.async_register_entity_service(
    platform.hass,
    PREDECESSOR_DOMAIN,
    name,
    entities=platform.domain_platform_entities,
    func=func,
    job_type=None,
    schema=schema,
    **kwargs,
  )
