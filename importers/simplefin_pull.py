#!/usr/bin/env python3
"""SimpleFIN Bridge client: claim a setup token, or pull a date range to the JSON cache.

    uv run python importers/simplefin_pull.py claim <SETUP_TOKEN>
    uv run python importers/simplefin_pull.py pull --month 2026-09
    uv run python importers/simplefin_pull.py pull --start 2026-09-01 --end 2026-10-01

The access URL (it embeds basic-auth credentials) is read from $SIMPLEFIN_ACCESS_URL
(.env) or the macOS Keychain item "danzacash-simplefin". It is never written to git.
"""

from __future__ import annotations

import argparse
import base64
import calendar
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from importers.common import books_dir, load_dotenv  # noqa: E402

KEYCHAIN_SERVICE = "danzacash-simplefin"
# SimpleFIN Bridge 403s urllib's default "Python-urllib/x.y" User-Agent.
USER_AGENT = "danzacash/0.1 (+https://github.com/vincentrosso/danzacash)"


def cache_dir() -> Path:
    d = books_dir() / ".cache" / "simplefin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def access_url() -> str:
    load_dotenv()
    url = os.environ.get("SIMPLEFIN_ACCESS_URL")
    if url:
        return url
    try:
        return subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("No SimpleFIN access URL: set SIMPLEFIN_ACCESS_URL in .env or run `claim`.")


def claim(setup_token: str) -> None:
    claim_url = base64.b64decode(setup_token.strip()).decode()
    req = urllib.request.Request(claim_url, method="POST", data=b"", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        url = resp.read().decode().strip()
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
         "-a", "access-url", "-w", url],
        check=True,
    )
    print(f"Access URL stored in Keychain item '{KEYCHAIN_SERVICE}'. Setup token is now spent.")


def fetch(start: dt.date, end: dt.date) -> dict:
    parts = urllib.parse.urlsplit(access_url())
    netloc = parts.hostname + (f":{parts.port}" if parts.port else "")
    query = urllib.parse.urlencode({
        "start-date": int(dt.datetime.combine(start, dt.time()).timestamp()),
        "end-date": int(dt.datetime.combine(end, dt.time()).timestamp()),
    })
    url = urllib.parse.urlunsplit((parts.scheme, netloc, parts.path.rstrip("/") + "/accounts", query, ""))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    creds = f"{urllib.parse.unquote(parts.username or '')}:{urllib.parse.unquote(parts.password or '')}"
    req.add_header("Authorization", "Basic " + base64.b64encode(creds.encode()).decode())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def pull(start: dt.date, end: dt.date) -> Path:
    payload = fetch(start, end)
    for err in payload.get("errors") or []:
        print(f"SimpleFIN warning: {err}", file=sys.stderr)
    # Record the requested window so the importer knows whether a balance assertion is safe.
    payload["_request"] = {"start": start.isoformat(), "end": end.isoformat(),
                           "pulled_at": dt.datetime.now().isoformat(timespec="seconds")}
    out = cache_dir() / f"simplefin-{start:%Y%m%d}-{end:%Y%m%d}.json"
    out.write_text(json.dumps(payload, indent=1, sort_keys=True))
    n = sum(len(a.get("transactions") or []) for a in payload.get("accounts") or [])
    print(f"{out}  ({len(payload.get('accounts') or [])} accounts, {n} txns)")
    return out


def month_range(month: str) -> tuple[dt.date, dt.date]:
    y, m = map(int, month.split("-"))
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, 1), dt.date(y, m, last) + dt.timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claim")
    c.add_argument("token")
    p = sub.add_parser("pull")
    p.add_argument("--month", help="YYYY-MM")
    p.add_argument("--start", type=dt.date.fromisoformat)
    p.add_argument("--end", type=dt.date.fromisoformat, help="exclusive")
    args = ap.parse_args()
    if args.cmd == "claim":
        claim(args.token)
        return
    if args.month:
        start, end = month_range(args.month)
    elif args.start:
        start, end = args.start, args.end or dt.date.today() + dt.timedelta(days=1)
    else:
        ap.error("pull needs --month or --start")
    pull(start, min(end, dt.date.today() + dt.timedelta(days=1)))


if __name__ == "__main__":
    main()
