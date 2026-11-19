"""Read aggregate schedule metrics with an authorised report-side DSN."""
import json
import os

from aegis_report.db import connect


def main():
    dsn = os.getenv("RPT_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set RPT_DATABASE_URL to an authorised report metrics DSN.")
    with connect(dsn, source=True) as conn:
        lag = conn.execute("""
            SELECT coalesce(max(greatest(0, extract(epoch FROM now() - next_poll_at))), 0) AS seconds
            FROM rpt.schedules WHERE enabled
        """).fetchone()
        queue = conn.execute("""
            SELECT state, count(*) AS count FROM rpt.runs WHERE schedule_generation IS NOT NULL
              AND state IN ('queued', 'waiting', 'running') GROUP BY state ORDER BY state
        """).fetchall()
        readiness = conn.execute("""
            SELECT observation->>'source' AS source, count(*) AS scopes,
                   avg(extract(epoch FROM (observation->>'stable_at')::timestamptz -
                        (observation->>'since')::timestamptz)) AS mean_seconds
            FROM rpt.schedule_periods p CROSS JOIN LATERAL jsonb_each(p.readiness) AS scope(id, observation)
            WHERE observation ? 'stable_at' GROUP BY source ORDER BY source
        """).fetchall()
        supersessions = conn.execute("""
            SELECT count(*) AS count FROM rpt.runs WHERE publication_state = 'superseded'
        """).fetchone()
        failures = conn.execute("""
            SELECT error_code, count(*) AS count FROM rpt.runs WHERE schedule_generation IS NOT NULL
                AND state = 'failed' GROUP BY error_code ORDER BY error_code
        """).fetchall()
    print(json.dumps({
        "poll_lag_seconds": lag["seconds"], "queue": queue, "source_quiet_seconds": readiness,
        "superseded": supersessions["count"], "failures": failures,
    }, default=str, indent=2))


if __name__ == "__main__":
    main()
