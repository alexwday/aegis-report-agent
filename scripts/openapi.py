import argparse
import json
from pathlib import Path

from aegis_report.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    filename = Path(__file__).resolve().parents[1] / "api/openapi.json"
    output = json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if not filename.exists() or filename.read_text(encoding="utf-8") != output:
            raise SystemExit("OpenAPI mismatch. Run uv run python scripts/openapi.py.")
        print("OpenAPI matches the FastAPI-generated contract")
    else:
        filename.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
