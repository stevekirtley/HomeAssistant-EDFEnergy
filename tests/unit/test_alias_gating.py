"""The old-name action aliases stay off the old domain when it belongs to somebody else.

They exist so automations written against `edf_energy.*` keep working after the move. But
another EDF integration uses that domain too, and registering actions in its namespace -
and overwriting their descriptions - is not ours to do. So they are only registered while
nothing else has a claim on it.
"""
import pytest

from custom_components.edfenergy_uk import _async_register_services
from custom_components.edfenergy_uk.const import DATA_PREDECESSOR_FOLDER, DOMAIN, PREDECESSOR_DOMAIN
from custom_components.edfenergy_uk.predecessor import FOLDER_NOT_OURS, FOLDER_OURS
from custom_components.edfenergy_uk.utils import entity_services


class StubServices:
  def __init__(self):
    self.registered = []

  def has_service(self, domain, name):
    return (domain, name) in self.registered

  def async_register(self, domain, name, handler, **kwargs):
    self.registered.append((domain, name))


class StubConfigEntries:
  def __init__(self, old_entries):
    self._old = old_entries

  def async_entries(self, domain=None):
    return list(self._old) if domain == PREDECESSOR_DOMAIN else []


class StubEntry:
  def __init__(self, version):
    self.data = {"account_id": "A-XXXXXX"}
    self.version = version
    self.source = "user"
    self.disabled_by = None


class StubHass:
  def __init__(self, folder, old_entries=()):
    self.data = {DOMAIN: {DATA_PREDECESSOR_FOLDER: folder}}
    self.services = StubServices()
    self.config_entries = StubConfigEntries(old_entries)


class StubPlatform:
  def __init__(self, hass):
    self.hass = hass
    self.domain_platform_entities = {}
    self.registered = []

  def async_register_entity_service(self, name, schema, func, **kwargs):
    self.registered.append(name)


@pytest.fixture
def aliased(monkeypatch):
  calls = []
  monkeypatch.setattr(entity_services.service, "async_register_entity_service",
                      lambda hass, domain, name, **kwargs: calls.append((domain, name)))
  monkeypatch.setattr(entity_services, "describe_alias", lambda hass, name: None)
  return calls


@pytest.mark.parametrize("folder", [FOLDER_OURS, None])
def test_an_entity_action_is_aliased_when_the_old_domain_is_ours_or_gone(aliased, folder):
  platform = StubPlatform(StubHass(folder))

  entity_services.register_entity_service(platform, "refresh_intelligent_dispatches", {}, None)

  assert platform.registered == ["refresh_intelligent_dispatches"]
  assert aliased == [(PREDECESSOR_DOMAIN, "refresh_intelligent_dispatches")]


@pytest.mark.parametrize("hass", [
  StubHass(FOLDER_NOT_OURS),
  StubHass(None, [StubEntry(version=1)]),
], ids=["their folder", "their entry"])
def test_an_entity_action_is_not_aliased_onto_the_other_integration(aliased, hass):
  platform = StubPlatform(hass)

  entity_services.register_entity_service(platform, "refresh_intelligent_dispatches", {}, None)

  assert platform.registered == ["refresh_intelligent_dispatches"], "the real action must still register"
  assert aliased == []


def _register_all(hass, monkeypatch):
  monkeypatch.setattr("custom_components.edfenergy_uk.describe_alias", lambda hass, name: None)
  _async_register_services(hass)
  return hass.services.registered


def test_account_actions_are_aliased_when_the_old_domain_is_ours(monkeypatch):
  registered = _register_all(StubHass(FOLDER_OURS), monkeypatch)

  ours = {name for domain, name in registered if domain == DOMAIN}
  old = {name for domain, name in registered if domain == PREDECESSOR_DOMAIN}
  assert ours and old == ours


def test_account_actions_are_not_aliased_onto_the_other_integration(monkeypatch):
  registered = _register_all(StubHass(FOLDER_NOT_OURS), monkeypatch)

  assert [r for r in registered if r[0] == DOMAIN], "the real actions must still register"
  assert [r for r in registered if r[0] == PREDECESSOR_DOMAIN] == []
