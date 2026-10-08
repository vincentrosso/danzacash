# HANDOFF: DANZA AUTO LLC bookkeeping — Beancount + Fava

## Goal
Set up a self-hosted, plain-text double-entry bookkeeping system for DANZA AUTO LLC
(California used-car dealer LLC). Single operator, low transaction volume.
Books live in a private git repo. Fava provides the local web UI.
Bank data comes from Chase business checking via SimpleFIN Bridge, with Chase CSV
import as a fallback.

## Stack
- Python 3.12+, managed with `uv`
- Beancount v3 + `beangulp` (importer framework) + `beanquery`
- Fava (web UI), bound to 127.0.0.1 only
- SimpleFIN Bridge for bank pulls (user will provide a setup token)
- git for versioning; repo must be PRIVATE

## Repo layout
danza-books/
  main.beancount            # includes everything below; options, plugins
  accounts.beancount        # open directives / chart of accounts
  prices.beancount          # (likely unused, USD only)
  ledger/2026/*.beancount   # one file per month of imported txns
  vehicles/                 # one file per vehicle (stock # / VIN) — see below
  importers/
    simplefin_pull.py       # fetch -> normalized JSON cache
    simplefin_importer.py   # beangulp importer for cached JSON
    chase_csv_importer.py   # beangulp importer for Chase business CSV export
    rules.yaml              # payee/regex -> account categorization rules
  import.py                 # beangulp entrypoint (identify/extract/archive)
  documents/                # receipts, bills of sale, auction invoices (gitignored or LFS — ask)
  scripts/
    run_fava.sh
    monthly_close.sh        # pull, extract, bean-check, commit
  .env.example              # SIMPLEFIN_ACCESS_URL=  (never commit real value)
  README.md

## Chart of accounts (starting point — confirm with user)
Assets:Bank:Chase:Checking
Assets:Inventory:Vehicles            # capitalized vehicle cost (see vehicle pattern)
Assets:Receivables
Liabilities:SalesTax:CDTFA           # CA sales tax collected on retail sales
Liabilities:DMV:FeesCollected        # DMV/registration fees collected, pass-through
Liabilities:CreditCard:*             # if any
Equity:Members:<Name>:Capital        # one per LLC member — ASK how many members
Equity:Members:<Name>:Draws
Equity:Opening-Balances
Income:Sales:Vehicles
Income:Fees:Documentation
Income:Other
Expenses:COGS:Vehicles               # cost basis released on sale
Expenses:Auction:BuyerFees           # only if NOT capitalized — default is capitalize
Expenses:Licensing:DealerLicense     # DMV dealer license, bond, LiveScan, etc.
Expenses:Insurance
Expenses:Rent
Expenses:Utilities
Expenses:Software
Expenses:BankFees
Expenses:Advertising
Expenses:Professional:Accounting
Expenses:Professional:Legal
Expenses:Misc
Expenses:Uncategorized               # importer default; should trend to zero

## Vehicle inventory pattern (important)
Each vehicle is tracked by stock number + VIN using transaction metadata and a tag.
- Purchase, buyer fees, transport, recon/repair, smog for a specific car -> debit
  Assets:Inventory:Vehicles with metadata `vin:` and `stock:` and tag `#stk-XXXX`.
- On sale: credit Income:Sales:Vehicles, credit Liabilities:SalesTax:CDTFA,
  credit Liabilities:DMV:FeesCollected; then a second entry moves the vehicle's total
  capitalized cost from Assets:Inventory:Vehicles to Expenses:COGS:Vehicles.
- Write a small helper script `scripts/vehicle_report.py` (beanquery) showing per-vehicle:
  cost basis, sale price, gross profit, days in inventory, unsold units.
- Add a Fava custom query/extension or saved queries for the same report.

## Importers
### SimpleFIN
- Claim flow: setup token is base64 of a claim URL; POST to it to receive the access URL
  (contains basic-auth credentials). Store the access URL in `.env` / macOS Keychain,
  never in git.
- Pull: GET {access_url}/accounts?start-date=<epoch>&end-date=<epoch>
  Cache raw JSON to `importers/cache/` (gitignored).
- Use SimpleFIN transaction `id` as `simplefin_id` metadata for de-dupe;
  importer must skip ids already present in the ledger.
- Emit `balance` assertions from the account balance + balance-date returned.

### Chase CSV fallback
- Parse Chase business checking CSV export (Details, Posting Date, Description,
  Amount, Type, Balance, Check or Slip #). Verify against a real sample file the user provides.
- De-dupe by (date, amount, normalized description) hash stored as metadata.

### Categorization
- rules.yaml: ordered list of {match: regex on payee/description, account: ..., tags: [...], narration: optional}
- Unmatched -> Expenses:Uncategorized (or Income:Other for credits), flagged `!`.
- Do NOT guess vehicle tags; leave for the user to assign stock #.

## Running Fava
- `scripts/run_fava.sh` -> `uv run fava main.beancount --host 127.0.0.1 --port 5000`
- Optional: launchd plist (macOS) to keep it running on login. ASK before installing.
- Do not expose to network. If remote access is wanted later, use Tailscale, not a public port.

## Monthly close script
monthly_close.sh:
1. simplefin_pull.py for the month
2. bean-extract (beangulp) into ledger/YYYY/MM.beancount
3. bean-check main.beancount — fail loudly on errors
4. print count of `!`-flagged / Uncategorized txns
5. git add + commit with message "close YYYY-MM"

## Validation / acceptance
- `bean-check` passes clean.
- Fava loads; Income Statement and Balance Sheet render.
- A test vehicle round trip (buy -> recon -> sell) produces correct gross profit in the
  vehicle report and nets Inventory back to zero for that unit.
- Re-running import on the same date range creates zero duplicates.
- Balance assertion from SimpleFIN matches the ledger.
- No secrets in git (`git log -p | grep -i simplefin` clean except .env.example).

## Ask the user before starting
1. Where it runs: local Mac only, or also on a server? (default: local Mac)
2. Number of LLC members (for equity accounts) and opening balance / start date of books.
3. SimpleFIN setup token now, or start with CSV only?
4. A sample Chase business CSV export to test the parser against.
5. Store receipts/documents in repo (git LFS) or keep them outside git?

## Out of scope for now
Invoicing/AR, payroll, sales tax return filing, multi-currency, any public hosting.