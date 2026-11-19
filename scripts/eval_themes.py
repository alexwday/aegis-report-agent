"""Read-only evidence evaluation. Output remains on the reviewer's machine."""
import argparse
import os

from eval_support import evaluation_client, evaluation_gateway, print_claims

from aegis_report.claims import shortlist_passages
from aegis_report.db import connect
from aegis_report.gateway import GatewayError
from aegis_report.models import Period
from aegis_report.sources import BankCatalog, EarningsSource, Scope


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--instruction", default="Highlight substantive financial drivers and quantitative changes.")
    parser.add_argument("--gateway", choices=("stub", "real"), default="stub")
    parser.add_argument("--credentials-hook", metavar="MODULE:FUNCTION")
    args = parser.parse_args()
    period = Period(year=args.year, quarter=args.quarter)
    dsn = os.environ.get("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to a read-only DSN.")
    with evaluation_client(args.gateway) as client, connect(dsn, source=True) as conn:
        try:
            gateway = evaluation_gateway(args.gateway, client, args.credentials_hook)
        except ValueError as exc:
            parser.error(str(exc))
        bank = BankCatalog().resolve(conn, args.bank)
        query = Scope(bank, period, topics=(args.topic,), terms=tuple(args.term))
        adapter = EarningsSource()
        probe = adapter.probe(conn, query)
        print(f"{bank.symbol} · {period} · {args.topic} · {probe.state} ({probe.generation or 'no generation'})")
        if probe.state != "ready":
            print(probe.reason)
            return
        try:
            vector = gateway.embed(args.topic) if args.gateway == "real" else None
            passages = adapter.search(conn, query, vector)
            print(f"{len(passages)} matched passages ({args.gateway} gateway)")
            shortlist = shortlist_passages(passages, args.instruction, semantic=gateway.supports_semantic_ranking)
            print_claims(shortlist, args.instruction, gateway)
        except GatewayError as exc:
            print(f"FAIL {bank.symbol} {period}: {exc}")
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
