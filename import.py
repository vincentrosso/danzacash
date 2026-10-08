#!/usr/bin/env python3
"""beangulp entrypoint.

    uv run python import.py identify books/.cache/simplefin
    uv run python import.py extract -e books/main.beancount books/.cache/simplefin
    uv run python import.py archive -o books/documents ~/Downloads/Chase*.csv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import beangulp  # noqa: E402

from importers.chase_csv_importer import ChaseCSVImporter  # noqa: E402
from importers.common import Rules  # noqa: E402
from importers.simplefin_importer import SimpleFINImporter  # noqa: E402

rules = Rules.load()
importers = [SimpleFINImporter(rules), ChaseCSVImporter(rules=rules)]

if __name__ == "__main__":
    beangulp.Ingest(importers)()
