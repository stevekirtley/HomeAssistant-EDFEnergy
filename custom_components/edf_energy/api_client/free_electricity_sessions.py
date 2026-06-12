from datetime import datetime


class FreeElectricitySession:
  code: str
  start: datetime
  end: datetime
  source: str
  duration_in_minutes: int

  def __init__(self, code: str, start: datetime, end: datetime, source: str):
    self.code = code
    self.start = start
    self.end = end
    self.source = source
    self.duration_in_minutes = (end - start).total_seconds() / 60


class FreeElectricitySessionsResponse:
  data: list[FreeElectricitySession]

  def __init__(self, data: list[FreeElectricitySession]):
    self.data = data
