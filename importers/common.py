"""Shared bits for the DANZA importers: config paths, rules, de-dupe, entry building."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml
from beancount.core import data

REPO_ROOT = Path(__file__).resolve().parent.parent
CURRENCY = "USD"
DEFAULT_ACCOUNT = "Assets:Bank:Chase:Checking"
UNCATEGORIZED_DEBIT = "Expenses:Uncategorized"
UNCATEGORIZED_CREDIT = "Income:Other"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment wins."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def books_dir() -> Path:
    load_dotenv()
    return Path(os.environ.get("DANZA_BOOKS", REPO_ROOT / "books")).expanduser().resolve()


@dataclass
class Rule:
    pattern: re.Pattern
    account: str
    tags: frozenset = frozenset()
    narration: str | None = None
    flag: str = "*"
    sign: str | None = None  # "debit" (money out), "credit" (money in), or None = either

    def applies(self, text: str, amount: Decimal) -> bool:
        if self.sign == "debit" and amount >= 0:
            return False
        if self.sign == "credit" and amount <= 0:
            return False
        return bool(self.pattern.search(text))


@dataclass
class Rules:
    rules: list[Rule] = field(default_factory=list)
    # SimpleFIN account id (or name regex) -> beancount account
    accounts: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "Rules":
        path = path or books_dir() / "rules.yaml"
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text()) or {}
        rules = [
            Rule(
                pattern=re.compile(r["match"], re.IGNORECASE),
                account=r["account"],
                tags=frozenset(r.get("tags") or ()),
                narration=r.get("narration"),
                flag=r.get("flag", "*"),
                sign=r.get("sign"),
            )
            for r in raw.get("rules") or []
        ]
        return cls(rules=rules, accounts=dict(raw.get("accounts") or {}))

    def categorize(self, text: str, amount: Decimal) -> tuple[str, str, frozenset, str | None]:
        """Return (account, flag, tags, narration) for the counter-posting."""
        for rule in self.rules:
            if rule.applies(text, amount):
                return rule.account, rule.flag, rule.tags, rule.narration
        fallback = UNCATEGORIZED_DEBIT if amount < 0 else UNCATEGORIZED_CREDIT
        return fallback, "!", frozenset(), None

    def account_for(self, sfin_id: str, name: str) -> str:
        if sfin_id in self.accounts:
            return self.accounts[sfin_id]
        for key, account in self.accounts.items():
            if re.search(key, name or "", re.IGNORECASE):
                return account
        return DEFAULT_ACCOUNT


def existing_ids(entries: data.Entries, key: str) -> set[str]:
    return {
        str(e.meta[key])
        for e in entries
        if isinstance(e, data.Transaction) and e.meta and key in e.meta
    }


def existing_balances(entries: data.Entries) -> set[tuple]:
    return {(e.date, e.account) for e in entries if isinstance(e, data.Balance)}


def make_txn(
    *,
    meta: dict,
    date,
    bank_account: str,
    amount: Decimal,
    description: str,
    rules: Rules,
    payee: str | None = None,
) -> data.Transaction:
    counter, flag, tags, narration = rules.categorize(description, amount)
    units = data.Amount(amount, CURRENCY)
    postings = [
        data.Posting(bank_account, units, None, None, None, None),
        data.Posting(counter, -units, None, None, None, None),
    ]
    return data.Transaction(
        meta, date, flag, payee, narration or description, tags, frozenset(), postings
    )


def normalize_desc(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).upper()
