from .base import EDFEnergyBaseDataLastRetrieved
from ..intelligent.base import EDFEnergyIntelligentSensor
from ..api_client.intelligent_device import IntelligentDevice

class EDFEnergyIntelligentSettingsDataLastRetrieved(EDFEnergyIntelligentSensor, EDFEnergyBaseDataLastRetrieved):
  """Sensor for displaying the last time the intelligent settings data was last retrieved."""

  def __init__(self, hass, coordinator, account_id: str, device: IntelligentDevice):
    """Init sensor."""
    self._account_id = account_id
    self._device_id = device.id
    EDFEnergyBaseDataLastRetrieved.__init__(self, hass, coordinator)
    EDFEnergyIntelligentSensor.__init__(self, device)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_{self._device_id}_intelligent_settings_data_last_retrieved"
    
  @property
  def name(self):
    """Name of the sensor."""
    return f"Smart Charging Settings Data Last Retrieved ({self._device_id})"