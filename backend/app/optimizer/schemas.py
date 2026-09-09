from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AvailabilityInput(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at doit être après starts_at")
        return self


class VolunteerInput(BaseModel):
    id: str
    display_name: str
    skills: set[str] = Field(default_factory=set)
    availability: list[AvailabilityInput] = Field(default_factory=list)
    preferred_roles: set[str] = Field(default_factory=set)
    latitude: float | None = None
    longitude: float | None = None


class ShiftInput(BaseModel):
    id: str
    name: str
    role_name: str
    required_skill: str | None = None
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)
    latitude: float | None = None
    longitude: float | None = None

    @model_validator(mode="after")
    def valid_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at doit être après starts_at")
        return self


class ScheduleInput(BaseModel):
    volunteers: list[VolunteerInput]
    shifts: list[ShiftInput]


class AssignmentResult(BaseModel):
    volunteer_id: str
    shift_id: str
    reason_codes: list[str]
    distance_km: float | None = None


class UncoveredRequirement(BaseModel):
    shift_id: str
    shift_name: str
    missing_positions: int
    cause: str


class ScheduleResult(BaseModel):
    status: str
    assignments: list[AssignmentResult]
    uncovered_requirements: list[UncoveredRequirement]
    score: dict[str, int]
    hard_constraint_violations: list[str] = Field(default_factory=list)
