# danzacash

Plain-text double-entry bookkeeping for **DANZA AUTO LLC**, a California used-car
dealer: Beancount v3 + beangulp importers + Fava, with Chase business checking
pulled via SimpleFIN Bridge (Chase CSV as fallback).

This repo is the **tooling only** and is public. The ledger lives in a separate
**private** repo (`danza-books`), checked out at `./books/` (gitignored here).

```
danzacash/ (public)               books/ (private: danza-books)
  importers/                        main.beancount       options, includes, Fava queries
    simplefin_pull.py               accounts.beancount   chart of accounts
    simplefin_importer.py           opening.beancount    opening balances
    chase_csv_importer.py           rules.yaml           categorization rules
    common.py  (rules, de-dupe)     ledger/2026/MM.beancount
  import.py   beangulp CLI          vehicles/STK-XXXX.beancount
  scripts/                          documents/           gitignored (Dropbox backs it up)
    run_fava.sh  monthly_close.sh   .cache/simplefin/    gitignored raw pulls
    vehicle_report.py  init_books.sh
  template/   skeleton for books/
  tests/      acceptance tests
```

## Setup

```bash
uv sync                                   # Python 3.12, beancount/beangulp/beanquery/fava
scripts/init_books.sh                     # only if ./books doesn't exist yet
git clone git@github.com:vincentrosso/danza-books.git books   # on a new machine
cp .env.example .env                      # optional overrides
uv run pytest -q
```

**SimpleFIN:** get a setup token from bridge.simplefin.org, then
`uv run python importers/simplefin_pull.py claim <TOKEN>`. That spends the token and
saves the access URL to the macOS Keychain (`danzacash-simplefin`). Setting
`SIMPLEFIN_ACCESS_URL` in `.env` works too. Neither goes into git.

## Daily use

```bash
scripts/run_fava.sh                       # http://127.0.0.1:5050 (localhost only)
scripts/monthly_close.sh                  # previous month: pull → extract → bean-check → commit books
scripts/monthly_close.sh 2026-09 ~/Downloads/Chase1234_Activity.CSV   # CSV fallback
uv run python scripts/vehicle_report.py   # per-vehicle cost/sale/gross/days, unsold units
```

Port 5000 (the handoff default) is taken by macOS AirPlay Receiver, so Fava uses
5050 (`FAVA_PORT`). Remote access goes through the hosted copy below, never a public port.

## Hosted copy

A **read-only** Fava runs at https://autoarb.ndex.us/books/. It sits behind the autoarb
login with a stricter owner-only check (`/api/auth/check-books`, `AUTH_BOOKS_EMAILS`):
no fleet-IP bypass, and it fails closed. Server pieces:

- `fava-books.service`: runs as user `books` on 127.0.0.1:5051 with `--prefix /books --read-only`.
- `books-pull.timer`: every 5 min, `git reset --hard origin/main` from `danza-books`, using a read-only deploy key.

No SimpleFIN credential lives on the server. Edit locally and push; `monthly_close.sh` pushes for you.

## Categorization

`books/rules.yaml` is an ordered list. The first regex match on the bank description
wins. Unmatched debits go to `Expenses:Uncategorized` and credits to `Income:Other`,
both flagged `!`. Auction payments land in `Assets:Inventory:Vehicles` flagged `!`. The
importer never guesses a stock number; you add it yourself.

## Vehicle pattern

Everything spent on one car (hammer, buyer fee, transport, recon, smog) debits
`Assets:Inventory:Vehicles` and carries `stock:` / `vin:` metadata plus a `#stk-XXXX` tag.
To record a sale:

1. Credit `Income:Sales:Vehicles`, `Liabilities:SalesTax:CDTFA`, and `Liabilities:DMV:FeesCollected`.
2. Release the basis. `vehicle_report.py --release STK-0001 2026-03-15` prints the COGS entry.

See `tests/fixtures/STK-0001.beancount` for a full round trip. Fava saved queries:
`vehicle-cost-basis`, `vehicle-unsold`, `vehicle-gross-profit`, `needs-attention`.

## De-dupe

- **SimpleFIN:** de-dupes on the exact transaction `id` (`simplefin_id`). Pending transactions are skipped. A balance assertion is emitted only when the pull window reaches the balance date.
- **Chase CSV:** de-dupes on `chase_id` = hash(date, amount, normalized description, occurrence #), so two identical same-day charges stay distinct.
- **Mixing sources:** don't import the same period from both. The two de-dupe ids don't know about each other.

The full original spec is in [HANDOFF.md](HANDOFF.md).
