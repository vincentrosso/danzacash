#!/usr/bin/env python3
"""Extract source files and append each new entry to ledger/YYYY/MM.beancount by its date.

    uv run python scripts/extract_to_months.py books/.cache/simplefin/simplefin-*.json
    uv run python scripts/extract_to_months.py ~/Downloads/Chase1234_Activity.CSV

De-dupes against the whole existing ledger (and across the files given), so re-running is a no-op.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

from beancount import loader
from beancount.core import data
from beancount.parser import printer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from importers.chase_csv_importer import ChaseCSVImporter  # noqa: E402
from importers.common import Rules, books_dir  # noqa: E402
from importers.simplefin_importer import SimpleFINImporter  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    args = ap.parse_args()

    books = books_dir()
    entries, errors, _ = loader.load_file(str(books / "main.beancount"))
    if errors:
        sys.exit(f"ledger has errors before import ({errors[0].message}); fix with bean-check first")

    rules = Rules.load(books / "rules.yaml")
    importers = [SimpleFINImporter(rules), ChaseCSVImporter(rules=rules)]
    by_month: dict[Path, list] = defaultdict(list)
    total = 0
    for src in sorted(args.sources):
        importer = next((i for i in importers if i.identify(src)), None)
        if importer is None:
            print(f"skip (unrecognised): {src}", file=sys.stderr)
            continue
        new = importer.extract(src, entries)
        entries.extend(new)  # later files de-dupe against earlier ones
        for e in new:
            by_month[books / "ledger" / f"{e.date:%Y}" / f"{e.date:%m}.beancount"].append(e)
        n = sum(isinstance(e, data.Transaction) for e in new)
        total += n
        print(f"{Path(src).name}: {n} new txns")

    stamp = dt.date.today().isoformat()
    for path, new in sorted(by_month.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        new.sort(key=data.entry_sortkey)
        with path.open("a") as f:
            f.write(f"\n;; --- imported {stamp}\n")
            for e in new:
                f.write("\n" + printer.format_entry(e))
        print(f"  -> {path.relative_to(books)} (+{len(new)})")
    print(f"total new transactions: {total}")


if __name__ == "__main__":
    main()
