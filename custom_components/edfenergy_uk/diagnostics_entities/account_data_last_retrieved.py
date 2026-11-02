from .base import EDFEnergyBaseDataLastRetrieved

class EDFEnergyAccountDataLastRetrieved(EDFEnergyBaseDataLastRetrieved):
  """Sensor for displaying the last time the account data was last retrieved."""

  def __init__(self, hass, coordinator, account_id):
    """Init sensor."""
    self._account_id = account_id
    EDFEnergyBaseDataLastRetrieved.__init__(self, hass, coordinator)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_{self._account_id}_account_data_last_retrieved"
    
  @property
  def name(self):
    """Name of the sensor."""
    return f"Account Data Last Retrieved ({self._account_id})"