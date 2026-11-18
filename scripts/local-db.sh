# Source from a script running at the repository root.
start_local_db() {
    pg_bin="$(pg_config --bindir)"
    fixture_dir="$(mktemp -d /tmp/aegis-g1.XXXXXXXX)"
    "$pg_bin/initdb" -D "$fixture_dir/pgdata" -U fixture_admin --auth=trust --no-locale -E UTF8 >/dev/null
    "$pg_bin/pg_ctl" -D "$fixture_dir/pgdata" -l "$fixture_dir/postgres.log" \
        -o "-c listen_addresses='' -p 5432 -k $fixture_dir" -w start >/dev/null

    local socket_dsn="host=$fixture_dir port=5432 dbname=postgres"
    export RPT_MIGRATION_DATABASE_URL="$socket_dsn user=fixture_admin"
    export RPT_DATABASE_URL="$socket_dsn user=rpt_runtime"
    export SOURCE_DATABASE_URL="$socket_dsn user=source_reader"
    export ENVIRONMENT=local AUTH_PROVIDER=local
    export LOCAL_AUTH_USER_ID=local-dev-user
    export OWNER_KEY_SECRET
    OWNER_KEY_SECRET="$(uv run --no-sync python -c 'import secrets; print(secrets.token_urlsafe(48))')"
    # The fixture always uses the stub, even when launched from a configured deployment shell.
    unset INTERNAL_LLM_URL INTERNAL_LLM_API_KEY CHAT_MODEL AUTH_VALIDATION_URL
    unset PGHOSTADDR PGSERVICE PGOPTIONS PGPASSWORD
    local fixture_psql=("$pg_bin/psql" -X "$RPT_MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1)
    "${fixture_psql[@]}" --single-transaction -q -f db/sources.sql -f db/seed/synthetic.sql
    uv run --no-sync python -m aegis_report.migrate
    "${fixture_psql[@]}" --single-transaction -q -f db/local-roles.sql
}

stop_local_db() {
    if [[ "${fixture_dir:-}" == /tmp/aegis-g1.* && -d "$fixture_dir" ]]; then
        if [[ -f "$fixture_dir/pgdata/postmaster.pid" ]]; then
            "$pg_bin/pg_ctl" -D "$fixture_dir/pgdata" -m fast -w stop >/dev/null
        fi
        rm -rf -- "$fixture_dir"
    fi
}
