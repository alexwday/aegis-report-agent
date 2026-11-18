from datetime import datetime

from psycopg.types.json import Jsonb

from .sources import Probe, Readiness


def observe(probe: Probe, previous: dict, now: datetime, quiet_seconds: float) -> dict:
    observation = probe.model_dump(mode="json") | {"since": None, "stable": False, "data_stability": "unknown"}
    if probe.state is not Readiness.READY or probe.marker is None:
        return observation
    if previous.get("since") and previous.get("marker") == probe.marker:
        since = datetime.fromisoformat(previous["since"])
        stable = (now - since).total_seconds() >= quiet_seconds
        observation.update(
            since=since.isoformat(), stable=stable,
            data_stability="stable" if stable else previous.get("data_stability", "unknown"),
        )
    else:
        observation["since"] = now.isoformat()
        if previous.get("marker") is not None and previous["marker"] != probe.marker:
            observation["data_stability"] = "recently_changed"
    return observation


def record_observation(conn, key: str, probe: Probe, now: datetime, quiet_seconds: float) -> str:
    # Serialize updates for the same scope. Older probe snapshots never replace newer observations.
    conn.execute("""
        INSERT INTO rpt.source_observations (scope_key, observed_at, observation) VALUES (%s, %s, '{}'::jsonb)
        ON CONFLICT (scope_key) DO NOTHING
    """, (key, now))
    previous = conn.execute("""
        SELECT observed_at, observation FROM rpt.source_observations WHERE scope_key = %s FOR UPDATE
    """, (key,)).fetchone()
    if previous["observed_at"] > now:
        return "unknown"
    current = observe(probe, previous["observation"], now, quiet_seconds)
    conn.execute("""
        UPDATE rpt.source_observations SET observed_at = %s, observation = %s WHERE scope_key = %s
    """, (now, Jsonb(current), key))
    return current["data_stability"]
