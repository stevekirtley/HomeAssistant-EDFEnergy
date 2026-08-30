import pytest

from integration import get_test_context
from custom_components.edf_energy.api_client import EDFEnergyApiClient

pytestmark = pytest.mark.xfail(reason="GraphQL token refresh blocked by CloudFront on GitHub Actions runner IPs", strict=False)

@pytest.mark.asyncio
async def test_when_get_intelligent_dispatches_is_called_for_account_on_different_tariff_then_exception_is_raised():
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(context.refresh_token)
    account_id = context.account_id

    # Act
    exception_raised = False
    try:
        await client.async_get_intelligent_dispatches(account_id, "123")
    except:
        exception_raised = True

    # Assert
    assert exception_raised == True
  