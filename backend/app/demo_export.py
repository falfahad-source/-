"""Export the data for the static demo page (frontend/demo, see its build.mjs).

    python -m app.demo_export ../frontend/demo/data.json

Full answers (every layer) for the verses that have a curated concept map, the
text of all verses for client-side search, and the /explore list. Answers for
other verses are built in the page with the text only, so the file stays small.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from .db import SessionLocal, init_db
from .main import explore
from .models import Verse, VersePhrase
from .rag.answer_builder import build_answer


def export(path: Path) -> dict:
    init_db()
    db = SessionLocal()
    try:
        model = sorted({(v.surah_number, v.ayah_number)
                        for v in db.query(Verse).join(VersePhrase, VersePhrase.verse_id == Verse.id)})
        answers = {f"{s}:{a}": dataclasses.asdict(build_answer(db, s, a)) for s, a in model}
        verses = [[v.surah_number, v.ayah_number, v.surah_name, v.arabic_text, v.text_imlaei or "",
                   v.page_number, v.juz_number]
                  for v in db.query(Verse).filter_by(reading="hafs").order_by(Verse.surah_number, Verse.ayah_number)]
    finally:
        db.close()
    data = {"answers": answers, "verses": verses, "explore": explore()}
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"model_verses": len(answers), "verses": len(verses), "bytes": path.stat().st_size}


if __name__ == "__main__":
    print(export(Path(sys.argv[1] if len(sys.argv) > 1 else "../frontend/demo/data.json")))
