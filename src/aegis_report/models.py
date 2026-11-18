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
    required: bool = True


class EarningsInput(StrictModel):
    source: Literal["transcripts"]
    topics: list[Label] = Field(min_length=1, max_length=4)
    vector: bool = False
    required: bool = True


class DocumentInput(StrictModel):
    source: Literal["investor_presentation", "rts"]
    topic: Label
    vector: bool = False
    required: bool = True


SectionInput = BenchmarkInput | EarningsInput | DocumentInput


class PeriodPreset(StrictModel):
    kind: Literal["trailing_quarters", "same_quarter_years", "quarter_sequence", "year_sequence"]
    count: int = Field(ge=1, le=12)

    def offsets(self) -> list[int]:
        step = 4 if self.kind in ("same_quarter_years", "year_sequence") else 1
        offsets = [-index * step for index in range(self.count)]
        return offsets[::-1] if self.kind in ("quarter_sequence", "year_sequence") else offsets


class TimeScope(StrictModel):
    offsets: list[Offset] | None = Field(default=None, min_length=1, max_length=12)
    compare_offset: Annotated[int, Field(ge=-20, le=-1)] | None = None
    preset: PeriodPreset | None = None
    compare: Literal["prior_quarter", "prior_year"] | None = None
    basis: Literal["vendor_fiscal_label"] = "vendor_fiscal_label"

    @model_validator(mode="after")
    def check_offsets(self) -> "TimeScope":
        if self.offsets is not None:
            if self.preset is not None or 0 not in self.offsets or len(self.offsets) != len(set(self.offsets)):
                raise ValueError("Explicit offsets must be unique, include zero, and have no preset")
        if self.preset is not None and min(self.preset.offsets()) < -20:
            raise ValueError("A preset cannot extend beyond 20 prior fiscal quarters")
        if self.compare is not None and self.compare_offset is not None:
            raise ValueError("Choose a named comparison or an explicit comparison offset")
        if len(self.resolved_offsets()) > 12:
            raise ValueError("A section may resolve at most 12 fiscal periods including comparison")
        return self

    def comparison_offset(self) -> int | None:
        return {"prior_quarter": -1, "prior_year": -4}.get(self.compare, self.compare_offset)

    def resolved_offsets(self) -> list[int]:
        offsets = self.preset.offsets() if self.preset else sorted(self.offsets or [0], reverse=True)
        compare = self.comparison_offset()
        return [*offsets, compare] if compare is not None and compare not in offsets else offsets


class SectionSpec(StrictModel):
    id: SectionId
    title: Label
    bank: Symbol
    sources: list[SectionInput] = Field(min_length=1, max_length=4)
    kind: Literal["benchmark", "themes"] = "benchmark"
    time: TimeScope = Field(default_factory=TimeScope)
    instruction: Instruction
    output_format: Literal["table", "table_with_note", "themes"] = "table_with_note"

    @model_validator(mode="before")
    @classmethod
    def reject_custom_stages(cls, value):
        if isinstance(value, dict) and "stages" in value:
            raise ValueError("Custom stage kinds are unsupported. Stages are generated from the section object.")
        return value

    @model_validator(mode="after")
    def check_sources(self) -> "SectionSpec":
        if self.kind == "themes":
            if not any(isinstance(item, EarningsInput) for item in self.sources):
                raise ValueError("Themes require at least one earnings transcript source")
            if self.output_format != "themes":
                raise ValueError("Themes sections use the themes output format")
        elif self.output_format == "themes" or not all(isinstance(item, BenchmarkInput) for item in self.sources):
            raise ValueError("Benchmark sections use benchmark sources and a table output format")
        identities = [source_identity(item) for item in self.sources]
        if len(set(identities)) != len(identities):
            raise ValueError("Source selections in a section must be distinct")
        if len(self.sources) * len(self.time.resolved_offsets()) > 24:
            raise ValueError("A section may resolve at most 24 source-period scopes")
        return self


def source_identity(item: SectionInput) -> tuple[str, ...]:
    if isinstance(item, BenchmarkInput):
        return (item.source, item.metric, item.segment)
    if isinstance(item, EarningsInput):
        return (item.source, *sorted({topic.casefold() for topic in item.topics}))
    return (item.source, item.topic.casefold())


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
    if section.time.comparison_offset() is not None and any(isinstance(item, BenchmarkInput) for item in section.sources):
        kinds.append(StageKind.CALCULATE)
    if section.output_format != "table":
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
