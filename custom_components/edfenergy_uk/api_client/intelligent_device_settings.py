from typing import List, Optional
from datetime import time

from pydantic import BaseModel

class IntelligentDeviceSettingPreferenceSchedule(BaseModel):
  dayOfWeek: str
  time: time
  min: Optional[float] = None
  max: Optional[float] = None
  upperLimit: Optional[float] = None

class IntelligentDeviceSettingPreference(BaseModel):
  targetType: Optional[str] = None
  unit: Optional[str] = None
  mode: Optional[str] = None
  schedules: List[IntelligentDeviceSettingPreferenceSchedule] = []

class IntelligentDeviceSettingStatus(BaseModel):
  isSuspended: bool = False

class IntelligentDeviceSettings(BaseModel):
  id: str
  status: Optional[IntelligentDeviceSettingStatus] = None
  preferences: Optional[IntelligentDeviceSettingPreference] = None
