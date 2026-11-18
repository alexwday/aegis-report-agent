"""Evaluate peer direction and missing banks on a read-only source connection."""
import argparse
import json
import os

from aegis_report.db import connect
from aegis_report.models import BIG_SIX, BenchmarkInput, Period, SectionSpec
from aegis_report.peers import peer_statistics
from aegis_report.sources import BankCatalog, BenchmarkingSource, Scope, SourceIssue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarter", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--metric", required=True)
    parser.add_argument("--segment", default="Enterprise")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--peer-group", choices=["big-6-canadian-banks"])
    group.add_argument("--bank", action="append")
    args = parser.parse_args()
    dsn = os.getenv("SOURCE_DATABASE_URL")
    if not dsn:
        parser.error("Set SOURCE_DATABASE_URL to an approved read-only DSN.")
    currencies = json.loads(os.getenv("CURRENCY_MAP", '{"CA":"CAD","US":"USD"}'))
    period = Period(year=args.year, quarter=args.quarter)
    selection = BenchmarkInput(metric=args.metric, segment=args.segment)
    catalog = BankCatalog()
    adapter = BenchmarkingSource(currencies)
    with connect(dsn, source=True) as conn:
        available = catalog.list(conn)
        spec = SectionSpec(
            id="peers", title="Peer results", sources=[selection], instruction="Compare peer data.",
            **({"peer_group": args.peer_group} if args.peer_group else
               {"banks": [catalog.match(available, label).symbol for label in args.bank]}),
        )
        rows = []
        for symbol in spec.bank_symbols():
            try:
                bank = catalog.match(available, symbol)
                if args.peer_group and (bank.symbol not in BIG_SIX or "canadian_bank" not in bank.tags):
                    print(f"{symbol}: peer_group_membership_unconfirmed")
                    continue
                scope = Scope(bank, period, args.metric, args.segment)
                probe = adapter.probe(conn, scope)
                if probe.state == "ready":
                    rows.extend(adapter.search(conn, scope))
                else:
                    print(f"{symbol}: {probe.reason}")
            except SourceIssue as exc:
                print(f"{symbol}: {exc.reason}")
        print(json.dumps(peer_statistics(spec, period, rows), indent=2))


if __name__ == "__main__":
    main()
