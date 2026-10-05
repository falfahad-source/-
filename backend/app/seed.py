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

import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import tempfile

import requests
from sqlalchemy import create_engine, inspect, text

from .db import sqlalchemy_url


STATUS_FILE = os.environ.get("AFAQ_SEED_STATUS_FILE", os.path.join(tempfile.gettempdir(), "afaq-seed-status.json"))
_steps: list[str] = []


def _log(msg: str) -> None:
    """Printed to the host's log, and kept for GET /health/seed (no URL or password is ever logged)."""
    print(f"[seed] {msg}", flush=True)
    _steps.append(msg)


def _finish(outcome: str) -> int:
    """Record how the seeding ended, for GET /health/seed."""
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as fh:
            json.dump({"outcome": outcome, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "steps": _steps}, fh, ensure_ascii=False)
    except OSError:
        pass
    return 0


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


_FORM = re.compile(r'<form[^>]*id="download-form"[^>]*action="([^"]+)"(.*?)</form>', re.S)
_INPUT = re.compile(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"')


def _get(url: str) -> requests.Response:
    """GET a backup part. Google Drive may answer a server with its "can't scan this file"
    page instead of the file; its download form is then followed to get the file."""
    r = requests.get(direct_link(url), stream=True, timeout=(15, 300))
    if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
        page = r.text
        m = _FORM.search(page)
        if m:
            r.close()
            params = {k: html.unescape(v) for k, v in _INPUT.findall(m.group(2))}
            _log("Google Drive answered with its confirmation page; following its download form.")
            return requests.get(html.unescape(m.group(1)), params=params, stream=True, timeout=(15, 300))
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        raise ValueError("the link returned a web page, not the file"
                         + (f" (page title: {html.unescape(title.group(1)).strip()[:80]})" if title else ""))
    return r


# Settings a newer pg_restore writes that an older server rejects (pg_restore 17, from the
# image's Debian, against PostgreSQL 16 on the host): dropped from the script.
_NEWER_SETTINGS = (b"SET transaction_timeout",)


def restore(path: str, libpq: str) -> tuple[int, str]:
    """Restore a pg_dump backup: pg_restore writes the SQL, psql runs it, stopping at the first
    error. --clean --if-exists: a server that once started without data has created the (empty)
    tables; they are dropped and restored from the backup (only reached with no verses).
    Returns (exit code, first error line); never the command or the URL, which hold the password."""
    dump = subprocess.Popen(["pg_restore", "--clean", "--if-exists", "--no-owner", "--no-acl", "-f", "-", path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    load = subprocess.Popen(["psql", "-q", "-X", "-v", "ON_ERROR_STOP=1", "-d", libpq],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for line in dump.stdout:
            if not line.startswith(_NEWER_SETTINGS):
                load.stdin.write(line)
    except BrokenPipeError:   # psql stopped at an error; its message says which
        pass
    finally:
        try:
            load.stdin.close()
        except BrokenPipeError:
            pass
    load_err, dump_err = load.stderr.read().decode("utf-8", "replace"), dump.stderr.read().decode("utf-8", "replace")
    load_rc, dump_rc = load.wait(), dump.wait()
    lines = [ln for ln in (load_err + "\n" + dump_err).splitlines() if ln.strip()]
    first = next((ln for ln in lines if "error" in ln.lower()), lines[0] if lines else "")
    return (load_rc or dump_rc), first


def main() -> int:
    try:
        return _main()
    except Exception as e:  # noqa: BLE001 - the server must start anyway; the reason is kept for /health/seed
        _log(f"seeding stopped: {type(e).__name__}: {str(e)[:300]}")
        return _finish("error")


def _main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    seed_url = os.environ.get("AFAQ_SEED_URL", "").strip()
    if not db_url:
        _log("DATABASE_URL is not set; nothing to do.")
        return _finish("skipped")
    if has_data(db_url):
        _log("the database already has the verses; nothing to do.")
        return _finish("has_data")
    if not seed_url:
        _log("the database is empty and AFAQ_SEED_URL is not set: the site will run without data.")
        return _finish("no_seed_url")
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as f:
        path = f.name
        urls = [u.strip() for u in seed_url.split(",") if u.strip()]
        size = 0
        for n, url in enumerate(urls, 1):
            _log(f"downloading the backup{f' (part {n} of {len(urls)})' if len(urls) > 1 else ''}...")
            try:
                r = _get(url)
            except (requests.RequestException, ValueError) as e:
                _log(f"part {n}: {e if isinstance(e, ValueError) else type(e).__name__}; the site will run without data.")
                return _finish("download_failed")
            with r:
                if r.status_code != 200:
                    _log(f"part {n}: download failed (HTTP {r.status_code}); the site will run without data.")
                    return _finish("download_failed")
                part = 0
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    part += len(chunk)
            size += part
            _log(f"part {n}: {part / 1e6:.1f} MB")
    _log(f"downloaded {size / 1e6:.1f} MB; restoring...")
    with open(path, "rb") as fh:
        if fh.read(5) != b"PGDMP":
            _log("the file is not a pg_dump backup (is the link a direct download?); the site will run without data.")
            return _finish("not_a_backup")
    libpq = re.sub(r"^postgresql\+\w+://", "postgresql://", db_url)
    rc, err = restore(path, libpq)
    os.unlink(path)
    if rc != 0:
        _log(f"restore failed: {err[:300]}")
        return _finish("restore_failed")
    ok = has_data(db_url)
    _log("restored." if ok else "restore finished but no verses were found.")
    return _finish("restored" if ok else "restore_empty")


if __name__ == "__main__":
    sys.exit(main())
