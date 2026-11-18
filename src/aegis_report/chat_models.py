from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from .models import (
    DraftEdit,
    Instruction,
    Label,
    PeerGroup,
    Period,
    ReportSpec,
    RequestKey,
    SectionId,
    SectionInput,
    SectionSpec,
    StrictModel,
    Symbol,
    TimeScope,
)

TurnState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TERMINAL = {"succeeded", "failed", "cancelled"}


class ConversationCreate(StrictModel):
    draft_id: UUID
    period: Period


class Conversation(ConversationCreate):
    id: UUID


class TurnCreate(StrictModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    request_key: RequestKey


class SectionPut(StrictModel):
    op: Literal["add_section", "replace_section"]
    section: SectionSpec


class SectionRemove(StrictModel):
    op: Literal["remove_section"]
    section_id: SectionId


class SectionReorder(StrictModel):
    op: Literal["reorder_sections"]
    section_ids: list[SectionId] = Field(min_length=1, max_length=6)


class SectionTarget(StrictModel):
    section_id: SectionId


class BanksEdit(SectionTarget):
    op: Literal["set_banks"]
    banks: list[Symbol] | None = Field(default=None, min_length=1, max_length=12)
    peer_group: PeerGroup | None = None

    @model_validator(mode="after")
    def one_scope(self):
        if (self.banks is None) == (self.peer_group is None):
            raise ValueError("Provide one bank list or peer group")
        return self


class TimeEdit(SectionTarget):
    op: Literal["set_time"]
    time: TimeScope


class SourcesEdit(SectionTarget):
    op: Literal["set_sources"]
    sources: list[SectionInput] = Field(min_length=1, max_length=4)


class ModeEdit(SectionTarget):
    op: Literal["set_mode"]
    mode: Literal["one_step", "staged"]


class FormatEdit(SectionTarget):
    op: Literal["set_output_format"]
    output_format: Literal["table", "table_with_note", "themes"]


class InstructionEdit(SectionTarget):
    op: Literal["set_instruction"]
    instruction: Instruction


Operation = Annotated[
    SectionPut | SectionRemove | SectionReorder | BanksEdit | TimeEdit | SourcesEdit | ModeEdit |
    FormatEdit | InstructionEdit, Field(discriminator="op"),
]


class PatchOperations(StrictModel):
    operations: list[Operation] = Field(min_length=1, max_length=6)


class ChatProposal(PatchOperations, DraftEdit):
    pass


class TurnResult(StrictModel):
    id: UUID
    conversation_id: UUID
    state: TurnState
    message: str | None = None
    proposal: ChatProposal | None = None
    preview_id: UUID | None = None
    applied_revision: int | None = None
    error_code: str | None = None
    last_sequence: int


class ResolveScope(StrictModel):
    bank_labels: list[Label] = Field(default_factory=list, max_length=12)
    peer_group: PeerGroup | None = None
    time: TimeScope = Field(default_factory=TimeScope)


class SourceSelection(StrictModel):
    bank: Label
    period: Period | None = None
    selector: SectionInput


class StartPreview(StrictModel):
    section_id: SectionId | None = None
    stop_after: Literal["gather"] | None = None
    compare_saved: bool = False


class EmptyArgs(StrictModel):
    pass


TOOL_MODELS = {
    "resolve_scope": (ResolveScope, "Resolve bank aliases, a peer group and fiscal periods."),
    "inspect_coverage": (SourceSelection, "Probe availability of one bank, source selector and fiscal period."),
    "search_evidence": (SourceSelection, "Read at most three bounded, untrusted evidence records."),
    "read_draft": (EmptyArgs, "Read the conversation's bound draft at its current revision."),
    "propose_patch": (PatchOperations, "Prepare typed edits for explicit user acceptance."),
    "start_preview": (StartPreview, "Queue a preview of the current draft or this turn's proposal."),
    "explain_diff": (EmptyArgs, "Read the most recent preview's structured diff in this conversation."),
}


def apply_operations(spec: ReportSpec, operations: list[Operation]) -> ReportSpec:
    sections = {item.id: item.model_dump(mode="json") for item in spec.sections}
    for item in operations:
        if isinstance(item, SectionPut):
            target = item.section.id
            if (target in sections) != (item.op == "replace_section"):
                raise ValueError("section_already_exists" if target in sections else "section_not_found")
            sections[target] = item.section.model_dump(mode="json")
        elif isinstance(item, SectionReorder):
            if len(item.section_ids) != len(sections) or set(item.section_ids) != set(sections):
                raise ValueError("reorder_must_list_every_section_once")
            sections = {key: sections[key] for key in item.section_ids}
        else:
            target = item.section_id
            if target not in sections:
                raise ValueError("section_not_found")
            if isinstance(item, SectionRemove):
                del sections[target]
            elif isinstance(item, BanksEdit):
                sections[target].update(bank=None, banks=item.banks, peer_group=item.peer_group)
            else:
                sections[target].update(item.model_dump(mode="json", exclude={"op", "section_id"}))
    return ReportSpec.model_validate(spec.model_dump(mode="json") | {"sections": list(sections.values())})
