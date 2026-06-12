from datetime import datetime


class FreeElectricitySession:
  code: str
  start: datetime
  end: datetime
  source: str
  duration_in_minutes: int

  def __init__(
    self,
    code: str,
    start: datetime,
    end: datetime,
    source: str
  ):
    self.code = code
    self.start = start
    self.end = end
    # The originating provider for this session (e.g. "sunday_saver" or "football").
    # EDF surfaces free electricity from multiple independent sources, so we tag each
    # session so consumers can distinguish EDF-confirmed windows from externally-derived ones.
    self.source = source
    self.duration_in_minutes = (end - start).total_seconds() / 60


class FreeElectricitySessionsResponse:
  data: list[FreeElectricitySession]

  def __init__(
    self,
    data: list[FreeElectricitySession]
  ):
    self.data = data
