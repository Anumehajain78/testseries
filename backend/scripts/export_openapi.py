"""Write the OpenAPI document to disk.

Run from the backend directory:

    ./.venv/bin/python scripts/export_openapi.py

The frontend generates its TypeScript from the emitted file, so this runs
whenever a schema changes. Keeping it a committed artifact means a contract
change shows up as a reviewable diff rather than a silent behaviour shift.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def main() -> int:
    schema = app.openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths = len(schema.get("paths", {}))
    models = len(schema.get("components", {}).get("schemas", {}))
    print(f"wrote {OUTPUT.relative_to(Path.cwd())} — {paths} paths, {models} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
