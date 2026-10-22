import os

from ..const import SUCCESSOR_DOMAIN


def successor_installed(hass) -> bool:
  """Whether the integration this one becomes in 21.0.0 is also installed.

  HACS works out where to put an integration from the domain in its manifest, so the new
  release lands in a new directory and the old one is simply left behind. Both are then on
  disk until somebody deletes this one.

  It lives here rather than in __init__ because the config flow needs to ask the same
  question, and importing the component module from the flow is a circular import.
  """
  return os.path.isdir(os.path.join(hass.config.config_dir, "custom_components", SUCCESSOR_DOMAIN))
