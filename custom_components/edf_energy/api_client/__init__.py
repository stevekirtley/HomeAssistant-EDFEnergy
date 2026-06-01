import logging
import json
from typing import Any, List
import aiohttp
from asyncio import TimeoutError
from datetime import (datetime, timedelta, time, timezone)
from threading import RLock
from zoneinfo import ZoneInfo

from homeassistant.util.dt import (as_utc, now, as_local, parse_datetime, parse_date)

from ..const import INTEGRATION_VERSION, INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLE_CHARGERS

from ..utils import (
  is_day_night_tariff,
)

from .intelligent_device import IntelligentDevice
from .intelligent_dispatches import IntelligentDispatchItem, IntelligentDispatches
from .intelligent_device_settings import IntelligentDeviceSettingPreferenceSchedule, IntelligentDeviceSettings

_LOGGER = logging.getLogger(__name__)

api_token_email_query = '''mutation {{
	obtainKrakenToken(input: {{ email: "{email}", password: "{password}" }}) {{
		token
    refreshToken
    refreshExpiresIn
	}}
}}'''

api_token_refresh_query = '''mutation {{
	obtainKrakenToken(input: {{ refreshToken: "{refresh_token}" }}) {{
		token
    refreshToken
    refreshExpiresIn
	}}
}}'''

account_query = '''query {{
  properties(accountNumber: "{account_id}") {{
      id
      occupancyPeriods {{
              effectiveTo
            }}
    }}
  account(accountNumber: "{account_id}") {{
    
    electricityAgreements(active: true) {{
			meterPoint {{
				mpan
				direction
				meters(includeInactive: false) {{
          activeFrom
          activeTo
          makeAndType
					serialNumber
          makeAndType
          meterType
          smartExportElectricityMeter {{
						deviceId
            manufacturer
            model
            firmwareVersion
					}}
          smartImportElectricityMeter {{
						deviceId
            manufacturer
            model
            firmwareVersion
					}}
				}}
				agreements(includeInactive: true) {{
					validFrom
					validTo
          tariff {{
            ... on TariffType {{
              productCode
              tariffCode
            }}
          }}
				}}
			}}
    }}
    gasAgreements(active: true) {{
			meterPoint {{
				mprn
				meters(includeInactive: false) {{
          activeFrom
          activeTo
					serialNumber
          consumptionUnits
          modelName
          mechanism
          smartGasMeter {{
						deviceId
            manufacturer
            model
            firmwareVersion
					}}
				}}
				agreements(includeInactive: true) {{
					validFrom
					validTo
					tariff {{
						tariffCode
            productCode
					}}
				}}
			}}
    }}
  }}
}}'''

live_consumption_query = '''query {{
	smartMeterTelemetry(
    deviceId: "{device_id}"
    grouping: HALF_HOURLY 
		start: "{period_from}"
		end: "{period_to}"
	) {{
    readAt
    consumption
		consumptionDelta
    demand
    export
	}}
}}'''

intelligent_dispatches_query = '''query {{
  devices(accountNumber: "{account_id}", deviceId: "{device_id}") {{
		id
    status {{
      currentState
    }}
  }}
  flexPlannedDispatches(deviceId:"{device_id}") {{
    start
    end
    type
    energyAddedKwh
  }}
	completedDispatches(accountNumber: "{account_id}") {{
		start
		end
    delta
    meta {{
			source
      location
		}}
	}}
}}'''

intelligent_device_query = '''query {{
  devices(accountNumber: "{account_id}") {{
		id
		provider
		deviceType
    status {{
      current
    }}
		__typename
		... on SmartFlexVehicle {{
			make
			model
		}}
		... on SmartFlexChargePoint {{
			make
			model
		}}
	}}
}}'''

intelligent_settings_query = '''query {{
  devices(accountNumber: "{account_id}", deviceId: "{device_id}") {{
		id
    status {{
      isSuspended
    }}
    preferences {{
      targetType
      unit
      mode
      schedules {{
        dayOfWeek
        time
        min
        max
        upperLimit
      }}
    }}
	}}
}}'''

intelligent_settings_mutation = '''mutation {{
  setDevicePreferences(input: {{
    deviceId: "{device_id}"
    mode: CHARGE
    unit: PERCENTAGE
    schedules: [{schedules}]
  }}) {{
    id
  }}
}}'''

intelligent_settings_mutation_schedule = '''{{
  dayOfWeek: {day_of_week}
  time: "{target_time}"
  max: "{target_percentage}"
}}'''

intelligent_turn_on_bump_charge_mutation = '''mutation {{
	updateBoostCharge(input: {{
    deviceId: "{device_id}"
    action: BOOST
  }}) {{
    id
  }}
}}'''

intelligent_turn_off_bump_charge_mutation = '''mutation {{
	updateBoostCharge(input: {{
    deviceId: "{device_id}"
    action: CANCEL
  }}) {{
    id
  }}
}}'''

intelligent_turn_on_smart_charge_mutation = '''mutation {{
  updateDeviceSmartControl(input: {{
    deviceId: "{device_id}"
    action: UNSUSPEND
  }}) {{
    id
  }}
}}'''

intelligent_turn_off_smart_charge_mutation = '''mutation {{
  updateDeviceSmartControl(input: {{
    deviceId: "{device_id}"
    action: SUSPEND
  }}) {{
    id
  }}
}}'''



user_agent_value = "stevekirtley-ha-edf-energy"

integration_context_header = "Ha-Integration-Context"

def get_valid_from(rate):
  return rate["valid_from"]

def get_start(rate):
  return (rate["start"].timestamp(), rate["start"].fold)
    
def rates_to_thirty_minute_increments(data, period_from: datetime, period_to: datetime, tariff_code: str, price_cap: float = None, favour_direct_debit_rates = True):
  """Process the collection of rates to ensure they're in 30 minute periods"""
  starting_period_from = period_from
  results = []
  if ("results" in data):
    items = data["results"]
    items.sort(key=get_valid_from)

    # We need to normalise our data into 30 minute increments so that all of our rates across all tariffs are the same and it's 
    # easier to calculate our target rate sensors
    for item in items:

      if ("payment_method" in item and
          item["payment_method"] is not None and
          (
            (item["payment_method"].lower() == "direct_debit" and favour_direct_debit_rates != True) or
            (item["payment_method"].lower() != "direct_debit" and favour_direct_debit_rates != False)
          )):
        continue

      value_inc_vat = float(item["value_inc_vat"])

      is_capped = False
      if (price_cap is not None and value_inc_vat > price_cap):
        value_inc_vat = price_cap
        is_capped = True

      if "valid_from" in item and item["valid_from"] is not None:
        valid_from = as_utc(parse_datetime(item["valid_from"]))

        # If we're on a fixed rate, then our current time could be in the past so we should go from
        # our target period from date otherwise we could be adjusting times quite far in the past
        if (valid_from < starting_period_from):
          valid_from = starting_period_from
      else:
        valid_from = starting_period_from

      # Some rates don't have end dates, so we should treat this as our period to target
      if "valid_to" in item and item["valid_to"] is not None:
        target_date = as_utc(parse_datetime(item["valid_to"]))

        # Cap our target date to our end period
        if (target_date > period_to):
          target_date = period_to
      else:
        target_date = period_to
      
      while valid_from < target_date:
        valid_to = valid_from + timedelta(minutes=30)
        results.append({
          "value_inc_vat": value_inc_vat,
          "start": valid_from,
          "end": valid_to,
          "tariff_code": tariff_code,
          "is_capped": is_capped
        })

        valid_from = valid_to
        starting_period_from = valid_to
    
  return results

def get_standing_charge(data: list, tariff_code: str, favour_direct_debit_rates: bool):
  for item in data:
    if ("payment_method" in item and
        item["payment_method"] is not None and
        (
          (item["payment_method"].lower() == "direct_debit" and favour_direct_debit_rates != True) or
          (item["payment_method"].lower() != "direct_debit" and favour_direct_debit_rates != False)
        )):
      continue

    return {
      "start": parse_datetime(item["valid_from"]) if "valid_from" in item and item["valid_from"] is not None else None,
      "end": parse_datetime(item["valid_to"]) if "valid_to" in item and item["valid_to"] is not None else None,
      "value_inc_vat": float(item["value_inc_vat"]),
      "tariff_code": tariff_code,
    }
  
  return None

async def async_get_refresh_token(email: str, password: str, timeout_in_seconds: int = 20) -> str:
  """Authenticate with email/password and return a refresh token. Used only at setup time — never stores the password."""
  url = 'https://api.edfgb-kraken.energy/v1/graphql/'
  payload = { "query": api_token_email_query.format(email=email, password=password) }
  timeout = aiohttp.ClientTimeout(total=None, sock_connect=timeout_in_seconds, sock_read=timeout_in_seconds)
  async with aiohttp.ClientSession() as session:
    async with session.post(url, json=payload, timeout=timeout) as response:
      body = await response.json()
  token_data = body.get("data", {}).get("obtainKrakenToken") if body else None
  if token_data and token_data.get("refreshToken"):
    return token_data["refreshToken"]
  errors = body.get("errors") if body else None
  raise AuthenticationException(
    f"Failed to authenticate with EDF Energy",
    [e["message"] for e in errors] if errors else []
  )

class ApiException(Exception): ...

class ServerException(ApiException): ...

class TimeoutException(ApiException): ...

class RequestException(ApiException):
  errors: list[str]

  def __init__(self, message: str, errors: list[str]):
    super().__init__(message)
    self.errors = errors

class AuthenticationException(RequestException): ...

class IntelligentBoostChargeException(RequestException):
  refusal_reason: str | None

  def __init__(self, message: str, errors: list[str], refusal_reason: str | None):
    super().__init__(message, errors)
    self.refusal_reason = refusal_reason

def process_boost_charge_refusal(reason: str):
  if reason == "BC_DEVICE_NOT_YET_LIVE":
    return "Device is not yet live"
  if reason == "BC_DEVICE_RETIRED":
    return "Device is retired"
  if reason == "BC_DEVICE_SUSPENDED":
    return "Device is suspended"
  if reason == "BC_DEVICE_DISCONNECTED":
    return "Device is disconnected"
  if reason == "BC_DEVICE_NOT_AT_HOME":
    return "Device is not at home"
  if reason == "BC_BOOST_CHARGE_IN_PROGRESS":
    return "Boost charge already in progress"
  if reason == "BC_DEVICE_FULLY_CHARGED":
    return "Device is already fully charged"
  
  return None

def process_graphql_response(data: Any, url: str, request_context: str, ignore_errors: bool, accepted_error_codes: list[str]):
  if ("graphql" in url and "errors" in data and ignore_errors == False):
    msg = f'Errors in request ({url}) ({request_context}): {data["errors"]}'
    errors = list(map(lambda error: error["message"].strip(".,!"), data["errors"]))
    errors_as_string = ', '.join(errors)
    _LOGGER.warning(msg)

    for error in data["errors"]:
      if ("extensions" in error and
          "errorCode" in error["extensions"] and
          error["extensions"]["errorCode"] in ("KT-CT-1139", "KT-CT-1111", "KT-CT-1143", "KT-CT-1134", "KT-CT-1135", "OE-0103")):
        raise AuthenticationException(f"Authentication failed - {errors_as_string}. See logs for more details.", errors)

      if ("extensions" in error and
          "errorCode" in error["extensions"] and
          error["extensions"]["errorCode"] in accepted_error_codes):
        return None

      if ("extensions" in error and
          "boostChargeRefusalReasons" in error["extensions"]):
        refusal_reason = process_boost_charge_refusal(error["extensions"]["boostChargeRefusalReasons"])
        raise IntelligentBoostChargeException(f"Boost failed - {refusal_reason} - {errors_as_string}. See logs for more details.", errors, refusal_reason)

    raise RequestException(f"Failed - {errors_as_string}. See logs for more details.", errors)
  
  return data

class EDFEnergyApiClient:
  _refresh_token_lock = RLock()
  _session_lock = RLock()

  def __init__(self, refresh_token: str, electricity_price_cap=None, gas_price_cap=None, timeout_in_seconds=20, favour_direct_debit_rates=True, on_token_refresh=None):
    if not refresh_token:
      raise Exception('refresh_token must be set')

    self._base_url = 'https://api.edfgb-kraken.energy'
    self._backend_base_url = 'https://api.backend.edfgb-kraken.energy'

    self._graphql_token = None
    self._graphql_expiration = None
    self._graphql_refresh_token = refresh_token
    self._graphql_refresh_expiration = None
    self._on_token_refresh = on_token_refresh

    self._product_tracker_cache = dict()

    self._electricity_price_cap = electricity_price_cap
    self._gas_price_cap = gas_price_cap
    self._favour_direct_debit_rates = favour_direct_debit_rates

    self._timeout = aiohttp.ClientTimeout(total=None, sock_connect=timeout_in_seconds, sock_read=timeout_in_seconds)
    self._default_headers = { "user-agent": f'{user_agent_value}/{INTEGRATION_VERSION}' }

    self._session = None

  async def _async_get_rest_auth(self, headers: dict):
    await self.async_refresh_token()
    headers['Authorization'] = f'JWT {self._graphql_token}'
    return None

  async def async_close(self):
    with self._session_lock:
      if self._session is not None:
        await self._session.close()

  def _create_client_session(self):
    if self._session is not None:
      return self._session
    
    with self._session_lock:
      if self._session is not None:
        return self._session
      
      self._session = aiohttp.ClientSession(headers=self._default_headers, skip_auto_headers=['User-Agent'])
      return self._session

  async def async_refresh_token(self):
    """Refresh user token"""
    if (self._graphql_expiration is not None and (self._graphql_expiration - timedelta(minutes=5)) > now()):
      return

    with self._refresh_token_lock:
      # Check that our token wasn't refreshed while waiting for the lock
      if (self._graphql_expiration is not None and (self._graphql_expiration - timedelta(minutes=5)) > now()):
        return

      if (self._graphql_refresh_expiration is not None and self._graphql_refresh_expiration < now()):
        _LOGGER.debug("Refresh token expired - re-authentication required")
        raise AuthenticationException("Refresh token has expired, re-authentication required", [])

      try:
        await self.__async_fetch_token()
      except TimeoutError:
        _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
        raise TimeoutException()

  async def __async_fetch_token(self):
    if not self._graphql_refresh_token:
      raise AuthenticationException("No refresh token available, re-authentication required", [])
    client = self._create_client_session()
    url = f'{self._base_url}/v1/graphql/'
    query = api_token_refresh_query.format(refresh_token=self._graphql_refresh_token)
    payload = { "query": query }
    headers = { integration_context_header: "refresh-token" }
    async with client.post(url, headers=headers, json=payload) as token_response:
      token_response_body = await self.__async_read_response__(token_response, url)
      if (token_response_body is not None and 
          "data" in token_response_body and
          "obtainKrakenToken" in token_response_body["data"] and 
          token_response_body["data"]["obtainKrakenToken"] is not None and
          "token" in token_response_body["data"]["obtainKrakenToken"] and
          "refreshToken" in token_response_body["data"]["obtainKrakenToken"] and
          "refreshExpiresIn" in token_response_body["data"]["obtainKrakenToken"]):
        
        self._graphql_token = token_response_body["data"]["obtainKrakenToken"]["token"]
        new_refresh_token = token_response_body["data"]["obtainKrakenToken"]["refreshToken"]
        self._graphql_refresh_expiration = datetime.fromtimestamp(token_response_body["data"]["obtainKrakenToken"]["refreshExpiresIn"], tz=timezone.utc)
        self._graphql_expiration = now() + timedelta(hours=1)
        _LOGGER.debug(f'Token refreshed; refresh token rotated: {new_refresh_token != self._graphql_refresh_token}; refresh token expiry: {self._graphql_refresh_expiration}')
        if new_refresh_token != self._graphql_refresh_token:
          self._graphql_refresh_token = new_refresh_token
          if self._on_token_refresh is not None:
            await self._on_token_refresh(new_refresh_token)
      elif (self._graphql_expiration is None or self._graphql_expiration > now()):
        raise AuthenticationException("Failed to retrieve auth token and current token is expired")
      else:
        _LOGGER.error("Failed to retrieve auth token")
      
  def map_electricity_meters(self, meter_point):
    is_export = (meter_point["meterPoint"]["direction"] == 'EXPORT') \
      if "meterPoint" in meter_point and "direction" in meter_point["meterPoint"] and meter_point["meterPoint"]["direction"] is not None \
      else None
    meters = list(
      map(lambda m: {
        "active_from": parse_date(m["activeFrom"]) if m["activeFrom"] is not None else None,
        "active_to": parse_date(m["activeTo"]) if m["activeTo"] is not None else None,
        "serial_number": m["serialNumber"],
        "is_export": is_export if is_export is not None else m["smartExportElectricityMeter"] is not None,
        "is_smart_meter": f'{m["meterType"]}'.startswith("S1") or f'{m["meterType"]}'.startswith("S2"),
        "device_id": m["smartImportElectricityMeter"]["deviceId"] if m["smartImportElectricityMeter"] is not None else None,
        "manufacturer": m["smartImportElectricityMeter"]["manufacturer"] 
          if m["smartImportElectricityMeter"] is not None 
          else m["smartExportElectricityMeter"]["manufacturer"] 
          if m["smartExportElectricityMeter"] is not None
          else m["makeAndType"],
        "model": m["smartImportElectricityMeter"]["model"] 
          if m["smartImportElectricityMeter"] is not None 
          else m["smartExportElectricityMeter"]["model"] 
          if m["smartExportElectricityMeter"] is not None
          else None,
        "firmware": m["smartImportElectricityMeter"]["firmwareVersion"] 
          if m["smartImportElectricityMeter"] is not None 
          else m["smartExportElectricityMeter"]["firmwareVersion"] 
          if m["smartExportElectricityMeter"] is not None
          else None
        },
        meter_point["meterPoint"]["meters"]
        if "meterPoint" in meter_point and "meters" in meter_point["meterPoint"] and meter_point["meterPoint"]["meters"] is not None
        else []
      )
    )

    meters.sort(key=lambda meter: meter["active_from"], reverse=True)

    return {
      "mpan": meter_point["meterPoint"]["mpan"],
      "meters": meters,
      "agreements": list(map(lambda a: {
        "start": a["validFrom"],
        "end": a["validTo"],
        "tariff_code": a["tariff"]["tariffCode"] if "tariff" in a and "tariffCode" in a["tariff"] else None,
        "product_code": a["tariff"]["productCode"] if "tariff" in a and "productCode" in a["tariff"] else None,
      }, 
      meter_point["meterPoint"]["agreements"]
      if "meterPoint" in meter_point and "agreements" in meter_point["meterPoint"] and meter_point["meterPoint"]["agreements"] is not None
      else []
    ))
  }

  def map_gas_meters(self, meter_point):
    meters = list(
      map(lambda m: {
        "active_from": parse_date(m["activeFrom"]) if m["activeFrom"] is not None else None,
        "active_to": parse_date(m["activeTo"]) if m["activeTo"] is not None else None,
        "serial_number": m["serialNumber"],
        "consumption_units": m["consumptionUnits"],
        "is_smart_meter": m["mechanism"] == "S1" or m["mechanism"] == "S2",
        "device_id": m["smartGasMeter"]["deviceId"] if m["smartGasMeter"] is not None else None,
        "manufacturer": m["smartGasMeter"]["manufacturer"] 
          if m["smartGasMeter"] is not None 
          else m["modelName"],
        "model": m["smartGasMeter"]["model"] 
          if m["smartGasMeter"] is not None 
          else None,
        "firmware": m["smartGasMeter"]["firmwareVersion"] 
          if m["smartGasMeter"] is not None 
          else None
      },
      meter_point["meterPoint"]["meters"]
      if "meterPoint" in meter_point and "meters" in meter_point["meterPoint"] and meter_point["meterPoint"]["meters"] is not None
      else []
      )
    )

    meters.sort(key=lambda meter: meter["active_from"], reverse=True)

    return {
      "mprn": meter_point["meterPoint"]["mprn"],
      "meters": meters,
      "agreements": list(map(lambda a: {
          "start": a["validFrom"],
          "end": a["validTo"],
          "tariff_code": a["tariff"]["tariffCode"] if "tariff" in a and "tariffCode" in a["tariff"] else None,
          "product_code": a["tariff"]["productCode"] if "tariff" in a and "productCode" in a["tariff"] else None,
        },
        meter_point["meterPoint"]["agreements"]
        if "meterPoint" in meter_point and "agreements" in meter_point["meterPoint"] and meter_point["meterPoint"]["agreements"] is not None
        else []
      ))
    }
  
  def map_properties(self, properties):
    property_ids = []
    for property in properties:
      if ("occupancyPeriods" in property and property["occupancyPeriods"] is not None):
        for period in property["occupancyPeriods"]:
          if "effectiveTo" in period and (period["effectiveTo"] is None or parse_datetime(period["effectiveTo"]) < now()):
            property_ids.append(property["id"])
    return property_ids

  async def async_check_headers(self):
    """Checks the headers are set correctly"""
    try:
      request_context = "test-headers"
      client = self._create_client_session()
      url = f'http://httpbin.org/headers'
      headers = { "Authorization": f"TEST", integration_context_header: request_context }
      async with client.get(url, headers=headers) as response:

        text = await response.text()
        response_body = json.loads(text)

        integration_context_header_present = integration_context_header in response_body['headers'] and response_body['headers'][integration_context_header] == request_context
        authorization_header_present = 'Authorization' in response_body['headers'] and response_body['headers']['Authorization'] == 'TEST'
        user_agent_header_present = 'User-Agent' in response_body['headers'] and response_body['headers']['User-Agent'] == self._default_headers['user-agent']
        
        _LOGGER.debug(f'integration_context_header_present: {integration_context_header_present}; authorization_header_present: {authorization_header_present}; user_agent_header_present: {user_agent_header_present}')
        _LOGGER.debug(f'Header response: {text}')

        return (
          integration_context_header_present and
          authorization_header_present and
          user_agent_header_present
        )
    
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
    
    return None
    
  async def async_get_account(self, account_id):
    """Get the user's account"""
    await self.async_refresh_token()

    try:
      request_context = "get-account"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      # Get account response
      payload = { "query": account_query.format(account_id=account_id) }
      headers = { "Authorization": f"{self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as account_response:
        account_response_body = await self.__async_read_response__(account_response, url)
        _LOGGER.debug(f'account: {account_response_body}')

        if (account_response_body is not None and 
            "data" in account_response_body and 
            "account" in account_response_body["data"] and 
            account_response_body["data"]["account"] is not None):
          return {
            "id": account_id,
            "property_ids": list(
              self.map_properties(
                account_response_body["data"]["properties"]
                if "data" in account_response_body and "properties" in account_response_body["data"]
                else []
              )
            ),
            "electricity_meter_points": list(map(self.map_electricity_meters, 
              account_response_body["data"]["account"]["electricityAgreements"]
              if "electricityAgreements" in account_response_body["data"]["account"] and account_response_body["data"]["account"]["electricityAgreements"] is not None
              else []
            )),
            "gas_meter_points": list(map(self.map_gas_meters,
              account_response_body["data"]["account"]["gasAgreements"] 
              if "gasAgreements" in account_response_body["data"]["account"] and account_response_body["data"]["account"]["gasAgreements"] is not None
              else []
            )),
          }
        else:
          _LOGGER.error("Failed to retrieve account")
    
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
    
    return None

  async def async_get_smart_meter_consumption(self, device_id: str, period_from: datetime, period_to: datetime):
    """Get the user's smart meter consumption"""
    await self.async_refresh_token()

    try:
      request_context = "home-mini-consumption"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'

      payload = { "query": live_consumption_query.format(device_id=device_id, period_from=period_from.strftime("%Y-%m-%dT%H:%M:%S%z"), period_to=period_to.strftime("%Y-%m-%dT%H:%M:%S%z")) }
      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as live_consumption_response:
        response_body = await self.__async_read_response__(live_consumption_response, url)

        if (response_body is not None and "data" in response_body and "smartMeterTelemetry" in response_body["data"] and response_body["data"]["smartMeterTelemetry"] is not None and len(response_body["data"]["smartMeterTelemetry"]) > 0):
          return list(map(lambda mp: {
            "total_consumption": float(mp["consumption"]) / 1000 if "consumption" in mp and mp["consumption"] is not None else None,
            "total_export": float(mp["export"]) / 1000 if "export" in mp and mp["export"] is not None else None,
            "consumption": float(mp["consumptionDelta"]) / 1000 if "consumptionDelta" in mp and mp["consumptionDelta"] is not None else 0,
            "demand": float(mp["demand"]) if "demand" in mp and mp["demand"] is not None else None,
            "start": parse_datetime(mp["readAt"]),
            "end": parse_datetime(mp["readAt"]) + timedelta(minutes=30)
          }, response_body["data"]["smartMeterTelemetry"]))
        else:
          _LOGGER.debug(f"Failed to retrieve smart meter consumption data - device_id: {device_id}; period_from: {period_from}; period_to: {period_to}")
    
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

    return None

  async def async_get_electricity_standard_rates(self, product_code: str, tariff_code: str, period_from: datetime, period_to: datetime):
    """Get the current standard rates"""
    results = []

    try:
      request_context = "electricity-rates"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      page = 1
      has_more_rates = True
      while has_more_rates:
        url = f'{self._base_url}/v1/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&page={page}'
        async with client.get(url, auth=auth, headers=headers) as response:
          data = await self.__async_read_response__(response, url)
          if data is None:
            return []
          else:
            results = results + rates_to_thirty_minute_increments(data, period_from, period_to, tariff_code, self._electricity_price_cap, self._favour_direct_debit_rates)
            has_more_rates = "next" in data and data["next"] is not None
            if has_more_rates:
              page = page + 1
    
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
    
    results.sort(key=get_start)
    return results

  async def async_get_electricity_day_night_rates(self, product_code: str, tariff_code: str, is_smart_meter: bool, period_from: datetime, period_to: datetime):
    """Get the current day and night rates"""
    results = []

    try:
      request_context = "electricity-rates"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      url = f'{self._base_url}/v1/products/{product_code}/electricity-tariffs/{tariff_code}/day-unit-rates?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}'
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if data is None:
          return []
        else:
          # Normalise the rates to be in 30 minute increments and remove any rates that fall outside of our day period
          day_rates = rates_to_thirty_minute_increments(data, period_from, period_to, tariff_code, self._electricity_price_cap, self._favour_direct_debit_rates)
          for rate in day_rates:
            if self.__is_night_rate(rate, is_smart_meter) == False:
              results.append(rate)

      url = f'{self._base_url}/v1/products/{product_code}/electricity-tariffs/{tariff_code}/night-unit-rates?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}'
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if data is None:
          return []

        # Normalise the rates to be in 30 minute increments and remove any rates that fall outside of our night period
        night_rates = rates_to_thirty_minute_increments(data, period_from, period_to, tariff_code, self._electricity_price_cap, self._favour_direct_debit_rates)
        for rate in night_rates:
          if self.__is_night_rate(rate, is_smart_meter) == True:
            results.append(rate)
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

    # Because we retrieve our day and night periods separately over a 2 day period, we need to sort our rates 
    results.sort(key=get_start)

    return results

  async def async_get_electricity_rates(self, product_code: str, tariff_code: str, is_smart_meter: bool, period_from: datetime, period_to: datetime):
    """Get the current rates"""

    if is_day_night_tariff(tariff_code):
      return await self.async_get_electricity_day_night_rates(product_code, tariff_code, is_smart_meter, period_from, period_to)
    else:
      return await self.async_get_electricity_standard_rates(product_code, tariff_code, period_from, period_to)
      
  async def async_get_electricity_consumption(self, mpan: str, serial_number: str, period_from: datetime | None = None, period_to: datetime | None = None, page_size: int | None = None):
    """Get the current electricity consumption"""

    try:
      request_context = "electricity-consumption"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)

      query_params = []
      if period_from is not None:
        query_params.append(f'period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}')

      if period_to is not None:
        query_params.append(f'period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}')

      if page_size is not None:
        query_params.append(f'page_size={page_size}')

      query_string = '&'.join(query_params)

      url = f"{self._base_url}/v1/electricity-meter-points/{mpan}/meters/{serial_number}/consumption{f'?{query_string}' if len(query_string) > 0 else ''}"
      async with client.get(url, auth=auth, headers=headers) as response:
        
        data = await self.__async_read_response__(response, url)
        if (data is not None and "results" in data):
          data = data["results"]
          results = []
          for item in data:
            item = self.__process_consumption(item)

            # For some reason, the end point sometimes returns slightly more data than we requested, so we need to filter out the results
            if (period_from is None or as_utc(item["start"]) >= period_from) and (period_to is None or as_utc(item["end"]) <= period_to):
              results.append(item)
            else:
              _LOGGER.debug(f'Skipping gas consumption item due to outside requested scope - period_from: {period_from}; period_to: {period_to}; item: {item}; mpan: {mpan}; serial_number: {serial_number}')
          
          results.sort(key=self.__get_interval_end)
          return results
        
        return None
        
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_get_gas_rates(self, product_code: str, tariff_code: str, period_from: datetime, period_to: datetime):
    """Get the gas rates"""
    results = []

    try:
      request_context = "gas-rates"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      url = f'{self._base_url}/v1/products/{product_code}/gas-tariffs/{tariff_code}/standard-unit-rates?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}'
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if data is None:
          return None
        else:
          results = rates_to_thirty_minute_increments(data, period_from, period_to, tariff_code, self._gas_price_cap, self._favour_direct_debit_rates)

      return results
    
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_get_gas_consumption(self, mprn: str, serial_number: str, period_from: datetime | None = None, period_to: datetime | None = None, page_size: int | None = None):
    """Get the current gas rates"""
    
    try:
      request_context = "gas-consumption"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)

      query_params = []
      if period_from is not None:
        query_params.append(f'period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}')

      if period_to is not None:
        query_params.append(f'period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}')

      if page_size is not None:
        query_params.append(f'page_size={page_size}')

      query_string = '&'.join(query_params)

      url = f"{self._base_url}/v1/gas-meter-points/{mprn}/meters/{serial_number}/consumption{f'?{query_string}' if len(query_string) > 0 else ''}"
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if (data is not None and "results" in data):
          data = data["results"]
          results = []
          for item in data:
            item = self.__process_consumption(item)

            # For some reason, the end point sometimes returns slightly more data than we requested, so we need to filter out the results
            if (period_from is None or as_utc(item["start"]) >= period_from) and (period_to is None or as_utc(item["end"]) <= period_to): 
              results.append(item)
            else:
              _LOGGER.debug(f'Skipping gas consumption item due to outside requested scope - period_from: {period_from}; period_to: {period_to}; item: {item}; mprn: {mprn}; serial_number: {serial_number}')

          results.sort(key=self.__get_interval_end)
          return results
        
        return None
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_get_product(self, product_code: str):
    """Get all products"""

    try:
      request_context = "get-product-info"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      url = f'{self._base_url}/v1/products/{product_code}'
      async with client.get(url, auth=auth, headers=headers) as response:
        return await self.__async_read_response__(response, url)
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_get_electricity_standing_charge(self, product_code: str, tariff_code: str, period_from: datetime, period_to: datetime):
    """Get the electricity standing charges"""
    result = None

    try:
      request_context = "electricity-standing-charge"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      url = f'{self._base_url}/v1/products/{product_code}/electricity-tariffs/{tariff_code}/standing-charges?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}'
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if (data is not None and "results" in data and len(data["results"]) > 0):
          result = get_standing_charge(data["results"], tariff_code, self._favour_direct_debit_rates)

      return result
    except TimeoutError:
        _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
        raise TimeoutException()

  async def async_get_gas_standing_charge(self, product_code: str, tariff_code: str, period_from: datetime, period_to: datetime):
    """Get the gas standing charges"""
    result = None

    try:
      request_context = "gas-standing-charge"
      client = self._create_client_session()
      headers = { integration_context_header: request_context }
      auth = await self._async_get_rest_auth(headers)
      url = f'{self._base_url}/v1/products/{product_code}/gas-tariffs/{tariff_code}/standing-charges?period_from={period_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}&period_to={period_to.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}'
      async with client.get(url, auth=auth, headers=headers) as response:
        data = await self.__async_read_response__(response, url)
        if (data is not None and "results" in data and len(data["results"]) > 0):
          result = get_standing_charge(data["results"], tariff_code, self._favour_direct_debit_rates)

      return result
    except TimeoutError:
        _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
        raise TimeoutException()
  
  async def async_get_intelligent_dispatches(self, account_id: str, device_id: str):
    """Get the user's intelligent dispatches"""
    await self.async_refresh_token()

    try:
      request_context = "intelligent-dispatches"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_dispatches_query.format(account_id=account_id, device_id=device_id) }
      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url, accepted_error_codes=['KT-CT-4340'])
        _LOGGER.debug(f'async_get_intelligent_dispatches: {response_body}')

        current_state = None
        if (response_body is not None and "data" in response_body and "devices" in response_body["data"]):
          for device in response_body["data"]["devices"]:
            if device["id"] == device_id:
              current_state = device["status"]["currentState"]

        if (response_body is not None and "data" in response_body):
          planned_dispatches = list(map(lambda ev: IntelligentDispatchItem(
              as_utc(parse_datetime(ev["start"])),
              as_utc(parse_datetime(ev["end"])),
              float(ev["energyAddedKwh"]) if "energyAddedKwh" in ev and ev["energyAddedKwh"] is not None else None,
              ev["type"] if "type" in ev else None,
              None
            ), response_body["data"]["flexPlannedDispatches"]
            if "flexPlannedDispatches" in response_body["data"] and response_body["data"]["flexPlannedDispatches"] is not None
            else [])
          )

          completed_dispatches = list(map(lambda ev: IntelligentDispatchItem(
              as_utc(parse_datetime(ev["start"])),
              as_utc(parse_datetime(ev["end"])),
              float(ev["delta"]) if "delta" in ev and ev["delta"] is not None else None,
              ev["meta"]["source"] if "meta" in ev and "source" in ev["meta"] else None,
              ev["meta"]["location"] if "meta" in ev and "location" in ev["meta"] else None,
            ), response_body["data"]["completedDispatches"]
            if "completedDispatches" in response_body["data"] and response_body["data"]["completedDispatches"] is not None
            else [])
          )

          planned_dispatches.sort(key=lambda x: x.start)
          completed_dispatches.sort(key=lambda x: x.start)

          return IntelligentDispatches(
            current_state,
            planned_dispatches,
            completed_dispatches
          )
        else:
          _LOGGER.error("Failed to retrieve intelligent dispatches")
      
      return None
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
  
  async def async_get_intelligent_settings(self, account_id: str, device_id: str):
    """Get the user's intelligent settings"""
    await self.async_refresh_token()

    try:
      request_context = "intelligent-settings"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_settings_query.format(account_id=account_id, device_id=device_id) }
      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_get_intelligent_settings: {response_body}')

        _LOGGER.debug(f'Intelligent Settings: {response_body}')
        if (response_body is not None and "data" in response_body and "devices" in response_body["data"]):

          devices = list(response_body["data"]["devices"])
          if len(devices) == 1:
            return IntelligentDeviceSettings.model_validate(devices[0])
        else:
          _LOGGER.error("Failed to retrieve intelligent settings")
      
      return None

    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
  
  def __ready_time_to_time__(self, time_str: str) -> time:
    if time_str is not None:
      parts = time_str.split(':')
      if len(parts) != 3:
        raise Exception(f"Unexpected number of parts in '{time_str}'")
      
      return time(int(parts[0]), int(parts[1]), int(parts[2]))

    return None
  
  async def async_update_intelligent_car_target_percentage(
      self, 
      account_id: str,
      device_id: str,
      target_percentage: int
    ):
    """Update a user's intelligent car target percentage"""
    await self.async_refresh_token()

    settings = await self.async_get_intelligent_settings(account_id, device_id)
    if settings is None:
      raise Exception(f'Failed to retrieve intelligent settings for device {device_id}')
    if settings.preferences is None:
      raise Exception(f'Device {device_id} has no preferences — charge target not supported')
    if len(settings.preferences.schedules) == 0:
      raise Exception(f'Device {device_id} has no schedules — charge target not supported')

    new_schedules = []
    for schedule in settings.preferences.schedules:
      schedule.max = target_percentage
      new_schedules.append(schedule)

    try:
      request_context = "set-intelligent-target-perc"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      schedules_str = self.__intelligent_settings_schedules__(new_schedules)
      payload = { "query": intelligent_settings_mutation.format(
          device_id=device_id,
          schedules=schedules_str
        )
      }

      _LOGGER.debug(f'Payload for intelligent settings mutation: {payload}')
      _LOGGER.debug(f'Schedules string: {schedules_str}')

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_update_intelligent_car_target_percentage: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_update_intelligent_car_target_time(
      self,
      account_id: str,
      device_id: str,
      target_time: time,
    ):
    """Update a user's intelligent car target time"""
    await self.async_refresh_token()
    
    settings = await self.async_get_intelligent_settings(account_id, device_id)
    if settings is None:
      raise Exception(f'Failed to retrieve intelligent settings for device {device_id}')
    if settings.preferences is None:
      raise Exception(f'Device {device_id} has no preferences — target time not supported')
    if len(settings.preferences.schedules) == 0:
      raise Exception(f'Device {device_id} has no schedules — target time not supported')

    new_schedules = []
    for schedule in settings.preferences.schedules:
      schedule.time = target_time
      new_schedules.append(schedule)

    try:
      request_context = "set-intelligent-target-time"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      schedules_str = self.__intelligent_settings_schedules__(new_schedules)
      payload = { "query": intelligent_settings_mutation.format(
          device_id=device_id,
          schedules=schedules_str
        )
      }

      _LOGGER.debug(f'Payload for target time mutation: {payload}')
      _LOGGER.debug(f'Schedules string: {schedules_str}')

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_update_intelligent_car_target_time: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  def __intelligent_settings_schedules__(self, schedules: List[IntelligentDeviceSettingPreferenceSchedule]) -> str:
    return ", ".join(list(map(lambda schedule: intelligent_settings_mutation_schedule
                    .format(day_of_week=schedule.dayOfWeek,
                            target_percentage=schedule.max,
                            target_time=schedule.time.strftime("%H:%M")), schedules)))

  async def async_turn_on_intelligent_bump_charge(
      self, device_id: str,
    ):
    """Turn on an intelligent bump charge"""
    await self.async_refresh_token()

    try:
      request_context = "set-intelligent-bump"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_turn_on_bump_charge_mutation.format(
        device_id=device_id,
      ) }

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_turn_on_intelligent_bump_charge: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_turn_off_intelligent_bump_charge(
      self, device_id: str,
    ):
    """Turn off an intelligent bump charge"""
    await self.async_refresh_token()

    try:
      request_context = "set-intelligent-bump"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_turn_off_bump_charge_mutation.format(
        device_id=device_id,
      ) }

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_turn_off_intelligent_bump_charge: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_turn_on_intelligent_smart_charge(
      self, device_id: str,
    ):
    """Turn on an intelligent smart charge"""
    await self.async_refresh_token()

    try:
      request_context = "set-intelligent-smart"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_turn_on_smart_charge_mutation.format(
        device_id=device_id,
      ) }

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_turn_on_intelligent_smart_charge: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

  async def async_turn_off_intelligent_smart_charge(
      self, device_id: str,
    ):
    """Turn off an intelligent smart charge"""
    await self.async_refresh_token()

    try:
      request_context = "set-intelligent-smart"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_turn_off_smart_charge_mutation.format(
        device_id=device_id,
      ) }

      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_turn_off_intelligent_smart_charge: {response_body}')
    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
  
  async def async_get_intelligent_devices(self, account_id: str) -> list[IntelligentDevice]:
    """Get the user's intelligent device"""
    await self.async_refresh_token()

    try:
      request_context = "get-intelligent-device"
      client = self._create_client_session()
      url = f'{self._base_url}/v1/graphql/'
      payload = { "query": intelligent_device_query.format(account_id=account_id) }
      headers = { "Authorization": f"JWT {self._graphql_token}", integration_context_header: request_context }
      async with client.post(url, json=payload, headers=headers) as response:
        response_body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'async_get_intelligent_device: {response_body}')

        result = []
        if (response_body is not None and "data" in response_body and "devices" in response_body["data"]):
          devices: list = response_body["data"]["devices"]

          for device in devices:
            device_type = device.get("__typename", "")
            if device_type not in ("SmartFlexChargePoint", "SmartFlexVehicle"):
              continue

            if (device["deviceType"] != "ELECTRIC_VEHICLES" or device["status"]["current"] != "LIVE"):
              continue

            make = device.get("make", "")
            model = device.get("model", "")
            vehicleBatterySizeInKwh = None
            chargePointPowerInKw = None
            is_charger = device_type == "SmartFlexChargePoint"

            result.append(IntelligentDevice(
              device["id"],
              device["provider"],
              make,
              model,
              vehicleBatterySizeInKwh,
              chargePointPowerInKw,
              INTELLIGENT_DEVICE_KIND_ELECTRIC_VEHICLE_CHARGERS if is_charger else device["deviceType"]
            ))

          return result
        else:
          _LOGGER.error("Failed to retrieve intelligent device")
      
      return []

    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()
  
  async def async_get_sunday_saver(self, account_id: str, week_start_date: str):
    """Get Sunday Saver free energy slot data for the given week anchor date."""
    await self.async_refresh_token()

    try:
      request_context = "sunday-saver"
      client = self._create_client_session()
      url = 'https://www.edfenergy.com/support/sunday-saver/api/weekly'
      payload = {
        "accountNumber": account_id,
        "WEEK_START_DATE": week_start_date,
      }
      headers = {
        "Authorization": self._graphql_token,
        integration_context_header: request_context,
      }
      async with client.post(url, json=payload, headers=headers) as response:
        body = await self.__async_read_response__(response, url)
        _LOGGER.debug(f'sunday_saver response: {body}')

        if body is None:
          return None

        if "data" not in body:
          return {}

        raw_data = body["data"]
        if isinstance(raw_data, str):
          try:
            parsed = json.loads(raw_data)
          except Exception:
            _LOGGER.warning(f'Failed to parse Sunday Saver data payload: {raw_data}')
            return None
          if isinstance(parsed, str):
            # Double-encoded: the API returned a JSON string whose content is itself JSON.
            # Try one more decode (e.g. "{}" → empty dict meaning no event this week).
            try:
              parsed = json.loads(parsed)
            except Exception:
              _LOGGER.warning(f'Sunday Saver data is double-encoded but inner value is not valid JSON: {parsed}')
              return None
          if not isinstance(parsed, dict):
            _LOGGER.warning(f'Sunday Saver data decoded to unexpected type {type(parsed).__name__}: {parsed}')
            return None
          return parsed
        elif isinstance(raw_data, dict):
          return raw_data

        _LOGGER.warning(f'Sunday Saver data has unexpected type {type(raw_data).__name__}: {raw_data}')
        return None

    except TimeoutError:
      _LOGGER.warning(f'Failed to connect. Timeout of {self._timeout} exceeded.')
      raise TimeoutException()

    return None

  def __get_interval_end(self, item):
    return (item["end"].timestamp(), item["end"].fold)

  def __is_night_rate(self, rate, is_smart_meter: bool):
    # Normally the economy seven night rate is between 12am and 7am UK time
    # However, if a smart meter is being used then the times are between 12:30am and 7:30am UTC time
    if is_smart_meter:
        is_night_rate = self.__is_between_times(rate, "00:30:00", "07:30:00", True)
    else:
        is_night_rate = self.__is_between_times(rate, "00:00:00", "07:00:00", False)
    return is_night_rate

  def __is_between_times(self, rate, target_from_time, target_to_time, use_utc):
    """Determines if a current rate is between two times"""
    rate_local_valid_from = as_local(rate["start"])
    rate_local_valid_to = as_local(rate["end"])

    if use_utc:
        rate_utc_valid_from = as_utc(rate["start"])
        # We need to convert our times into local time to account for BST to ensure that our rate is valid between the target times.
        from_date_time = as_local(parse_datetime(rate_utc_valid_from.strftime(f"%Y-%m-%dT{target_from_time}Z")))
        to_date_time = as_local(parse_datetime(rate_utc_valid_from.strftime(f"%Y-%m-%dT{target_to_time}Z")))
    else:
        local_now = now()
        # We need to convert our times into local time to account for BST to ensure that our rate is valid between the target times.
        from_date_time = as_local(parse_datetime(rate_local_valid_from.strftime(f"%Y-%m-%dT{target_from_time}{local_now.strftime('%z')}")))
        to_date_time = as_local(parse_datetime(rate_local_valid_from.strftime(f"%Y-%m-%dT{target_to_time}{local_now.strftime('%z')}")))

    _LOGGER.debug('is_valid: %s; from_date_time: %s; to_date_time: %s; rate_local_valid_from: %s; rate_local_valid_to: %s', rate_local_valid_from >= from_date_time and rate_local_valid_from < to_date_time, from_date_time, to_date_time, rate_local_valid_from, rate_local_valid_to)

    return rate_local_valid_from >= from_date_time and rate_local_valid_from < to_date_time

  def __process_consumption(self, item):
    return {
      "consumption": float(item["consumption"]),
      "start": as_utc(parse_datetime(item["interval_start"])),
      "end": as_utc(parse_datetime(item["interval_end"]))
    }

  async def __async_read_response__(self, response, url, ignore_errors = False, accepted_error_codes = []):
    """Reads the response, logging any json errors"""

    request_context = response.request_info.headers[integration_context_header] if integration_context_header in response.request_info.headers else "Unknown"

    text = await response.text()

    if response.status >= 400:
      if response.status >= 500:
        msg = f'Response received - {url} ({request_context}) - DO NOT REPORT - EDF Energy server error ({url}): {response.status}; {text}'
        _LOGGER.warning(msg)
        raise ServerException(msg)
      elif response.status in [401, 403]:
        msg = f'Response received - {url} ({request_context}) - Unauthenticated request: {response.status}; {text}'
        _LOGGER.warning(msg)
        raise AuthenticationException(msg, [])
      elif response.status not in [404]:
        msg = f'Response received - {url} ({request_context}) - Failed to send request: {response.status}; {text}'
        _LOGGER.warning(msg)
        raise RequestException(msg, [])
      
      _LOGGER.info(f"Response received - {url} ({request_context}) - Unexpected response received: {response.status}; {text}")
      return None
    
    _LOGGER.debug(f'Response received - {url} ({request_context}) - Successful response')

    data_as_json = None
    try:
      data_as_json = json.loads(text)
    except:
      raise Exception(f'Failed to extract response json: {url}; {text}')
    
    return process_graphql_response(data_as_json, url, request_context, ignore_errors, accepted_error_codes)
