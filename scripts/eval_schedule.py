"""Probe one schedule period in the exact source path used by the poller without writing."""
import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aegis_report.config import Settings
from aegis_report.db import connect
from aegis_report.models import Period, ReportSpec
from aegis_report.scheduler import calendar_ready_at, inspect_schedule
from aegis_report.sources import BankCatalog, SourceIssue
from aegis_report.templates import SYSTEM_TEMPLATES, build_system_template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--spec", type=Path)
    selection.add_argument("--template", choices=sorted(SYSTEM_TEMPLATES))
    banks = parser.add_mutually_exclusive_group()
    banks.add_argument("--bank", action="append")
    banks.add_argument("--peer-group", choices=("big-6-canadian-banks",))
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--timezone", default="America/Toronto")
    args = parser.parse_args()
    if (args.template and not (args.bank or args.peer_group)) or (args.spec and (args.bank or args.peer_group)):
        parser.error("Use --spec alone, or combine --template with --bank or --peer-group.")
    try:
        ZoneInfo(args.timezone)
    except (ValueError, ZoneInfoNotFoundError):
        parser.error("Choose a valid IANA timezone.")
    dsn = os.getenv("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to an approved read-only source DSN.")
    catalog = BankCatalog()
    if args.spec:
        spec = ReportSpec.model_validate_json(args.spec.read_text())
    else:
        try:
            with connect(dsn, source=True) as conn:
                available = catalog.list(conn)
                symbols = [catalog.match(available, label).symbol for label in args.bank or []]
        except SourceIssue as exc:
            parser.error(exc.reason)
        spec = build_system_template(args.template, symbols[0] if symbols else "RY-CA")
        scope = {"bank": None, "banks": symbols or None, "peer_group": args.peer_group}
        spec = ReportSpec.model_validate(spec.model_dump() | {
            "sections": [section.model_dump() | scope for section in spec.sections],
        })
    settings = Settings(report_dsn="", source_dsn=dsn, owner_secret=b"")
    period = Period(year=args.year, quarter=args.quarter)
    readiness = inspect_schedule(settings, spec, period, {}, datetime.now(UTC), settings.quiet_seconds)
    earliest = calendar_ready_at(spec, period, args.timezone)
    basis = f"calendar floor {earliest.isoformat()}" if earliest else "physical readiness only"
    print(f"{period} · {basis}")
    for item in readiness.values():
        period_text = Period.model_validate(item["period"])
        flag = "required" if item["required"] else "optional"
        print(f"{item['section_id']} · {item['bank']} · {item['source']} · {period_text} · "
              f"{flag} · {item['state']}" + (f" ({item['reason']})" if item["reason"] else ""))
    print(json.dumps({
        "checked": len(readiness),
        "physically_ready": sum(entry["state"] == "ready" for entry in readiness.values()),
        "stable": sum(entry["stable"] for entry in readiness.values()),
        "quiet_period": "A second observation is required.",
    }))


if __name__ == "__main__":
    main()
