import asyncio

import aiohttp

from ..api_client import ApiException, RequestException, ServerException, TimeoutException

# Failures that are worth another go rather than giving up on. aiohttp's ClientError covers
# DNS lookups and refused connections, which is exactly what a Home Assistant restart runs
# into when the network isn't up yet; OSError catches the lower level cases aiohttp doesn't
# wrap. None of these mean the account or the credential is wrong, so anything that treats
# them as fatal strands the integration until someone notices and reloads it by hand.
RETRYABLE_EXCEPTIONS = (aiohttp.ClientError, asyncio.TimeoutError, OSError)

def api_exception_to_string(e: Exception):
  if isinstance(e, ServerException):
    return "Error on EDF Energy servers. Please try again later."
  if isinstance(e, TimeoutException):
    return "EDF Energy servers did not respond in a timely manner"
  if isinstance(e, RequestException):
    return f"EDF Energy server returned one or more errors - {', '.join(e.errors)}"

  if not isinstance(e, ApiException):
    # Not one of ours - a connection error from aiohttp, say - so name it rather than
    # claiming EDF's servers are at fault when the problem is closer to home.
    return f"{type(e).__name__}: {e}"

  return "Error on EDF Energy servers. Please try again later."

def exception_to_string(e: Exception):
  if e is None:
    return 'None'

  if isinstance(e, ApiException):
    return api_exception_to_string(e)
  
  return "Unexpected error. Please review logs fo more information"