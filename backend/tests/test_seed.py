from app import main
from app.seed import direct_link


def test_dropbox_share_links_become_direct_downloads():
    assert direct_link("https://www.dropbox.com/s/x/afaq.dump?dl=0") == "https://www.dropbox.com/s/x/afaq.dump?dl=1"
    assert direct_link("https://www.dropbox.com/scl/fi/x/afaq.dump?rlkey=k&dl=0") == "https://www.dropbox.com/scl/fi/x/afaq.dump?rlkey=k&dl=1"
    assert direct_link("https://www.dropbox.com/scl/fi/x/afaq.dump?rlkey=k") == "https://www.dropbox.com/scl/fi/x/afaq.dump?rlkey=k&dl=1"
    assert direct_link("https://example.com/afaq.dump") == "https://example.com/afaq.dump"


def test_cors_origin_bare_host_gets_https(monkeypatch):
    import importlib
    monkeypatch.setenv("AFAQ_CORS_ORIGINS", "afaq-web.onrender.com, http://localhost:3000/")
    try:
        assert importlib.reload(main).CORS_ORIGINS == ["https://afaq-web.onrender.com", "http://localhost:3000"]
    finally:
        monkeypatch.delenv("AFAQ_CORS_ORIGINS")
        importlib.reload(main)


def test_host_database_urls_use_psycopg2():
    from app.db import sqlalchemy_url
    assert sqlalchemy_url("postgresql://u:p@h:5432/d") == "postgresql+psycopg2://u:p@h:5432/d"
    assert sqlalchemy_url("postgres://u:p@h/d") == "postgresql+psycopg2://u:p@h/d"
    assert sqlalchemy_url("postgresql+psycopg2://u:p@h/d") == "postgresql+psycopg2://u:p@h/d"
    assert sqlalchemy_url("sqlite://") == "sqlite://"


class _Resp:
    def __init__(self, body: bytes, ctype="application/octet-stream", status=200):
        self.status_code, self._body = status, body
        self.headers = {"content-type": ctype}
        self.text = body.decode("utf-8", "replace")

    def iter_content(self, n):
        yield self._body

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


DRIVE_PAGE = (b'<html><title>Google Drive - Virus scan warning</title><form id="download-form" '
              b'action="https://drive.usercontent.google.com/download" method="get">'
              b'<input type="hidden" name="id" value="F1"><input type="hidden" name="export" value="download">'
              b'<input type="hidden" name="confirm" value="t"><input type="hidden" name="uuid" value="u-1"></form></html>')


def _seed(monkeypatch, tmp_path, responses, restore_rc=0):
    from app import seed
    calls, verses = [], iter([False, restore_rc == 0])
    monkeypatch.setattr(seed, "STATUS_FILE", str(tmp_path / "status.json"))
    monkeypatch.setattr(seed, "_steps", [])
    monkeypatch.setattr(seed, "has_data", lambda url: next(verses))
    monkeypatch.setattr(seed.requests, "get", lambda url, **kw: (calls.append((url, kw.get("params"))), responses.pop(0))[1])
    monkeypatch.setattr(seed, "restore", lambda path, url: (restore_rc, "pg_restore: error: boom" if restore_rc else ""))
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
    monkeypatch.setenv("AFAQ_SEED_URL", "https://drive.usercontent.google.com/download?id=F1&export=download&confirm=t")
    seed.main()
    import json
    return json.loads((tmp_path / "status.json").read_text()), calls


def test_seed_follows_the_google_drive_confirmation_page(monkeypatch, tmp_path):
    status, calls = _seed(monkeypatch, tmp_path, [_Resp(DRIVE_PAGE, "text/html; charset=utf-8"), _Resp(b"PGDMP" + b"x" * 10)])
    assert status["outcome"] == "restored"
    assert calls[1] == ("https://drive.usercontent.google.com/download", {"id": "F1", "export": "download", "confirm": "t", "uuid": "u-1"})
    assert any("confirmation page" in s for s in status["steps"])


def test_seed_reports_a_web_page_instead_of_the_file(monkeypatch, tmp_path):
    page = b"<html><title>Google Drive - Quota exceeded</title><body>Too many users</body></html>"
    status, _ = _seed(monkeypatch, tmp_path, [_Resp(page, "text/html")])
    assert status["outcome"] == "download_failed" and "Quota exceeded" in " ".join(status["steps"])


def test_seed_reports_restore_errors_without_secrets(monkeypatch, tmp_path):
    status, _ = _seed(monkeypatch, tmp_path, [_Resp(b"PGDMP" + b"x" * 10)], restore_rc=1)
    text = " ".join(status["steps"])
    assert status["outcome"] == "restore_failed" and "pg_restore: error: boom" in text and "u:p@h" not in text


def test_seed_status_page(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app import seed
    monkeypatch.setattr(seed, "STATUS_FILE", str(tmp_path / "none.json"))
    monkeypatch.setenv("RENDER_GIT_COMMIT", "9260f9db5d970cb5ad1eac299dc3f039c596d91b")
    r = TestClient(main.app).get("/health/seed").json()
    assert r["outcome"] == "unknown" and r["commit"] == "9260f9d" and "verses" in r


def test_restore_drops_settings_an_older_server_rejects(monkeypatch, tmp_path):
    """pg_restore 17 writes SET transaction_timeout, which PostgreSQL 16 rejects: the line is
    dropped and the rest reaches psql unchanged."""
    import io

    from app import seed
    sent = io.BytesIO()

    class Proc:
        def __init__(self, args, **kw):
            self.args = args
            self.stdout = io.BytesIO(b"SET statement_timeout = 0;\nSET transaction_timeout = 0;\nCREATE TABLE verses ();\n")
            self.stderr = io.BytesIO(b"")
            self.stdin = sent if args[0] == "psql" else None

        def wait(self):
            return 0

    monkeypatch.setattr(sent, "close", lambda: None)
    monkeypatch.setattr(seed.subprocess, "Popen", Proc)
    assert seed.restore("x.dump", "postgresql://u:p@h/d") == (0, "")
    assert sent.getvalue() == b"SET statement_timeout = 0;\nCREATE TABLE verses ();\n"
