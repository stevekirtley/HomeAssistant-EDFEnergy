import logging
import os
from datetime import datetime, timedelta

logging.getLogger().setLevel(logging.DEBUG)

class TestContext:
  refresh_token: str
  account_id: str
  gas_mprn: str
  gas_serial_number: str
  electricity_mpan: str
  electricity_serial_number: str

  def __init__(self, refresh_token, account_id, gas_mprn, gas_serial_number, electricity_mpan, electricity_serial_number):
    self.refresh_token = refresh_token
    self.account_id = account_id
    self.gas_mprn = gas_mprn
    self.gas_serial_number = gas_serial_number
    self.electricity_mpan = electricity_mpan
    self.electricity_serial_number = electricity_serial_number

def get_test_context():
  refresh_token = os.environ["REFRESH_TOKEN"]
  if (refresh_token is None):
      raise Exception("REFRESH_TOKEN must be set")

  account_id = os.environ["ACCOUNT_ID"]
  if (account_id is None):
      raise Exception("ACCOUNT_ID must be set")

  gas_mprn = os.environ.get("GAS_MPRN", None)
  gas_serial_number = os.environ.get("GAS_SN", None)

  electricity_mpan= os.environ["ELECTRICITY_MPAN"]
  if (electricity_mpan is None):
      raise Exception("ELECTRICITY_MPAN must be set")

  electricity_serial_number = os.environ["ELECTRICITY_SN"]
  if (electricity_serial_number is None):
      raise Exception("ELECTRICITY_SN must be set")

  return TestContext(refresh_token, account_id, gas_mprn, gas_serial_number, electricity_mpan, electricity_serial_number)

def create_consumption_data(period_from: datetime, period_to: datetime, reverse = False):
  consumption = []
  current_valid_from = period_from
  current_valid_to = None
  while current_valid_to is None or current_valid_to < period_to:
    current_valid_to = current_valid_from + timedelta(minutes=30)

    consumption.append({
      "start": current_valid_from,
      "end": current_valid_to,
      "consumption": 1
    })

    current_valid_from = current_valid_to

  if reverse == True:
    def get_interval_start(item):
      return (item["start"].timestamp(), item["start"].fold)

    consumption.sort(key=get_interval_start, reverse=True)

  return consumption

def create_rate_data(period_from, period_to, expected_rates: list):
  rates = []
  current_valid_from = period_from
  current_valid_to = None

  rate_index = 0
  while current_valid_to is None or current_valid_to < period_to:
    current_valid_to = current_valid_from + timedelta(minutes=30)

    rates.append({
      "start": current_valid_from,
      "end": current_valid_to,
      "tariff_code": "1-ER-TARIFF-L",
      "value_inc_vat": expected_rates[rate_index],
      "is_capped": False
    })

    current_valid_from = current_valid_to
    rate_index = rate_index + 1

    if (rate_index > (len(expected_rates) - 1)):
      rate_index = 0

  return rates


# ── Live product discovery ───────────────────────────────────────────────────
# These tests talk to EDF's real pricing API, and EDF retire tariffs from sale every few
# months. Hard-coded product codes therefore rot: EDF_SIMPLY_FIXED_SEP2027 was withdrawn
# on 10 September 2026 and every run since answered 404, which is what broke CI daily
# without a line of our code changing. The products in use are now read from EDF's own
# catalogue at run time, so the suite follows them.

PRODUCTS_URL = "https://api.edfgb-kraken.energy/v1/products/"

# A region has to be picked to get a tariff code; _A (East England) is as good as any and
# keeps failures comparable between runs.
TEST_REGION = "_A"

# EDF publish a product that is explicitly not for use. Never pick it.
_EXCLUDED = ("TEST_DO_NOT_USE",)

# Preferred first, so the suite exercises EDF's mainstream tariffs rather than whichever
# name happens to sort first - that picked a half-hourly dynamic FreePhase product, which
# is not a sensible baseline for a standing charge. These are only preferences: if EDF
# withdraw them the search falls through to anything else that fits, which is the whole
# point of discovering products instead of naming them.
_PREFERRED = ("EDF_STANDARD_VARIABLE", "EDF_SIMPLY_FIXED", "EDF_SIMPLY_TRACKER")

# Prepayment variants price differently and are not what the suite is about.
_DEPRIORITISED = ("_PAYG",)

_catalogue_cache = None
_product_cache = {}


def _get_json(url):
  import json as _json
  import urllib.request
  with urllib.request.urlopen(url, timeout=30) as response:
    return _json.load(response)


def available_products():
  """Every product EDF currently publish, newest listing cached for the session."""
  global _catalogue_cache
  if _catalogue_cache is None:
    _catalogue_cache = _get_json(f"{PRODUCTS_URL}?page_size=100").get("results") or []
  return _catalogue_cache


def product_detail(product_code: str):
  """One product, including the tariff codes per region."""
  if product_code not in _product_cache:
    # The trailing slash matters: without it the API answers 301 and urllib drops the body.
    _product_cache[product_code] = _get_json(f"{PRODUCTS_URL}{product_code}/")
  return _product_cache[product_code]


class TestProduct:
  """A product currently on sale, with the tariff codes the tests need."""

  def __init__(self, code, electricity_tariff_code, gas_tariff_code):
    self.code = code
    self.electricity_tariff_code = electricity_tariff_code
    self.gas_tariff_code = gas_tariff_code

  def __repr__(self):
    return f"TestProduct({self.code})"


def _tariff_code(detail, key):
  region = (detail.get(key) or {}).get(TEST_REGION) or {}
  for payment_method in region.values():
    code = (payment_method or {}).get("code")
    if code:
      return code
  return None


def find_product(is_variable: bool, needs_gas: bool = False):
  """A product on sale now matching what a test needs.

  Sorted by code before choosing, so a run picks the same product as the last one for as
  long as EDF keep selling it, rather than moving about between runs.
  """
  def rank(product):
    code = product.get("code") or ""
    preferred = next((i for i, name in enumerate(_PREFERRED) if code.startswith(name)), len(_PREFERRED))
    return (any(d in code for d in _DEPRIORITISED), preferred, code)

  for product in sorted(available_products(), key=rank):
    code = product.get("code") or ""
    if not code or any(marker in code for marker in _EXCLUDED):
      continue
    if bool(product.get("is_variable")) != is_variable:
      continue
    if product.get("direction") not in (None, "IMPORT"):
      continue

    detail = product_detail(code)
    electricity = _tariff_code(detail, "single_register_electricity_tariffs")
    gas = _tariff_code(detail, "single_register_gas_tariffs")
    if electricity is None or (needs_gas and gas is None):
      continue
    return TestProduct(code, electricity, gas)

  raise AssertionError(
    f"EDF are not currently selling a product with is_variable={is_variable} "
    f"and gas={needs_gas}; the catalogue held "
    f"{[p.get('code') for p in available_products()]}"
  )


def pricing_period():
  """A day that any product on sale is priced for.

  Fixed dates rot as surely as fixed product codes - the old window sat in August 2026,
  which predates the products EDF now sell - so this asks about tomorrow instead.
  """
  from datetime import timezone
  start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
  return start, start + timedelta(days=1)
