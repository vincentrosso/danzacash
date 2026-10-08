"""Acceptance tests from HANDOFF.md, run against a throwaway copy of template/."""

import datetime as dt
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from beancount import loader
from beancount.core import data

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from importers.chase_csv_importer import ChaseCSVImporter  # noqa: E402
from importers.common import Rules  # noqa: E402
from importers.simplefin_importer import SimpleFINImporter  # noqa: E402
from scripts.vehicle_report import collect  # noqa: E402


@pytest.fixture
def books(tmp_path):
    dst = tmp_path / "books"
    shutil.copytree(ROOT / "template", dst)
    return dst


def load(books):
    entries, errors, _ = loader.load_file(str(books / "main.beancount"))
    assert not errors, [e.message for e in errors]
    return entries


def extract_into(books, importer, src: Path, month_file="2026/03.beancount"):
    """Mimic monthly_close: extract against the existing ledger, append to the month file."""
    entries = load(books)
    new = importer.extract(str(src), entries)
    out = books / "ledger" / month_file
    from beancount.parser import printer
    with out.open("a") as f:
        for e in new:
            f.write(printer.format_entry(e) + "\n")
    return new


def test_template_checks_clean(books):
    load(books)


def test_vehicle_round_trip(books):
    shutil.copy(FIX / "STK-0001.beancount", books / "vehicles")
    car = collect(load(books))["STK-0001"]
    assert car.cost == Decimal("8510.00")
    assert car.sale == Decimal("12000.00")
    assert car.gross_profit == Decimal("3490.00")
    assert car.on_hand == 0
    assert car.days(dt.date(2026, 10, 1)) == 40
    assert car.vin == "2T3W1RFV8JW000001"


@pytest.mark.parametrize("make_importer,src", [
    (lambda r: SimpleFINImporter(r), FIX / "simplefin-20260301-20260307.json"),
    (lambda r: ChaseCSVImporter(rules=r), FIX / "chase_sample.csv"),
])
def test_import_idempotent_and_balances(books, make_importer, src):
    importer = make_importer(Rules.load(books / "rules.yaml"))
    assert importer.identify(str(src))
    first = extract_into(books, importer, src)
    txns = [e for e in first if isinstance(e, data.Transaction)]
    assert len(txns) == 5  # pending skipped; the two identical coffees both kept
    assert sum(isinstance(e, data.Balance) for e in first) == 1
    by_desc = {t.narration: t for t in txns}
    assert by_desc["MONTHLY SERVICE FEE"].postings[1].account == "Expenses:BankFees"
    assert by_desc["MONTHLY SERVICE FEE"].flag == "*"
    copart = next(t for t in txns if "COPART" in t.narration)
    assert copart.postings[1].account == "Assets:Inventory:Vehicles" and copart.flag == "!"
    assert not copart.tags - {"auction"}  # never guesses a stock tag
    xfer = next(t for t in txns if "TRANSFER" in t.narration)
    assert xfer.postings[1].account == "Income:Other" and xfer.flag == "!"
    load(books)  # balance assertion matches the ledger
    assert extract_into(books, importer, src) == []  # re-run: zero duplicates


def test_simplefin_skips_balance_for_stale_window(books, tmp_path):
    import json
    raw = json.loads((FIX / "simplefin-20260301-20260307.json").read_text())
    raw["_request"]["end"] = "2026-03-04"  # window ends before the balance date
    src = tmp_path / "simplefin-20260301-20260304.json"
    src.write_text(json.dumps(raw))
    out = SimpleFINImporter(Rules.load(books / "rules.yaml")).extract(str(src), [])
    assert not any(isinstance(e, data.Balance) for e in out)


def test_beangulp_cli_extract(books):
    out = subprocess.run(
        [sys.executable, str(ROOT / "import.py"), "extract", "-e", str(books / "main.beancount"),
         str(FIX / "chase_sample.csv")],
        capture_output=True, text=True, env={"DANZA_BOOKS": str(books), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.count("chase_id:") == 5
