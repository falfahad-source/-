"""Load curated concept maps (backend/curation/<surah>-<ayah>.json) into the DB.

    python -m app.curation              # every file in backend/curation/
    python -m app.curation 24-40.json

A file names a verse's key phrases (by word number), the scientific concepts
they may be compared with, scientific claims about those concepts, and the
phrase -> concept comparisons. The loader enforces the trust rules before
writing anything:
- a claim may carry `verified_at` only together with a `url` and a verbatim
  `quote` from that page; without them it is stored, and shown, as an
  UNVERIFIED_CLAIM;
- every comparison is a POSSIBLE_CONNECTION with review_status "draft" and a
  source (the claim's source, or the file's own provenance document);
- phrase word ranges must lie inside the stored verse.
Re-loading a file replaces what that file loaded before.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import (
    Concept,
    Relationship,
    ScientificEvidence,
    Source,
    Verse,
    VersePhrase,
    WordAnalysis,
)
from .trust import TrustCategory, require_provenance

CURATION_DIR = Path(__file__).resolve().parents[1] / "curation"


class CurationError(ValueError):
    pass


def phrase_entity(surah: int, ayah: int, key: str) -> str:
    return f"phrase:{surah}:{ayah}:{key}"


def validate(doc: dict, verse: Verse | None, word_count: int | None) -> None:
    s, a = doc["verse"]
    if verse is None:
        raise CurationError(f"verse {s}:{a} is not in the database")
    phrases = {p["key"] for p in doc.get("phrases", [])}
    concepts = {c["key"] for c in doc.get("concepts", [])}
    sources = {x["key"] for x in doc.get("sources", [])}
    for p in doc.get("phrases", []):
        lo, hi = p["words"]
        if not (1 <= lo <= hi) or (word_count and hi > word_count):
            raise CurationError(f"phrase {p['key']}: words {lo}-{hi} outside verse {s}:{a} ({word_count} words)")
    for c in doc.get("claims", []):
        if c["concept"] not in concepts or c["source"] not in sources:
            raise CurationError(f"claim refers to unknown concept/source: {c['concept']}/{c['source']}")
        if c.get("verified_at") and not (c.get("url") and c.get("quote")):
            raise CurationError(
                f"claim on {c['concept']} is marked verified without a url and a verbatim quote")
    for r in doc.get("connections", []):
        if r["phrase"] not in phrases or r["concept"] not in concepts:
            raise CurationError(f"connection refers to unknown phrase/concept: {r['phrase']}/{r['concept']}")
        if r.get("source") and r["source"] not in sources:
            raise CurationError(f"connection refers to unknown source: {r['source']}")
        if not r.get("explanation", "").strip():
            raise CurationError(f"connection {r['phrase']}->{r['concept']} has no explanation")


def _source(db: Session, citation: str, **fields) -> Source:
    src = db.query(Source).filter_by(citation_identifier=citation).first()
    if src is None:
        src = Source(citation_identifier=citation, **fields)
        db.add(src)
        db.flush()
    return src


def load_document(db: Session, doc: dict) -> dict[str, int]:
    s, a = doc["verse"]
    verse = db.query(Verse).filter_by(surah_number=s, ayah_number=a, reading="hafs").first()
    word_count = None
    if verse is not None:
        word_count = db.query(WordAnalysis).filter_by(verse_id=verse.id).count() or None
    validate(doc, verse, word_count)

    prov = doc["provenance"]
    doc_source = _source(
        db, prov["key"], title=prov["title"], publisher="مشروع آفاق", author=None,
        source_type="project_document", url="AFAQ.pdf", trust_category=TrustCategory.POSSIBLE_CONNECTION,
    )
    sources: dict[str, Source] = {}
    for x in doc.get("sources", []):
        sources[x["key"]] = _source(
            db, f"curation:{x['key']}", title=x["title"], publisher=x["publisher"], author=None,
            source_type="scientific_org", url=x["url"], trust_category=TrustCategory.UNVERIFIED_CLAIM,
        )

    concepts: dict[str, Concept] = {}
    for c in doc.get("concepts", []):
        row = db.query(Concept).filter_by(key=c["key"]).first() or Concept(key=c["key"], concept_type="scientific")
        row.name_ar, row.name_en, row.description = c["name_ar"], c.get("name_en"), c.get("description")
        db.add(row)
        concepts[c["key"]] = row
    db.flush()

    # replace what this file loaded before
    db.query(VersePhrase).filter_by(verse_id=verse.id).delete()
    db.query(Relationship).filter(Relationship.source_entity.like(f"phrase:{s}:{a}:%")).delete(
        synchronize_session=False)
    concept_ids = [c.id for c in concepts.values()]
    source_ids = [x.id for x in sources.values()]
    if concept_ids and source_ids:
        db.query(ScientificEvidence).filter(
            ScientificEvidence.concept_id.in_(concept_ids), ScientificEvidence.source_id.in_(source_ids)
        ).delete(synchronize_session=False)

    for p in doc.get("phrases", []):
        db.add(VersePhrase(verse_id=verse.id, key=p["key"], label=p["label"],
                           word_from=p["words"][0], word_to=p["words"][1]))
    verified_sources = set()
    for c in doc.get("claims", []):
        verified = dt.datetime.fromisoformat(c["verified_at"]) if c.get("verified_at") else None
        src = sources[c["source"]]
        require_provenance(src.id, "ScientificEvidence")
        db.add(ScientificEvidence(
            concept_id=concepts[c["concept"]].id, source_id=src.id, claim=c["claim"], quote=c.get("quote"),
            url=c.get("url"), publication_date=c.get("publication_date"), scientific_domain=c.get("domain"),
            verified_at=verified, provenance_note=c.get("provenance_note"),
        ))
        if verified:
            verified_sources.add(c["source"])
    for key, src in sources.items():
        # a source counts as scientific only once one of its claims was checked against it
        src.trust_category = TrustCategory.SCIENTIFIC_FACT if key in verified_sources else TrustCategory.UNVERIFIED_CLAIM
    for r in doc.get("connections", []):
        evidence = sources[r["source"]] if r.get("source") else doc_source
        db.add(Relationship(
            source_entity=phrase_entity(s, a, r["phrase"]), target_entity=f"concept:{r['concept']}",
            relationship_type=r.get("type", "comparison"), evidence_source_id=evidence.id,
            trust_category=TrustCategory.POSSIBLE_CONNECTION,
            confidence=0.0,  # not scored; the trust category is what the UI shows
            explanation=r["explanation"], review_status=r.get("review_status", "draft"),
        ))
    db.commit()
    return {"phrases": len(doc.get("phrases", [])), "concepts": len(concepts),
            "claims": len(doc.get("claims", [])), "connections": len(doc.get("connections", []))}


def main(argv: list[str]) -> None:
    files = [CURATION_DIR / f for f in argv] if argv else sorted(CURATION_DIR.glob("*.json"))
    init_db()
    db = SessionLocal()
    try:
        for f in files:
            print(f.name, load_document(db, json.loads(f.read_text(encoding="utf-8"))))
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
