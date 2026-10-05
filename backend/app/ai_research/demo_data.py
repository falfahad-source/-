"""Test-mode data for the static demo page (frontend/demo/build.mjs runs this), so the
demo answers /ai-research exactly like a server in test mode, without one.

    python -m app.ai_research.demo_data
"""
import json

from .api import DISCLAIMER
from .mock import mock_data
from .prompt import PROMPT_VERSION, RESEARCH_PROMPT
from .providers import MockProvider
from .report import render
from .topic import MOCK_NOTE

if __name__ == "__main__":
    info = MockProvider().info()
    print(json.dumps({
        "status": {"mode": info.mode, "provider": info.name, "model": info.model, "configured": info.configured,
                   "missing_settings": info.missing, "tools": info.tools, "prompt_version": PROMPT_VERSION,
                   "prompt": RESEARCH_PROMPT},
        "disclaimer": DISCLAIMER,
        "topic_note": MOCK_NOTE,
        # filled in the page with the chosen verse
        "report_template": render(mock_data(v := {"surah_name": "{surah_name}", "ayah_number": "{ayah_number}",
                                                  "text": "{text}"}), v, mock=True),
    }, ensure_ascii=False))
