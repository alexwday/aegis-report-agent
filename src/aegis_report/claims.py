import json
import re
from collections import defaultdict
from dataclasses import dataclass

from pydantic import Field, ValidationError

from .gateway import GatewayError, ModelGateway
from .models import Label, StrictModel
from .sources import Citation, Passage
from .topics import lexical_hits, search_terms

INSTRUCTION_TEXT = re.compile(
    r"(?:ignore|override|disregard).{0,45}(?:instructions|prompt|rules)"
    r"|\b(?:system prompt|developer message|prompt injection|reveal (?:the )?token)\b"
    r"|<\s*/?\s*(?:system|assistant|script)\b",
    re.IGNORECASE,
)


PLEASANTRY = re.compile(
    r"^(?:thank(?:s| you)\b|(?:very )?good (?:morning|afternoon|evening)\b|"
    r"hello\b|welcome\b|operator\b|(?:our |the )?next question\b|"
    r"(?:i(?:'ll| will)|let me|i would like to) (?:now )?(?:turn|hand|pass)\b|"
    r"please (?:go ahead|stand by|begin)\b|over to you\b|(?:hi|hey) there\b)", re.IGNORECASE,
)
INTRODUCTION = re.compile(r"^(?:(?:this is|i am|i'm|my name is) )?(?:[A-Z][a-z'’-]+\s+){1,3}[A-Z][a-z'’-]+[.!:]?$")
SPEAKER_TAG = re.compile(r"^\s*\[([^\]\n]{1,160})\]\s*")
WORD = re.compile(r"\b[\w'-]+\b")
FOCUS_STOP = {"about", "from", "highlight", "show", "include", "identify", "quote", "claims", "topic", "the", "for",
              "report", "with", "cited", "evidence", "and", "financial", "context", "recent"}
MAX_CANDIDATES = 50
MAX_PROMPT_BYTES = 16_000  # UTF-8 byte ceiling also bounds the model's text token count.


class ProposedClaim(StrictModel):
    topic: Label
    text: str = Field(min_length=1, max_length=320)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)


class ThemeClaim(StrictModel):
    key: str
    topic: str
    text: str
    evidence_ids: list[str]
    citations: list[Citation]
    method: str


@dataclass(frozen=True)
class Candidate:
    topic: str
    text: str
    citation: Citation
    score: float
    speaker: str

    def as_prompt_data(self) -> dict[str, str]:
        return {"id": self.citation.id, "topic": self.topic, "text": self.text, "source": self.citation.source}


def passage_candidates(passage: Passage, focus: set[str], semantic: bool):
    if INSTRUCTION_TEXT.search(passage.text):
        return
    tag = SPEAKER_TAG.match(passage.text)
    speaker = tag[1].split(",", 1)[0].casefold().strip() if tag else passage.speaker or passage.citation.id
    if speaker == "operator" or speaker.startswith("operator ") or (
        tag and any(role.strip().casefold() == "operator" for role in tag[1].split(",")[1:])
    ):
        return
    body = passage.text[tag.end():] if tag else passage.text
    if not tag and "\n" in body:
        first_line, remaining = body.split("\n", 1)
        heading = first_line.strip(" #*:[]")
        if heading.lower() == "operator":
            return
        if INTRODUCTION.fullmatch(heading) and len(heading.split()) <= 4:
            speaker, body = heading.casefold(), remaining
    topic_terms = {topic: search_terms((topic,)) for topic in passage.topics}
    vector_bonus = 2 * max(0, 1 - passage.distance) if semantic and passage.distance is not None else 0
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        sentence = " ".join(sentence.split())
        words = WORD.findall(sentence.casefold())
        if (
            not (20 <= len(sentence) <= 320 and len(words) >= 4 and sentence.endswith((".", "!")))
            or PLEASANTRY.match(sentence) or INTRODUCTION.fullmatch(sentence)
        ):
            continue
        intent = min(4, len(focus.intersection(words)))
        numeric = 1.5 if re.search(r"\d", sentence) else 0
        for topic, terms in topic_terms.items():
            score = 4 * lexical_hits(sentence, terms) + intent + numeric + vector_bonus
            yield Candidate(topic, sentence, passage.citation, score, speaker)


def focus_terms(instruction: str) -> set[str]:
    return {word for word in WORD.findall(instruction.casefold()) if len(word) >= 3} - FOCUS_STOP


def candidates_for(passages: list[Passage], instruction: str = "", *, semantic: bool = False) -> list[Candidate]:
    focus = focus_terms(instruction)
    unique = {}
    for passage in passages:
        for item in passage_candidates(passage, focus, semantic):
            unique.setdefault((item.topic, item.text, item.citation.id), item)
    # Rerank with a repetition penalty so multiple blocks and speakers contribute.
    sorted_candidates = sorted(unique.values(), key=lambda item: (-item.score, item.citation.id, item.text, item.topic))
    per_block = defaultdict(int)
    remaining = []
    for item in sorted_candidates:
        if per_block[item.citation.id] < 12:
            remaining.append(item)
            per_block[item.citation.id] += 1
    output, budget = [], MAX_PROMPT_BYTES
    blocks, speakers, groups = defaultdict(int), defaultdict(int), defaultdict(int)
    while remaining and len(output) < MAX_CANDIDATES:
        item = max(remaining, key=lambda candidate: (
            candidate.score - 3 * blocks[candidate.citation.id] - 2 * speakers[candidate.speaker]
            - groups[(candidate.topic.casefold(), candidate.citation.source)]
        ))
        remaining.remove(item)
        if blocks[item.citation.id] >= 5 or speakers[item.speaker] >= 10:
            continue
        cost = len(json.dumps(item.as_prompt_data(), ensure_ascii=False).encode("utf-8")) + 4
        if cost <= budget:
            output.append(item)
            budget -= cost
            blocks[item.citation.id] += 1
            speakers[item.speaker] += 1
            groups[(item.topic.casefold(), item.citation.source)] += 1
    return output


def shortlist_passages(passages: list[Passage], instruction: str, *, semantic: bool) -> list[Passage]:
    if len(passages) <= 40:
        return passages
    # Preserve relevance and diversity before assembling the report-wide evidence list.
    ranked_ids = dict.fromkeys(item.citation.id for item in candidates_for(passages, instruction, semantic=semantic))
    by_id = {item.citation.id: item for item in passages}
    return [by_id[id_] for id_ in list(ranked_ids)[:40]]


def draft_themes(instruction: str, passages: list[Passage], gateway: ModelGateway) -> list[ThemeClaim]:
    candidates = candidates_for(
        passages, instruction, semantic=getattr(gateway, "supports_semantic_ranking", False),
    )
    if not candidates:
        return []
    allowed = {(item.topic.casefold(), item.text, item.citation.id): item for item in candidates}
    accepted = []
    try:
        payload = gateway.draft_claims(instruction, [item.as_prompt_data() for item in candidates])
    except GatewayError:
        payload = None
    claims = payload.get("claims") if isinstance(payload, dict) and set(payload) == {"claims"} else None
    if isinstance(claims, list) and len(claims) <= 6:
        for raw in claims:
            try:
                proposed = ProposedClaim.model_validate(raw)
            except ValidationError:
                continue
            text = " ".join(proposed.text.split())
            matches = [allowed.get((proposed.topic.casefold(), text, id_)) for id_ in proposed.evidence_ids]
            if all(matches):
                accepted.append((matches[0].topic, text, [match.citation for match in matches], "verified_quote"))
    if not accepted:
        seen = set()
        for item in candidates:
            group = (item.topic.casefold(), item.citation.source)
            if group not in seen:
                accepted.append((item.topic, item.text, [item.citation], "fallback_quote"))
                seen.add(group)

    grouped = {}
    for topic, text, citations, method in accepted:
        key = (topic.casefold(), text)
        _, refs, _ = grouped.setdefault(key, (topic, {}, method))
        refs.update((citation.id, citation) for citation in citations)

    slot = defaultdict(int)
    output = []
    for (folded, text), (topic, refs, method) in list(grouped.items())[:6]:
        slot[folded] += 1
        output.append(ThemeClaim(
            key=f"{folded}:{slot[folded]}", topic=topic, text=text,
            evidence_ids=list(refs), citations=list(refs.values()), method=method,
        ))
    return output
