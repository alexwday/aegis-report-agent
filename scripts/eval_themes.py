"""Read-only evidence evaluation. Output remains on the reviewer's machine."""
import argparse
import os

from aegis_report.claims import draft_themes, shortlist_passages
from aegis_report.db import connect
from aegis_report.gateway import StubGateway
from aegis_report.models import Period
from aegis_report.sources import BankCatalog, EarningsSource, Scope


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--instruction", default="Highlight substantive financial drivers and quantitative changes.")
    args = parser.parse_args()
    period = Period(year=args.year, quarter=args.quarter)
    dsn = os.environ.get("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to a read-only DSN.")
    with connect(dsn, source=True) as conn:
        bank = BankCatalog().resolve(conn, args.bank)
        query = Scope(bank, period, topics=(args.topic,))
        adapter = EarningsSource()
        probe = adapter.probe(conn, query)
        print(f"{bank.symbol} · {period} · {args.topic} · {probe.state} ({probe.generation or 'no generation'})")
        if probe.state != "ready":
            print(probe.reason)
            return
        passages = adapter.search(conn, query)
    claims = draft_themes(args.instruction, shortlist_passages(passages, args.instruction, semantic=False), StubGateway())
    print(f"{len(passages)} matched passages; {len(claims)} claims (lexical evaluation)")
    for claim in claims:
        print(f"[{claim.method}] {claim.text}")
        for citation in claim.citations:
            print(f"  {citation.locator}")
    if not claims:
        print("No evidence passed claim selection.")


if __name__ == "__main__":
    main()
