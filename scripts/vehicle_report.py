#!/usr/bin/env python3
"""Per-vehicle report: cost basis, sale price, gross profit, days in inventory, unsold units.

    uv run python scripts/vehicle_report.py [books/main.beancount]
    uv run python scripts/vehicle_report.py --release STK-0001 2026-03-15   # print the COGS entry

A vehicle is any transaction carrying `stock:` metadata. Costs are postings to
Assets:Inventory:Vehicles; the sale is Income:Sales:Vehicles; COGS releases the basis.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from beancount import loader
from beancount.core import data

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from importers.common import books_dir  # noqa: E402

INVENTORY = "Assets:Inventory:Vehicles"
SALES = "Income:Sales:Vehicles"
COGS = "Expenses:COGS:Vehicles"
ZERO = Decimal("0")


@dataclass
class Vehicle:
    stock: str
    vin: str = ""
    desc: str = ""
    cost: Decimal = ZERO        # capitalized into inventory
    on_hand: Decimal = ZERO     # current inventory balance
    sale: Decimal = ZERO
    cogs: Decimal = ZERO
    first_cost: dt.date | None = None
    sold: dt.date | None = None
    txns: list = field(default_factory=list)

    @property
    def gross_profit(self) -> Decimal:
        return self.sale - self.cogs

    def days(self, today: dt.date) -> int | None:
        if not self.first_cost:
            return None
        return ((self.sold or today) - self.first_cost).days


def untagged_inventory(entries: data.Entries) -> Decimal:
    """Inventory postings with no `stock:` — e.g. an imported auction payment awaiting a tag."""
    return sum((p.units.number for e in entries if isinstance(e, data.Transaction)
                and "stock" not in (e.meta or {}) for p in e.postings if p.account == INVENTORY), ZERO)


def collect(entries: data.Entries) -> dict[str, Vehicle]:
    cars: dict[str, Vehicle] = {}

    def car(stock: str) -> Vehicle:
        return cars.setdefault(stock, Vehicle(stock))

    for e in entries:
        if isinstance(e, data.Custom) and e.type == "vehicle":
            vals = [v.value for v in e.values]
            v = car(str(vals[0]))
            v.vin = str(vals[1]) if len(vals) > 1 else v.vin
            v.desc = str(vals[2]) if len(vals) > 2 else v.desc
            continue
        if not isinstance(e, data.Transaction) or "stock" not in (e.meta or {}):
            continue
        v = car(str(e.meta["stock"]))
        v.vin = v.vin or str(e.meta.get("vin", ""))
        v.txns.append(e)
        for p in e.postings:
            n = p.units.number
            if p.account == INVENTORY:
                v.on_hand += n
                if n > 0:
                    v.cost += n
                    v.first_cost = min(filter(None, [v.first_cost, e.date]))
            elif p.account == SALES:
                v.sale += -n
                v.sold = max(filter(None, [v.sold, e.date]))
            elif p.account == COGS:
                v.cogs += n
    return cars


def report(cars: dict[str, Vehicle], today: dt.date) -> str:
    head = f"{'STOCK':<10} {'VIN':<17} {'COST':>10} {'SALE':>10} {'GROSS':>10} {'DAYS':>5}  STATUS"
    lines = [head, "-" * len(head)]
    for v in sorted(cars.values(), key=lambda c: c.stock):
        if v.on_hand and v.sold:
            status = "SOLD — basis not released"
        elif v.on_hand:
            status = "unsold"
        elif v.sold:
            status = "sold"
        else:
            status = "?"
        sale = f"{v.sale:,.2f}" if v.sold else ""
        gross = f"{v.gross_profit:,.2f}" if v.sold and not v.on_hand else ""
        days = v.days(today)
        lines.append(f"{v.stock:<10} {v.vin[:17]:<17} {v.cost:>10,.2f} {sale:>10} {gross:>10} "
                     f"{days if days is not None else '':>5}  {status}")
    unsold = [v for v in cars.values() if v.on_hand]
    lines.append("")
    lines.append(f"Unsold units: {len(unsold)}   inventory on hand: "
                 f"{sum((v.on_hand for v in unsold), ZERO):,.2f} USD")
    return "\n".join(lines)


def release_entry(v: Vehicle, date: dt.date) -> str:
    tag = "stk-" + v.stock.lower().removeprefix("stk-")
    return (f'{date} * "Release cost basis — {v.stock}" #{tag}\n'
            f'  stock: "{v.stock}"\n' + (f'  vin: "{v.vin}"\n' if v.vin else "") +
            f"  {COGS:<34} {v.on_hand:>10.2f} USD\n"
            f"  {INVENTORY:<34} {-v.on_hand:>10.2f} USD\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger", nargs="?", default=str(books_dir() / "main.beancount"))
    ap.add_argument("--release", nargs=2, metavar=("STOCK", "DATE"))
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args()
    entries, errors, _ = loader.load_file(args.ledger)
    for err in errors:
        print(f"warning: {err.message}", file=sys.stderr)
    cars = collect(entries)
    if args.release:
        stock, date = args.release
        if stock not in cars or not cars[stock].on_hand:
            sys.exit(f"{stock}: nothing in inventory to release")
        print(release_entry(cars[stock], dt.date.fromisoformat(date)))
        return
    print(report(cars, args.today))
    loose = untagged_inventory(entries)
    if loose:
        print(f"Untagged inventory (needs stock:/vin:): {loose:,.2f} USD")


if __name__ == "__main__":
    main()
