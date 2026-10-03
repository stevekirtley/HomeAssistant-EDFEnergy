"""Device lookup across the Home Assistant 2026.9 registry change (issue #36).

async_get_device was deprecated in favour of async_get_device_by_identifier, which does
not exist on the oldest Home Assistant this integration supports, so the helper has to
work either way.
"""
from custom_components.edf_energy import _async_device_by_identifier

IDENTIFIER = ("edf_energy", "electricity_123_456")
ENTRY_ID = "01ABCDEF"


class NewRegistry:
  """Home Assistant 2026.9 and later."""

  def __init__(self):
    self.calls = []

  def async_get_device_by_identifier(self, identifier, config_entry_id):
    self.calls.append((identifier, config_entry_id))
    return "new-device"

  def async_get_device(self, identifiers=None, connections=None):
    raise AssertionError("the deprecated lookup must not be used when the new one exists")


class OldRegistry:
  """Home Assistant before 2026.9 - the deprecated call is all there is."""

  def __init__(self):
    self.calls = []

  def async_get_device(self, identifiers=None, connections=None):
    self.calls.append(identifiers)
    return "old-device"


def test_prefers_the_new_lookup_and_scopes_it_to_the_config_entry():
  registry = NewRegistry()

  assert _async_device_by_identifier(registry, IDENTIFIER, ENTRY_ID) == "new-device"
  assert registry.calls == [(IDENTIFIER, ENTRY_ID)]


def test_falls_back_on_older_home_assistant():
  registry = OldRegistry()

  assert _async_device_by_identifier(registry, IDENTIFIER, ENTRY_ID) == "old-device"
  assert registry.calls == [{IDENTIFIER}]


def test_a_missing_device_is_passed_through():
  class Empty(NewRegistry):
    def async_get_device_by_identifier(self, identifier, config_entry_id):
      return None

  assert _async_device_by_identifier(Empty(), IDENTIFIER, ENTRY_ID) is None
