"""The account tab's meter point and tariff history feed."""
from datetime import datetime, timezone

import pytest

from custom_components.edf_energy import _agreements_for_panel, websocket_account_summary
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DATA_ACCOUNT,
  DOMAIN,
)

ACCOUNT_ID = "A-1A2B3C4D"
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

CURRENT = {"start": "2026-09-14T00:00:00+01:00", "end": "2028-03-14T00:00:00+00:00",
           "tariff_code": "E-1R-EDF_EV_FIX_GOELEC_18M_HH-K", "product_code": "EDF_EV_FIX_GOELEC_18M_HH"}
OLDER = {"start": "2025-01-01T00:00:00+00:00", "end": "2026-09-14T00:00:00+01:00",
         "tariff_code": "E-1R-EDF_SIMPLY_FIXED_2YR-B", "product_code": "EDF_SIMPLY_FIXED_2YR"}
OLDEST = {"start": "2024-01-01T00:00:00+00:00", "end": "2025-01-01T00:00:00+00:00",
          "tariff_code": "E-1R-EDF_STANDARD-B", "product_code": "EDF_STANDARD"}

class StubResult:
  def __init__(self, account):
    self.account = account

class StubEntry:
  def __init__(self):
    self.data = {CONFIG_KIND: CONFIG_KIND_ACCOUNT, CONFIG_ACCOUNT_ID: ACCOUNT_ID}
    self.options = {}

class StubConfigEntries:
  def __init__(self, entries):
    self._entries = entries

  def async_entries(self, domain):
    return self._entries

class StubHass:
  def __init__(self, account):
    self.config_entries = StubConfigEntries([StubEntry()])
    self.data = {DOMAIN: {ACCOUNT_ID: {DATA_ACCOUNT: StubResult(account) if account is not None else None}}}

class StubConnection:
  def __init__(self):
    self.result = None
    self.error = None

  def send_result(self, msg_id, result):
    self.result = result

  def send_error(self, msg_id, code, message):
    self.error = (code, message)

def ask(account, account_id=ACCOUNT_ID):
  connection = StubConnection()
  websocket_account_summary(StubHass(account), connection, {"id": 1, "account_id": account_id})
  return connection

ACCOUNT = {
  "electricity_meter_points": [{
    "mpan": "1234567890123",
    "meters": [{"serial_number": "20L1234567", "is_smart_meter": True, "is_export": False,
                "manufacturer": "Landis", "model": "E470", "firmware": "1.2",
                "active_from": datetime(2022, 5, 1, tzinfo=timezone.utc), "active_to": None}],
    "agreements": [OLDER, CURRENT, OLDEST],
  }],
  "gas_meter_points": [{
    "mprn": "1234567",
    "meters": [{"serial_number": "G4K123", "is_smart_meter": False, "manufacturer": None,
                "model": None, "firmware": None, "active_from": None, "active_to": None}],
    "agreements": [],
  }],
}

# ── Agreement ordering and the live flag ──────────────────────────────────────

@pytest.mark.asyncio
async def test_agreements_come_back_newest_first():
  # Act
  result = _agreements_for_panel([OLDEST, CURRENT, OLDER], NOW)

  # Assert
  assert [a["product_code"] for a in result] == [
    "EDF_EV_FIX_GOELEC_18M_HH", "EDF_SIMPLY_FIXED_2YR", "EDF_STANDARD"]

@pytest.mark.asyncio
async def test_only_the_agreement_in_force_is_marked_live():
  # Act
  result = _agreements_for_panel([OLDEST, CURRENT, OLDER], NOW)

  # Assert
  assert [a["is_active"] for a in result] == [True, False, False]

@pytest.mark.asyncio
async def test_when_nothing_is_in_force_then_nothing_is_marked_live():
  """A switch away leaves only ended agreements, and none of them should read as Live."""
  # Act
  result = _agreements_for_panel([OLDEST, OLDER], datetime(2027, 1, 1, tzinfo=timezone.utc))

  # Assert
  assert all(a["is_active"] == False for a in result)

@pytest.mark.asyncio
async def test_agreements_with_no_history_are_fine():
  assert _agreements_for_panel([], NOW) == []

# ── The websocket command ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_meter_points_and_history_are_returned():
  # Act
  result = ask(ACCOUNT).result

  # Assert
  assert result["account_id"] == ACCOUNT_ID
  assert len(result["electricity"]) == 1
  assert result["electricity"][0]["mpan"] == "1234567890123"
  assert len(result["electricity"][0]["agreements"]) == 3
  assert result["gas"][0]["mprn"] == "1234567"

@pytest.mark.asyncio
async def test_meter_dates_are_serialised_for_the_browser():
  """datetimes do not survive the websocket, so they go out as ISO strings."""
  # Act
  meter = ask(ACCOUNT).result["electricity"][0]["meters"][0]

  # Assert
  assert meter["active_from"] == "2022-05-01T00:00:00+00:00"
  assert meter["active_to"] is None

@pytest.mark.asyncio
async def test_export_meter_points_are_flagged():
  # Arrange
  account = {
    "electricity_meter_points": [{
      "mpan": "1234567890124", "agreements": [],
      "meters": [{"serial_number": "20L1234567", "is_export": True, "is_smart_meter": True,
                  "manufacturer": None, "model": None, "firmware": None,
                  "active_from": None, "active_to": None}],
    }],
    "gas_meter_points": [],
  }

  # Act/Assert
  assert ask(account).result["electricity"][0]["is_export"] == True

@pytest.mark.asyncio
async def test_when_account_not_loaded_yet_then_error_rather_than_empty():
  """An empty answer would render as 'no meter points', which is a different claim."""
  # Act
  connection = ask(None)

  # Assert
  assert connection.result is None
  assert connection.error[0] == "not_loaded"

@pytest.mark.asyncio
async def test_when_account_unknown_then_not_found():
  # Act
  connection = ask(ACCOUNT, "a_someoneelse")

  # Assert
  assert connection.error[0] == "not_found"
