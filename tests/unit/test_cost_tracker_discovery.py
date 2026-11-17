"""Only sensors measuring electricity used are offered as cost trackers."""
from types import SimpleNamespace

import pytest

from custom_components.edfenergy_uk.discovery import is_cost_tracker_candidate

def entity(entity_id="sensor.kettle_energy", unit="kWh", device_class=None, original_device_class="energy"):
  return SimpleNamespace(
    entity_id=entity_id,
    domain=entity_id.split(".")[0],
    unit_of_measurement=unit,
    device_class=device_class,
    original_device_class=original_device_class,
  )

@pytest.mark.parametrize("entry,expected", [
  (entity(), True),
  (entity(unit="Wh"), True),
  (entity(unit="MWh"), True),
  # Classless kWh sensors (templates, older integrations) are still offered
  (entity(original_device_class=None), True),
  # Fitness trackers
  (entity(entity_id="sensor.active_calories", unit="kcal"), False),
  (entity(unit="MJ"), False),
  # A battery's stored energy
  (entity(entity_id="sensor.battery_stored_energy", original_device_class="energy_storage"), False),
  # The user's own class wins over the integration's, either way
  (entity(device_class="energy_storage"), False),
  (entity(device_class="energy", original_device_class="energy_storage"), True),
  (entity(entity_id="number.charge_limit_energy"), False),
  (entity(unit=None), False),
])
def test_is_cost_tracker_candidate(entry, expected):
  assert is_cost_tracker_candidate(entry) == expected
