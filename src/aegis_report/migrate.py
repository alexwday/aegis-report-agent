import argparse
import os
from hashlib import sha256
from pathlib import Path

from .db import connect


def migrate(dsn: str, directory: Path) -> list[str]:
    scripts = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not scripts:
        raise ValueError("Migration directory contains no SQL migrations")
    applied = []
    with connect(dsn) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(28567001)")
        connection.execute("CREATE SCHEMA IF NOT EXISTS rpt")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS rpt.schema_migrations (
                name text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        known = {row["name"]: row["checksum"] for row in connection.execute(
            "SELECT name, checksum FROM rpt.schema_migrations"
        )}
        for path in scripts:
            sql = path.read_bytes()
            checksum = sha256(sql).hexdigest()
            if path.name in known:
                if known[path.name] != checksum:
                    raise ValueError(f"Edited migration: {path.name}")
                continue
            connection.execute(sql.decode("utf-8"), prepare=False)
            connection.execute("INSERT INTO rpt.schema_migrations (name, checksum) VALUES (%s, %s)",
                               (path.name, checksum))
            applied.append(path.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("db/migrations"))
    args = parser.parse_args()
    applied = migrate(os.environ["RPT_MIGRATION_DATABASE_URL"], args.directory)
    print("Applied " + ", ".join(applied) if applied else "Migrations up to date")


if __name__ == "__main__":
    main()
