"""Read-only slides and RTS evaluation. Keep excerpts local."""
import argparse
import os

import httpx
from eval_support import evaluation_gateway, print_claims

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
    parser.add_argument("--source", choices=("both", "slides", "rts"), default="both")
    parser.add_argument("--claims", action="store_true")
    parser.add_argument("--instruction", default="Highlight substantive financial drivers and quantitative changes.")
    parser.add_argument("--gateway", choices=("stub", "real"), default="stub")
    parser.add_argument("--credentials-hook", metavar="MODULE:FUNCTION")
    args = parser.parse_args()
    if not args.topic and not args.term:
        parser.error("Provide a --topic or one or more --term arguments.")
    period = Period(year=args.year, quarter=args.quarter)
    dsn = os.environ.get("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to a read-only DSN.")
    with httpx.Client(trust_env=False) as client, connect(dsn, source=True) as conn:
        try:
            gateway = evaluation_gateway(args.gateway, client, args.credentials_hook)
        except ValueError as exc:
            parser.error(str(exc))
        bank = BankCatalog().resolve(conn, args.bank)
        query = Scope(bank, period, topics=tuple(args.topic), terms=tuple(args.term))
        terms = search_terms(query.topics, query.terms)
        vector = gateway.embed(", ".join(terms)) if args.gateway == "real" else None
        print(f"{bank.symbol} · {period} · {args.gateway} gateway · lexical terms: {', '.join(terms)}")
        for label, adapter in (("slides", SlideSource(0.35)), ("RTS", RtsSource(0.35))):
            if args.source not in ("both", label.casefold()):
                continue
            probe = adapter.probe(conn, query)
            hits = adapter.search(conn, query, vector) if probe.state == "ready" else []
            print(f"{label}: {probe.state}, {len(hits)} hits")
            for index, hit in enumerate(hits, 1):
                words = " ".join(hit.text.split())
                excerpt = words[:220]
                distance = f", vector distance {hit.distance:.5f}" if hit.distance is not None else ""
                print(f"  {index}. {hit.citation.locator} (lexical score {hit.relevance:.5f}{distance})")
                print(f"     {excerpt}" + ("…" if len(words) > 220 else ""))
            if args.claims:
                print_claims(hits, args.instruction, gateway)


if __name__ == "__main__":
    main()
