from .base import EDFEnergyBaseDataLastRetrieved
from ..gas.base import EDFEnergyGasSensor

class EDFEnergyGasCurrentRatesDataLastRetrieved(EDFEnergyGasSensor, EDFEnergyBaseDataLastRetrieved):
  """Sensor for displaying the last time the current rates data was last retrieved."""

  def __init__(self, hass, coordinator, meter, point):
    """Init sensor."""
    self._mprn = point["mprn"]
    self._serial_number = meter["serial_number"]
    EDFEnergyGasSensor.__init__(self, hass, meter, point)
    EDFEnergyBaseDataLastRetrieved.__init__(self, hass, coordinator)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_gas_{self._serial_number}_{self._mprn}_rates_data_last_retrieved"
    
  @property
  def name(self):
    """Name of the sensor."""
    return f"Rates Data Last Retrieved Gas ({self._serial_number}/{self._mprn})"