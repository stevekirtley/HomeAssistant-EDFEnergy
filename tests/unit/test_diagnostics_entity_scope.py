"""A diagnostics download only reports the entities of the account it was asked for.

It used to take every registry entity with "edf_energy" in its unique id. That also matched
the other EDF integration's entities (it installs as edf_energy), and the entities of any
second account set up here. The redaction only knows this account's number and meter ids,
so theirs went out in full in a file that usually ends up attached to a public issue.
"""
import json

import pytest

from custom_components.edfenergy_uk import diagnostics
from custom_components.edfenergy_uk.const import CONFIG_ACCOUNT_ID, DATA_ACCOUNT, DATA_CLIENT, DOMAIN

ACCOUNT = "A-AAAA1111"
OTHER_ACCOUNT = "A-BBBB2222"
OTHER_INTEGRATION_ACCOUNT = "A-CCCC3333"


class StubEntry:
  def __init__(self, entry_id, account_id):
    self.entry_id = entry_id
    self.data = {CONFIG_ACCOUNT_ID: account_id}


class StubConfigEntries:
  def __init__(self, entries):
    self._entries = entries

  def async_entries(self, domain, include_ignore=False):
    return list(self._entries) if domain == DOMAIN else []


class StubRegistryEntity:
  def __init__(self, platform, config_entry_id, unique_id):
    self.platform = platform
    self.config_entry_id = config_entry_id
    self.unique_id = unique_id
    self.entity_id = f"sensor.{unique_id.lower()}"


class StubRegistry:
  def __init__(self, entities):
    self.entities = {entity.entity_id: entity for entity in entities}


class StubStates:
  def async_all(self):
    return []


class StubAccountResult:
  def __init__(self, account):
    self.account = account


class StubClient:
  token_diagnostics = None

  async def async_get_electricity_consumption(self, mpan, serial_number, page_size=None):
    return []

  async def async_get_intelligent_devices(self, account_id):
    return []


class StubHass:
  def __init__(self, entries):
    self.config_entries = StubConfigEntries(entries)
    self.states = StubStates()
    self.data = {DOMAIN: {ACCOUNT: {
      DATA_ACCOUNT: StubAccountResult({
        "id": ACCOUNT,
        "electricity_meter_points": [{"mpan": "1000000000001", "meters": [{"serial_number": "SERIAL1"}]}],
        "gas_meter_points": [],
      }),
      DATA_CLIENT: StubClient(),
    }}}


ENTRIES = [StubEntry("account", ACCOUNT), StubEntry("cost-tracker", ACCOUNT), StubEntry("second-account", OTHER_ACCOUNT)]

ENTITIES = [
  StubRegistryEntity(DOMAIN, "account", "edf_energy_electricity_SERIAL1_1000000000001_current_rate"),
  StubRegistryEntity(DOMAIN, "cost-tracker", f"edf_energy_ct_{ACCOUNT}_sensor.kettle"),
  StubRegistryEntity(DOMAIN, "second-account", "edf_energy_electricity_SERIAL9_1999999999999_current_rate"),
  StubRegistryEntity(DOMAIN, "second-account", f"edf_energy_{OTHER_ACCOUNT}_account_balance"),
  StubRegistryEntity("edf_energy", "their-entry", f"edf_energy_{OTHER_INTEGRATION_ACCOUNT}_balance"),
]


@pytest.fixture
def hass(monkeypatch):
  async def no_debug_override(hass, account_id):
    return None

  monkeypatch.setattr(diagnostics.er, "async_get", lambda hass: StubRegistry(ENTITIES))
  monkeypatch.setattr(diagnostics, "async_get_account_debug_override", no_debug_override)
  return StubHass(ENTRIES)


@pytest.mark.asyncio
@pytest.mark.parametrize("download", ["entry", "device"])
async def test_only_this_accounts_entities_are_reported(hass, download):
  if download == "entry":
    result = await diagnostics.async_get_config_entry_diagnostics(hass, ENTRIES[0])
  else:
    result = await diagnostics.async_get_device_diagnostics(hass, ENTRIES[0], None)

  assert sorted(result["entities"]) == [
    "edf_energy_ct_a_sensor.kettle",
    "edf_energy_electricity_1_2_current_rate",
  ]


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", [OTHER_INTEGRATION_ACCOUNT, OTHER_ACCOUNT, "SERIAL9", "1999999999999"])
async def test_no_other_accounts_identifiers_reach_the_download(hass, identifier):
  result = await diagnostics.async_get_config_entry_diagnostics(hass, ENTRIES[0])

  assert identifier.lower() not in json.dumps(result, default=str).lower()
