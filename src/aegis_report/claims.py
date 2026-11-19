import json
import re
from collections import defaultdict
from dataclasses import dataclass

from pydantic import Field, ValidationError

from .gateway import GatewayError, ModelGateway
from .models import Label, SourceName, StrictModel
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
DOCUMENT_SOURCE = {SourceName.SLIDES, SourceName.RTS}
DEFINITION_REQUEST = re.compile(r"\b(?:define|definitions?|what is|what does .{1,60} mean|meaning of|glossary)\b", re.I)
REFERENCE_HEADING = re.compile(
    r"(?:^|[>:/–—-] ?)(?:[ #*_]*)(?:glossary|definitions?|endnotes?|footnotes?|notes(?: to|$)|"
    r"non.gaap|legal|forward.looking|disclaimer)\b", re.I,
)
DEFINITION_UNIT = re.compile(
    r"\b(?:is|are) (?:defined|calculated|measured|computed) (?:as|by)\b|\brefers to\b|"
    r"^(?-i:[A-Z][A-Z0-9 /()-]{1,30}):|^\s*(?:[*†‡]+|\[\d+\]|\(\d+\))\s+", re.I,
)
CONTINUATION = re.compile(
    r"^(?:and|or|but|nor|yet|which|that|where|while|with|as well as|including|resulting in|due to)\b", re.I
)
FRAGMENT_START = re.compile(r"^[A-Z][a-z-]+, (?:which|where|who|while)\b")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$€£“])")
ABBREVIATION = re.compile(
    r"(?:\b[a-z](?:\.[a-z])+|\b(?:inc|corp|ltd|co|no|nos|approx|vs|etc|mr|mrs|ms|dr|st|fig|jan|feb|mar|apr|"
    r"jun|jul|aug|sep|sept|oct|nov|dec))\.$", re.I,
)
BULLET = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+•▪◦‣–—]\s+|\d{1,2}[.)]\s+)")
FOOTNOTE = re.compile(r"<sup[^>]*>\s*\d+\s*</sup>|[⁰¹²³⁴⁵⁶⁷⁸⁹]+|(?:\*{1,3}|_{1,3})?\[\d{1,2}\]", re.I)
FUSED_YEAR = re.compile(
    r"(\b(?:fiscal(?: year)?\s+|FY)(?:19|20|21)\d{2})(?:[1-9]\d?(?=\W|$)|"
    r"[ \t]+[1-9]\d?(?=[,.;:)]|$|\s+(?:was|at|rose|increased)\b))", re.I,
)
AMBIGUOUS_YEAR = re.compile(r"\b(?:fiscal(?: year)?\s+|FY)(?:19|20|21)\d{2}\d+", re.I)
QUANTIFIED = re.compile(r"\d[\d.,]*\s*(?:%|bps?\b|basis points?\b|million\b|billion\b|[×x]\b)|[$€£]\s*\d", re.I)
SUBSTANTIVE = re.compile(
    r"\b(?:rose|fell|grew|declined|increas\w*|decreas\w*|improv\w*|expand\w*|"
    r"contract\w*|stable|held|driven|benefit\w*|reflect\w*|offset|lower|higher|unchanged)\b", re.I,
)

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
    banks: list[str] | None = None
    source_text: str | None = None


@dataclass(frozen=True)
class Candidate:
    topic: str
    text: str
    citation: Citation
    score: float
    speaker: str

    def as_prompt_data(self) -> dict[str, str]:
        return {"id": self.citation.id, "topic": self.topic, "text": self.text, "source": self.citation.source}


def sentences(text: str, *, maxsplit: int = -1) -> list[str]:
    start = 0
    output = []
    for split in SENTENCE_BREAK.finditer(text):
        if ABBREVIATION.search(text[start:split.start()]) or len(output) == maxsplit:
            continue
        output.append(text[start:split.start()])
        start = split.end()
    return [*output, text[start:]]


def display_claim(text: str) -> str:
    text = re.sub(r"\*{1,3}\(\d{1,2}\)", "", text)
    text = FOOTNOTE.sub("", text)
    text = re.sub(r"(?<!\w)\*{1,3}([^*]+)\*{1,3}(?!\w)", r"\1", text)
    return FUSED_YEAR.sub(r"\1", text)


def slide_lines(body: str):
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        marker = BULLET.match(raw)
        text = raw[marker.end():].strip() if marker else raw.strip()
        index += 1
        if text.endswith(":") and not text.startswith(("#", "|", "<")):
            children = []
            for following in lines[index:]:
                child = BULLET.match(following)
                if not child:
                    break
                label = following[child.end():].strip()
                if not label or label.endswith(":") or (
                    marker and len(child["indent"]) <= len(marker["indent"]) and complete_claim(label)
                ):
                    break
                children.append(label.removesuffix(".").rstrip(" ;"))
            combined = text + " " + "; ".join(children) + "."
            if children and len(combined) <= 320:
                index += len(children)
                yield combined
                continue
        yield text


def complete_claim(text: str) -> bool:
    text = display_claim(text)
    if not 24 <= len(text) <= 320 or len(WORD.findall(text)) < 5 or not text.endswith((".", "!")):
        return False
    if text.endswith(("...", "….", "..")) or ABBREVIATION.search(text) or AMBIGUOUS_YEAR.search(text):
        return False
    beginning = text.lstrip("\"'“‘($€£")
    return bool(
        beginning and (beginning[0].isupper() or beginning[0].isdigit())
        and not CONTINUATION.match(beginning) and not FRAGMENT_START.match(beginning)
    )


def document_units(passage: Passage, allow_definitions: bool):
    if not allow_definitions and (
        REFERENCE_HEADING.search(passage.heading or "")
        or REFERENCE_HEADING.search(passage.text.lstrip().split("\n", 1)[0].strip())
    ):
        return
    body = re.sub(r"<!--.*?-->", "", passage.text, flags=re.S)
    units = []
    for line in slide_lines(body) if passage.citation.source is SourceName.SLIDES else re.split(r"\n[ \t]*\n", body):
        line = line.strip()
        if not allow_definitions and REFERENCE_HEADING.search(line.lstrip("# ")):
            break
        bullet = BULLET.match(line)
        line = line[bullet.end():] if bullet else line
        if line.startswith(("#", "|", "<")):
            line = "\n".join(piece for piece in line.splitlines()
                             if not piece.lstrip().startswith(("#", "|", "<")))
        units.extend(sentences(line))

    following = passage.following
    if units and following and not INSTRUCTION_TEXT.search(following.text):
        tail = " ".join(units[-1].split())
        continuation = " ".join(sentences(following.text.strip(), maxsplit=1)[0].split())
        if tail and continuation and not continuation.startswith(("#", "<", "|", "•")) and (
            not tail.endswith((".", "!", "?")) and (
                tail.endswith((",", ";")) or CONTINUATION.match(continuation) or continuation[0].islower()
            )
        ):
            units[-1] = tail + " " + continuation
            joined = len(units) - 1
        else:
            joined = None
    else:
        joined = None
    citation = passage.citation
    for index, part in enumerate(units):
        if index == 0 and passage.begins_mid_sentence:
            continue
        text = " ".join(part.strip().split())
        quantified = bool(QUANTIFIED.search(text))
        definition = bool(DEFINITION_UNIT.search(text))
        if complete_claim(text) and (allow_definitions or not definition):
            if quantified or SUBSTANTIVE.search(text) or (allow_definitions and definition):
                yield text, int(quantified), following.citation if index == joined else citation


def document_candidates(passage: Passage, instruction: str, focus: set[str], semantic: bool):
    vector_bonus = 2 * max(0, 1 - passage.distance) if semantic and passage.distance is not None else 0
    for text, quantified, citation in document_units(passage, bool(DEFINITION_REQUEST.search(instruction))):
        intent = min(4, len(focus.intersection(WORD.findall(text.casefold()))))
        for topic in passage.topics:
            hits = lexical_hits(text, search_terms((topic,), passage.terms))
            if hits or (intent and quantified):
                yield Candidate(topic, text, citation,
                                4 * hits + intent + 5 * quantified + min(4, (passage.relevance or 0) / 4) + vector_bonus,
                                citation.id)


def passage_candidates(passage: Passage, instruction: str, focus: set[str], semantic: bool):
    if INSTRUCTION_TEXT.search(passage.text):
        return
    if passage.citation.source in DOCUMENT_SOURCE:
        yield from document_candidates(passage, instruction, focus, semantic)
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
    topic_terms = {
        topic: tuple(term for term in search_terms((topic,), passage.terms)
                     if term not in ("margin", "allowance") or term in passage.terms)
        for topic in passage.topics
    }
    vector_bonus = 2 * max(0, 1 - passage.distance) if semantic and passage.distance is not None else 0
    for sentence in (unit for paragraph in re.split(r"\n+", body) for unit in sentences(paragraph)):
        sentence = " ".join(sentence.split())
        words = WORD.findall(sentence.casefold())
        if (
            not complete_claim(sentence) and not (
                len(words) == 4 and 20 <= len(sentence) <= 320 and sentence.endswith(".")
                and not ABBREVIATION.search(sentence) and sentence[0].isupper()
            )
            or PLEASANTRY.match(sentence) or INTRODUCTION.fullmatch(sentence)
        ):
            continue
        intent = min(4, len(focus.intersection(words)))
        numeric = 1.5 if re.search(r"\d", sentence) else 0
        for topic, terms in topic_terms.items():
            matches = lexical_hits(sentence, terms)
            if matches:
                score = 4 * matches + intent + numeric + vector_bonus
                yield Candidate(topic, sentence, passage.citation, score, speaker)


def focus_terms(instruction: str) -> set[str]:
    return {word for word in WORD.findall(instruction.casefold()) if len(word) >= 3} - FOCUS_STOP


def candidates_for(passages: list[Passage], instruction: str = "", *, semantic: bool = False) -> list[Candidate]:
    focus = focus_terms(instruction)
    unique = {}
    for passage in passages:
        for item in passage_candidates(passage, instruction, focus, semantic):
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
    by_id = {item.citation.id: item for item in passages}
    by_id.update((item.following.citation.id, item) for item in passages if item.following)
    ranked = {}
    for candidate in candidates_for(passages, instruction, semantic=semantic):
        passage = by_id[candidate.citation.id]
        ranked.setdefault(passage.citation.id, passage)
    return list(ranked.values())[:40]


def draft_themes(
    instruction: str, passages: list[Passage], gateway: ModelGateway, *, candidates: list[Candidate] | None = None,
    strict_gateway: bool = False,
) -> list[ThemeClaim]:
    if candidates is None:
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
        if strict_gateway:
            raise
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
        display = display_claim(text)
        output.append(ThemeClaim(
            key=f"{folded}:{slot[folded]}", topic=topic, text=display,
            source_text=text if display != text else None,
            evidence_ids=list(refs), citations=list(refs.values()), method=method,
        ))
    return output
