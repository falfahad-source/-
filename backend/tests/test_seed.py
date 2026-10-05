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
