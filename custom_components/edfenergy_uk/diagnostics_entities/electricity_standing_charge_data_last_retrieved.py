from .base import EDFEnergyBaseDataLastRetrieved
from ..electricity.base import EDFEnergyElectricitySensor

class EDFEnergyElectricityCurrentStandingChargeDataLastRetrieved(EDFEnergyElectricitySensor, EDFEnergyBaseDataLastRetrieved):
  """Sensor for displaying the last time the standing charge data was last retrieved."""

  def __init__(self, hass, coordinator, meter, point):
    """Init sensor."""
    self._mpan = point["mpan"]
    self._serial_number = meter["serial_number"]
    EDFEnergyElectricitySensor.__init__(self, hass, meter, point)
    EDFEnergyBaseDataLastRetrieved.__init__(self, hass, coordinator)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_electricity_{self._serial_number}_{self._mpan}_standing_charge_data_last_retrieved"
    
  @property
  def name(self):
    """Name of the sensor."""
    return f"Standing Charge Data Last Retrieved Electricity ({self._serial_number}/{self._mpan})"