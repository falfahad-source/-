"""Fill an empty database from a backup, once, when the server first starts on a host.

AFAQ's data (KFGQPC Quran text, Quranpedia tafsir and topics, i'jaz article links, the
curated comparisons) is not in git. On a new server, set AFAQ_SEED_URL to a direct
download link of a backup made with

    pg_dump -Fc --no-owner --no-acl -d <local database> -f afaq.dump

and start: if the database has no verses yet, the backup is downloaded and restored.
A backup split into parts (split -b 14m afaq.dump afaq.dump.part-) is given as their links
separated by commas, in order; the parts are joined as they download.
Later starts find the verses and do nothing. Dropbox share links (?dl=0) are turned into
direct downloads (?dl=1).

    python -m app.seed
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import requests
from sqlalchemy import create_engine, inspect, text

from .db import sqlalchemy_url


def _log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def direct_link(url: str) -> str:
    """A share link as a direct download (Dropbox: dl=1)."""
    if "dropbox.com" in url:
        url = re.sub(r"([?&])dl=0", r"\1dl=1", url)
        if "dl=1" not in url and "raw=1" not in url:
            url += ("&" if "?" in url else "?") + "dl=1"
    return url


def has_data(db_url: str) -> bool:
    engine = create_engine(sqlalchemy_url(db_url))
    try:
        if "verses" not in inspect(engine).get_table_names():
            return False
        with engine.connect() as c:
            return (c.execute(text("select count(*) from verses")).scalar() or 0) > 0
    finally:
        engine.dispose()


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    seed_url = os.environ.get("AFAQ_SEED_URL", "").strip()
    if not db_url:
        _log("DATABASE_URL is not set; nothing to do.")
        return 0
    if has_data(db_url):
        _log("the database already has the verses; nothing to do.")
        return 0
    if not seed_url:
        _log("the database is empty and AFAQ_SEED_URL is not set: the site will run without data.")
        return 0
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as f:
        path = f.name
        urls = [u.strip() for u in seed_url.split(",") if u.strip()]
        size = 0
        for n, url in enumerate(urls, 1):
            _log(f"downloading the backup{f' (part {n} of {len(urls)})' if len(urls) > 1 else ''}...")
            with requests.get(direct_link(url), stream=True, timeout=(15, 300)) as r:
                if r.status_code != 200:
                    _log(f"download failed (HTTP {r.status_code}); the site will run without data.")
                    return 0
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    size += len(chunk)
    _log(f"downloaded {size / 1e6:.1f} MB; restoring...")
    with open(path, "rb") as fh:
        if fh.read(5) != b"PGDMP":
            _log("the file is not a pg_dump backup (is the link a direct download?); the site will run without data.")
            return 0
    libpq = re.sub(r"^postgresql\+\w+://", "postgresql://", db_url)
    # --clean --if-exists: a server that once started without data has created the (empty)
    # tables; they are dropped and restored from the backup. Only reached with no verses.
    done = subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-acl", "--exit-on-error",
                           "-d", libpq, path], capture_output=True, text=True)
    os.unlink(path)
    if done.returncode != 0:
        # the first error line, never the command or the URL: they hold the database password
        lines = done.stderr.strip().splitlines()
        err = next((ln for ln in lines if "error" in ln.lower()), lines[-1] if lines else "")
        _log(f"restore failed: {err[:300]}")
        return 0
    _log("restored." if has_data(db_url) else "restore finished but no verses were found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
