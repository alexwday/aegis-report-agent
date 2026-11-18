#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
pg_bin="$(pg_config --bindir)"
fixture_dir="$(mktemp -d /tmp/aegis-fixture.XXXXXXXX)"
cleanup() {
    if [[ -f "$fixture_dir/pgdata/postmaster.pid" ]]; then
        "$pg_bin/pg_ctl" -D "$fixture_dir/pgdata" -m fast -w stop >/dev/null
    fi
    rm -rf -- "$fixture_dir"
}
trap cleanup EXIT

"$pg_bin/initdb" -U fixture_admin --auth=trust --no-locale -E UTF8 -D "$fixture_dir/pgdata" >/dev/null
# The private temporary directory isolates the socket. TCP is disabled.
"$pg_bin/pg_ctl" -D "$fixture_dir/pgdata" -l "$fixture_dir/postgres.log" \
    -o "-c listen_addresses='' -p 5432 -k $fixture_dir" -w start >/dev/null
# Supplying every connection field prevents inherited PG* settings from targeting another database.
fixture_psql=(env -u PGHOSTADDR -u PGSERVICE "$pg_bin/psql" -X -h "$fixture_dir" -p 5432 -U fixture_admin -d postgres -v ON_ERROR_STOP=1)
"${fixture_psql[@]}" --single-transaction -q -f "$repo_dir/db/sources.sql" -f "$repo_dir/db/seed/synthetic.sql"
"${fixture_psql[@]}" --single-transaction -q -f "$repo_dir/docs/collab/plans/rpt-draft.sql"
"${fixture_psql[@]}" -At -f "$repo_dir/db/seed/check.sql"
