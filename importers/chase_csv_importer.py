"""beangulp importer for the Chase business checking CSV export.

Expected header: Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
(Chase adds a trailing comma on every row; csv.DictReader tolerates it.)
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
from collections import Counter
from decimal import Decimal
from pathlib import Path

import beangulp
from beancount.core import data

from importers.common import (
    CURRENCY, DEFAULT_ACCOUNT, Rules, existing_balances, existing_ids, make_txn, normalize_desc,
)

ID_KEY = "chase_id"
HEADER = ["Details", "Posting Date", "Description", "Amount", "Type", "Balance", "Check or Slip #"]


def _rows(filepath: str) -> list[dict]:
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%m/%d/%Y").date()


def _money(text: str) -> Decimal:
    return Decimal(text.replace(",", "").replace("$", "").strip())


class ChaseCSVImporter(beangulp.Importer):
    def __init__(self, account: str = DEFAULT_ACCOUNT, rules: Rules | None = None):
        self.bank_account = account
        self.rules = rules or Rules.load()

    def identify(self, filepath: str) -> bool:
        if not filepath.lower().endswith(".csv"):
            return False
        with open(filepath, encoding="utf-8-sig") as f:
            first = f.readline()
        return [h.strip() for h in first.strip().rstrip(",").split(",")] == HEADER

    def account(self, filepath: str) -> str:
        return self.bank_account

    def date(self, filepath: str):
        rows = _rows(filepath)
        return max(_date(r["Posting Date"]) for r in rows) if rows else None

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        rows = _rows(filepath)
        seen = existing_ids(existing, ID_KEY)
        entries: data.Entries = []
        # Occurrence counter keeps two identical same-day charges distinct while staying
        # stable when the same file (or an overlapping export) is imported again.
        occurrences: Counter = Counter()
        # Chase lists newest first; walk oldest first so the counter order is chronological.
        for lineno, row in reversed(list(enumerate(rows, start=2))):
            date = _date(row["Posting Date"])
            amount = _money(row["Amount"])
            desc = normalize_desc(row["Description"])
            key = (date.isoformat(), str(amount), desc)
            occurrences[key] += 1
            cid = hashlib.sha1("|".join(key + (str(occurrences[key]),)).encode()).hexdigest()[:16]
            if cid in seen:
                continue
            seen.add(cid)
            meta = data.new_metadata(filepath, lineno)
            meta[ID_KEY] = cid
            if (row.get("Check or Slip #") or "").strip():
                meta["check"] = row["Check or Slip #"].strip()
            entries.append(make_txn(
                meta=meta, date=date, bank_account=self.bank_account,
                amount=amount, description=" ".join(row["Description"].split()), rules=self.rules,
            ))
        # Top row carries the running balance after the newest day's activity.
        if rows and (rows[0].get("Balance") or "").strip():
            when = _date(rows[0]["Posting Date"]) + dt.timedelta(days=1)
            if (when, self.bank_account) not in existing_balances(existing):
                entries.append(data.Balance(
                    data.new_metadata(filepath, 2), when, self.bank_account,
                    data.Amount(_money(rows[0]["Balance"]), CURRENCY), None, None,
                ))
        return entries

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        pass  # exact de-dupe by chase_id happens in extract()
