"""Test-mode data for the static demo page (frontend/demo/build.mjs runs this), so the
demo answers /ai-research exactly like a server in test mode, without one. Reports a
connected platform produced and stored in the database (ai_reports, current prompt
version) are included as they are, so the demo can show real output; it never makes one.

    python -m app.ai_research.demo_data
"""
import json

from .api import DISCLAIMER
from .mock import mock_data
from .prompt import PROMPT_VERSION
from .providers import MockProvider
from .report import render
from .topic import MOCK_NOTE

def saved_reports() -> list[dict]:
    """Stored reports of the current prompt version, as GET /ai-research/report returns them."""
    try:
        from ..db import SessionLocal
        from ..models import AiReport, Verse
        from .api import _from_row
        db = SessionLocal()
    except Exception:  # noqa: BLE001 - no database: the demo has the test report only
        return []
    try:
        out = []
        for row in db.query(AiReport).filter_by(prompt_version=PROMPT_VERSION):
            v = db.query(Verse).filter_by(surah_number=row.surah_number, ayah_number=row.ayah_number, reading="hafs").one()
            info = type("Info", (), {"mode": "live", "name": "OpenAI (Responses API)" if row.model.startswith("gpt") else "منصة متصلة",
                                     "model": row.model})
            out.append(_from_row({"surah_number": v.surah_number, "ayah_number": v.ayah_number,
                                  "surah_name": v.surah_name, "text": v.arabic_text}, info, row))
        return out
    except Exception:  # noqa: BLE001
        return []
    finally:
        db.close()


if __name__ == "__main__":
    info = MockProvider().info()
    print(json.dumps({
        "status": {"mode": info.mode, "provider": info.name, "model": info.model, "configured": info.configured,
                   "missing_settings": info.missing, "tools": info.tools, "prompt_version": PROMPT_VERSION},
        "disclaimer": DISCLAIMER,
        "topic_note": MOCK_NOTE,
        "saved": saved_reports(),
        # filled in the page with the chosen verse
        "report_template": render(mock_data(v := {"surah_name": "{surah_name}", "ayah_number": "{ayah_number}",
                                                  "text": "{text}"}), v, mock=True),
    }, ensure_ascii=False))
