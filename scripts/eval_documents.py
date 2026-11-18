"""Read-only lexical slides and RTS evaluation. Keep excerpts local."""
import argparse
import os

from aegis_report.db import connect
from aegis_report.documents import RtsSource, SlideSource
from aegis_report.models import Period
from aegis_report.sources import BankCatalog, Scope
from aegis_report.topics import search_terms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--term", action="append", default=[])
    args = parser.parse_args()
    if not args.topic and not args.term:
        parser.error("Provide a --topic or one or more --term arguments.")
    period = Period(year=args.year, quarter=args.quarter)
    dsn = os.environ.get("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to a read-only DSN.")
    with connect(dsn, source=True) as conn:
        bank = BankCatalog().resolve(conn, args.bank)
        query = Scope(bank, period, topics=tuple(args.topic), terms=tuple(args.term))
        print(f"{bank.symbol} · {period} · lexical terms: {', '.join(search_terms(query.topics, query.terms))}")
        for label, adapter in (("slides", SlideSource(0.35)), ("RTS", RtsSource(0.35))):
            probe = adapter.probe(conn, query)
            hits = adapter.search(conn, query) if probe.state == "ready" else []
            print(f"{label}: {probe.state}, {len(hits)} hits")
            for index, hit in enumerate(hits, 1):
                words = " ".join(hit.text.split())
                excerpt = words[:220]
                print(f"  {index}. {hit.citation.locator} (lexical rank {hit.relevance:.5f})")
                print(f"     {excerpt}" + ("…" if len(words) > 220 else ""))


if __name__ == "__main__":
    main()
