"""Test-mode data for the static demo page (frontend/demo/build.mjs runs this), so the
demo answers /ai-research exactly like a server in test mode, without one.

    python -m app.ai_research.demo_data
"""
import json

from .api import DISCLAIMER
from .mock import mock_report
from .prompt import PROMPT_VERSION, RESEARCH_PROMPT
from .providers import MockProvider

if __name__ == "__main__":
    info = MockProvider().info()
    print(json.dumps({
        "status": {"mode": info.mode, "provider": info.name, "model": info.model, "configured": info.configured,
                   "missing_settings": info.missing, "prompt_version": PROMPT_VERSION, "prompt": RESEARCH_PROMPT},
        "disclaimer": DISCLAIMER,
        # filled in the page with the chosen verse
        "report_template": mock_report({"surah_name": "{surah_name}", "ayah_number": "{ayah_number}", "text": ""}),
    }, ensure_ascii=False))
