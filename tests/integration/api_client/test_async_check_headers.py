import pytest

from integration import get_test_context
from custom_components.edf_energy.api_client import EDFEnergyApiClient

@pytest.mark.asyncio
@pytest.mark.xfail(reason="GraphQL token refresh blocked by CloudFront on GitHub Actions runner IPs", strict=False)
async def test_when_check_headers_is_called_then_True_returned():
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(context.refresh_token)

    # Act
    result = await client.async_check_headers()

    # Assert
    assert result == True