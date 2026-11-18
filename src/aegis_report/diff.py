from typing import Literal

from .models import Period, StrictModel


class FieldChange(StrictModel):
    before: object
    after: object


class DetailChange(StrictModel):
    entity: Literal["section", "row", "claim", "note"]
    section_id: str
    key: str
    operation: Literal["added", "removed", "moved", "changed"]
    before: dict | None = None
    after: dict | None = None
    before_index: int | None = None
    after_index: int | None = None
    fields: dict[str, FieldChange] | None = None


class DiffDetails(StrictModel):
    before_periods: dict[str, list[Period]]
    after_periods: dict[str, list[Period]]
    entries: list[DetailChange]


def report_diff(baseline: dict, preview: dict) -> tuple[dict, DiffDetails]:
    before = {section["id"]: section for section in baseline["sections"]}
    after = {section["id"]: section for section in preview["sections"]}
    summary = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(key for key in before.keys() & after.keys() if compared(before[key]) != compared(after[key])),
    }
    changes = []
    for section_id in dict.fromkeys([*before, *after]):
        old, new = before.get(section_id, {}), after.get(section_id, {})
        for entity, field, identity in (
            ("row", "rows", row_key), ("claim", "claims", lambda claim: claim["key"]),
            ("note", "note", lambda note: "note"),
        ):
            old_items = old.get(field) or []
            new_items = new.get(field) or []
            if field == "note":
                old_items = [old_items] if old_items else []
                new_items = [new_items] if new_items else []
            changes.extend(compare_items(section_id, entity, old_items, new_items, identity))

    # Match section headings/order without duplicating the nested rows or claims already compared.
    for change in compare_items("", "section", headings(before), headings(after), lambda section: section["id"]):
        changes.append(change.model_copy(update={"section_id": change.key}))
    details = DiffDetails(
        before_periods={key: section.get("resolved_periods") or [baseline["period"]] for key, section in before.items()},
        after_periods={key: section.get("resolved_periods") or [preview["period"]] for key, section in after.items()},
        entries=changes,
    )
    return summary, details



def compared(section: dict) -> dict:
    return {"mode": "one_step"} | {key: value for key, value in section.items() if key != "stage_outputs"}


def headings(sections):
    return [{"id": section["id"], "title": section["title"]} for section in sections.values()]


def row_key(row):
    period = row["period"]
    return f"{row['bank']} · {row['metric']} · {row['segment']} · FY{period['year']} Q{period['quarter']}"


def compare_items(section_id, entity, before, after, identity):
    old = {identity(item): (index, item) for index, item in enumerate(before)}
    new = {identity(item): (index, item) for index, item in enumerate(after)}
    shared = old.keys() & new.keys()
    old_shared = {key: i for i, key in enumerate(key for key in old if key in shared)}
    new_shared = {key: i for i, key in enumerate(key for key in new if key in shared)}
    for key in dict.fromkeys([*old, *new]):
        old_position, old_item = old.get(key, (None, None))
        new_position, new_item = new.get(key, (None, None))
        common = {
            "entity": entity, "section_id": section_id, "key": key,
            "before": old_item, "after": new_item, "before_index": old_position, "after_index": new_position,
        }
        if old_item is None:
            yield DetailChange(operation="added", **common)
        elif new_item is None:
            yield DetailChange(operation="removed", **common)
        else:
            if old_shared[key] != new_shared[key]:
                yield DetailChange(operation="moved", **common)
            fields = {
                name: FieldChange(before=old_item.get(name), after=new_item.get(name))
                for name in sorted(old_item.keys() | new_item.keys())
                if old_item.get(name) != new_item.get(name)
            }
            if fields:
                yield DetailChange(operation="changed", fields=fields, **common)
