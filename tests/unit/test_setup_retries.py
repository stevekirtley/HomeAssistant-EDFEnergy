"""A connection error during setup used to kill the integration for good.

Raised as issue #42. Home Assistant only retries a config entry when setup raises
ConfigEntryNotReady; any other exception marks the entry "Failed to set up" and leaves it
there until somebody reloads it by hand. async_setup_entry caught our own ApiException and
re-raised everything else, so a DNS lookup that failed because the network wasn't up yet -
the normal state of affairs for a few seconds after a reboot - escaped as an
aiohttp.ClientConnectorError and stranded the entry. Nothing in the logs afterwards, no
repair, no retry: the integration was simply gone until the next manual reload.

These tests cover the decision itself rather than the whole of async_setup_entry, which
needs most of Home Assistant stood up before it will run.
"""
import asyncio
import socket

import aiohttp
import pytest

from custom_components.edf_energy.api_client import (
  ApiException,
  AuthenticationException,
  RequestException,
  ServerException,
  TimeoutException,
)
from custom_components.edf_energy.utils.error import RETRYABLE_EXCEPTIONS, api_exception_to_string
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady


def is_handled(e: Exception):
  """The test's stand-in for the isinstance check in async_setup_entry."""
  return isinstance(e, (ApiException, *RETRYABLE_EXCEPTIONS))


def connector_error():
  """What aiohttp actually raises when a hostname won't resolve."""
  key = aiohttp.client_reqrep.ConnectionKey("api.edfgb-kraken.energy", 443, True, True, None, None, None)
  return aiohttp.ClientConnectorError(key, socket.gaierror(8, "nodename nor servname provided"))


@pytest.mark.parametrize("e", [
  connector_error(),
  aiohttp.ClientConnectionError("closed"),
  aiohttp.ServerDisconnectedError(),
  asyncio.TimeoutError(),
  ConnectionResetError(),
  OSError(51, "Network is unreachable"),
  socket.gaierror(8, "nodename nor servname provided"),
])
def test_a_connection_failure_is_handled_rather_than_escaping(e):
  """The #42 cases. Each of these used to fall straight through to `raise`."""
  assert is_handled(e)


@pytest.mark.parametrize("e", [
  ApiException(),
  ServerException(),
  TimeoutException(),
  RequestException("failed", ["boom"]),
  AuthenticationException("expired", []),
])
def test_our_own_errors_are_still_handled(e):
  assert is_handled(e)


@pytest.mark.parametrize("e", [
  KeyError("kind"),
  ValueError("nonsense"),
  ConfigEntryNotReady("no account"),
  ConfigEntryAuthFailed("reauth"),
])
def test_everything_else_still_escapes(e):
  """A bug in our own code should surface, not be swallowed as a network wobble.

  The two Home Assistant exceptions matter as much: they are raised inside the same try
  block and have to pass through untouched, or setup would answer the wrong question.
  """
  assert not is_handled(e)


def test_a_connection_error_gets_a_message_that_names_it():
  """api_exception_to_string used to tell everyone EDF's servers were at fault."""
  message = api_exception_to_string(connector_error())
  assert "ClientConnectorError" in message
  assert "EDF Energy servers" not in message


def test_our_own_errors_keep_their_wording():
  assert api_exception_to_string(TimeoutException()) == "EDF Energy servers did not respond in a timely manner"
  assert api_exception_to_string(ServerException()) == "Error on EDF Energy servers. Please try again later."
