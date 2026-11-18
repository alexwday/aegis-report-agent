from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Symbol = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z0-9.]+-[A-Z]{2}$", max_length=10)]
Offset = Annotated[int, Field(ge=-20, le=0)]
SectionId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
Instruction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
RequestKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Period(StrictModel, frozen=True):
    year: int = Field(ge=1900, le=2200)
    quarter: int = Field(ge=1, le=4)

    def shifted(self, offset: int) -> "Period":
        year, quarter = divmod(self.year * 4 + self.quarter - 1 + offset, 4)
        return Period(year=year, quarter=quarter + 1)

    def __str__(self) -> str:
        return f"FY{self.year} Q{self.quarter}"


class SourceName(StrEnum):
    BENCHMARKING = "benchmarking"
    EARNINGS = "transcripts"
    SLIDES = "investor_presentation"
    SUPPLEMENT = "supplementary_financials"
    EVENTS = "event_transcripts"
    PILLAR3 = "pillar3"
    RTS = "rts"


class BenchmarkInput(StrictModel):
    source: Literal["benchmarking"] = "benchmarking"
    metric: Label
    segment: Label = "Enterprise"


class TimeScope(StrictModel):
    offsets: list[Offset] = Field(default_factory=lambda: [0], min_length=1, max_length=5)
    compare_offset: Annotated[int, Field(ge=-20, le=-1)] | None = None
    basis: Literal["vendor_fiscal_label"] = "vendor_fiscal_label"

    @model_validator(mode="after")
    def check_offsets(self) -> "TimeScope":
        if 0 not in self.offsets or len(self.offsets) != len(set(self.offsets)):
            raise ValueError("offsets must be unique and include the run quarter (0)")
        return self


class SectionSpec(StrictModel):
    id: SectionId
    title: Label
    bank: Symbol
    sources: list[BenchmarkInput] = Field(min_length=1, max_length=1)
    time: TimeScope = Field(default_factory=TimeScope)
    instruction: Instruction
    output_format: Literal["table", "table_with_note"] = "table_with_note"

    @model_validator(mode="before")
    @classmethod
    def reject_custom_stages(cls, value):
        if isinstance(value, dict) and "stages" in value:
            raise ValueError("Custom stage kinds are unsupported. Stages are generated from the section object.")
        return value


class ReportSpec(StrictModel):
    spec_version: Literal[1] = 1
    title: Label
    sections: list[SectionSpec] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def check_section_ids(self) -> "ReportSpec":
        ids = [section.id for section in self.sections]
        if len(set(ids)) != len(ids):
            raise ValueError("Section IDs must be unique")
        return self


class StageKind(StrEnum):
    RETRIEVE = "retrieve"
    CALCULATE = "calculate"
    DRAFT = "draft"
    NUMERIC_CHECK = "numeric_check"
    FORMAT = "format"


class Stage(StrictModel):
    kind: StageKind


def compile_section(section: SectionSpec) -> list[Stage]:
    kinds = [StageKind.RETRIEVE]
    if section.time.compare_offset is not None:
        kinds.append(StageKind.CALCULATE)
    if section.output_format == "table_with_note":
        kinds.append(StageKind.DRAFT)
    return [Stage(kind=kind) for kind in (*kinds, StageKind.NUMERIC_CHECK, StageKind.FORMAT)]


class DraftCreate(StrictModel):
    template: Literal["quarterly-earnings"] = "quarterly-earnings"
    bank: Symbol


class DraftPatch(StrictModel):
    revision: int = Field(ge=1)
    op: Literal["add_section", "replace_section"]
    section: SectionSpec


class DraftEdit(StrictModel):
    revision: int = Field(ge=1)


class PreviewRequest(DraftEdit):
    period: Period
    baseline_run_id: UUID | None = None
    section_id: SectionId | None = None


class RunRequest(StrictModel):
    version: int = Field(ge=1)
    period: Period
    request_key: RequestKey


class SourceProbeRequest(StrictModel):
    bank: Symbol
    period: Period
    metric: Label | None = None
    segment: Label = "Enterprise"
