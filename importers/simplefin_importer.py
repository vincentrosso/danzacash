"""beangulp importer for SimpleFIN JSON written by simplefin_pull.py."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import beangulp
from beancount.core import data

from importers.common import CURRENCY, Rules, existing_balances, existing_ids, make_txn

ID_KEY = "simplefin_id"


def _date(epoch) -> dt.date:
    return dt.datetime.fromtimestamp(int(epoch)).date()


class SimpleFINImporter(beangulp.Importer):
    def __init__(self, rules: Rules | None = None):
        self.rules = rules or Rules.load()

    def identify(self, filepath: str) -> bool:
        name = Path(filepath).name
        return name.startswith("simplefin-") and name.endswith(".json")

    def account(self, filepath: str) -> str:
        accts = json.loads(Path(filepath).read_text()).get("accounts") or [{}]
        return self.rules.account_for(accts[0].get("id", ""), accts[0].get("name", ""))

    def filename(self, filepath: str) -> str:
        return Path(filepath).name

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        payload = json.loads(Path(filepath).read_text())
        seen = existing_ids(existing, ID_KEY)
        seen_bal = existing_balances(existing)
        req_end = payload.get("_request", {}).get("end")
        entries: data.Entries = []
        for idx, acct in enumerate(payload.get("accounts") or []):
            bank = self.rules.account_for(acct.get("id", ""), acct.get("name", ""))
            for t in acct.get("transactions") or []:
                if t.get("pending"):
                    continue  # pending ids can change; pick them up once posted
                tid = str(t["id"])
                if tid in seen:
                    continue
                seen.add(tid)
                meta = data.new_metadata(filepath, idx)
                meta[ID_KEY] = tid
                description = " ".join(filter(None, [t.get("description"), t.get("memo")])).strip()
                entries.append(make_txn(
                    meta=meta,
                    date=_date(t["posted"]),
                    bank_account=bank,
                    amount=Decimal(str(t["amount"])),
                    description=description,
                    payee=t.get("payee") or None,
                    rules=self.rules,
                ))
            # A balance assertion is only valid if the pull reached the balance date;
            # an old month's pull would be missing everything posted since.
            if acct.get("balance-date") and acct.get("balance") is not None:
                bal_day = _date(acct["balance-date"])
                if req_end and dt.date.fromisoformat(req_end) > bal_day:
                    when = bal_day + dt.timedelta(days=1)
                    if (when, bank) not in seen_bal:
                        entries.append(data.Balance(
                            data.new_metadata(filepath, idx), when, bank,
                            data.Amount(Decimal(str(acct["balance"])), CURRENCY), None, None,
                        ))
        return entries

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        # De-dupe is exact, by simplefin_id, inside extract(). The default fuzzy
        # matcher would wrongly drop two genuine same-day, same-amount charges.
        pass
