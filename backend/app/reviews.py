"""Researcher review of the curated comparisons (POSSIBLE_CONNECTION).

The concept document makes comparisons the researcher's work, so each one is a
draft until a reviewer approves it. Reviewers are configured in the environment,
never in code or the database:

    AFAQ_REVIEWERS="name:token;other name:other-token"

and send `Authorization: Bearer <token>`. Decisions:
- approved           — shown with the reviewer's name and date; an edited text
                       replaces the curated one;
- changes_requested  — still shown as a draft ("under review"), with the comment
                       kept for the curator;
- rejected           — hidden from the public answer.
A decision holds only while the comparison's current text is the text reviewed
(or approved); editing the curation file sends it back to "draft".

    python -m app.reviews --export   # write effective decisions into curation/*.json
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from .models import ConnectionReview, Relationship

DECISIONS = ("approved", "changes_requested", "rejected")


def connection_key(source_entity: str, target_entity: str) -> str:
    """"phrase:24:40:zulumat" + "concept:ocean_zones" -> "24:40:zulumat->ocean_zones"."""
    return f"{source_entity.removeprefix('phrase:')}->{target_entity.removeprefix('concept:')}"


def reviewers_from_env(value: str | None = None) -> dict[str, str]:
    """{token: name} from AFAQ_REVIEWERS ("name:token;name:token")."""
    raw = os.environ.get("AFAQ_REVIEWERS", "") if value is None else value
    out = {}
    for item in raw.split(";"):
        name, sep, token = item.strip().rpartition(":")
        if sep and name.strip() and len(token.strip()) >= 16:
            out[token.strip()] = name.strip()
    return out


def reviewer_for(token: str | None, reviewers: dict[str, str]) -> str | None:
    if not token:
        return None
    for known, name in reviewers.items():
        if hmac.compare_digest(known.encode(), token.encode()):
            return name
    return None


@dataclass
class Effective:
    status: str                  # draft | approved | changes_requested | rejected
    explanation: str
    reviewer: str | None = None
    reviewed_at: str | None = None
    comment: str | None = None


def effective(db: Session, rel: Relationship) -> Effective:
    """The comparison's current review state, from the latest valid DB review,
    else from the decision exported into its curation file."""
    key = connection_key(rel.source_entity, rel.target_entity)
    latest = (db.query(ConnectionReview).filter_by(connection_key=key)
              .order_by(ConnectionReview.created_at.desc(), ConnectionReview.id.desc()).first())
    if latest and rel.explanation in {latest.reviewed_text, latest.approved_text}:
        text = latest.approved_text if latest.decision == "approved" and latest.approved_text else rel.explanation
        return Effective(latest.decision, text, latest.reviewer, latest.created_at.date().isoformat(), latest.comment)
    status = rel.review_status if rel.review_status in DECISIONS else "draft"
    return Effective(status, rel.explanation, rel.reviewed_by, rel.reviewed_at)


def submit(db: Session, rel: Relationship, reviewer: str, decision: str, comment: str | None,
           explanation: str | None, now: dt.datetime | None = None) -> ConnectionReview:
    if decision not in DECISIONS:
        raise ValueError("القرار يجب أن يكون: approved أو changes_requested أو rejected")
    comment = (comment or "").strip() or None
    if decision != "approved" and not comment:
        raise ValueError("اكتب ملاحظة توضح سبب طلب التعديل أو الرفض.")
    edited = (explanation or "").strip()
    if decision == "approved" and explanation is not None and not edited:
        raise ValueError("نص المقارنة المعتمد لا يكون فارغًا.")
    current = effective(db, rel)
    review = ConnectionReview(
        connection_key=connection_key(rel.source_entity, rel.target_entity), reviewer=reviewer,
        decision=decision, comment=comment, reviewed_text=rel.explanation,
        approved_text=(edited or current.explanation) if decision == "approved" else None,
        created_at=now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),  # naive UTC, matches column
    )
    db.add(review)
    db.commit()
    return review


def history(db: Session, key: str) -> list[dict]:
    return [{"reviewer": r.reviewer, "decision": r.decision, "comment": r.comment,
             "approved_text": r.approved_text, "at": r.created_at.isoformat(timespec="minutes")}
            for r in db.query(ConnectionReview).filter_by(connection_key=key)
            .order_by(ConnectionReview.created_at.desc(), ConnectionReview.id.desc())]


def export_to_curation(db: Session, curation_dir: Path) -> int:
    """Write each comparison's effective decision into its curation file, so the
    decisions are version-controlled. Approved edits replace the explanation."""
    changed = 0
    for f in sorted(curation_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        s, a = doc["verse"]
        dirty = False
        for c in doc.get("connections", []):
            rel = (db.query(Relationship)
                   .filter_by(source_entity=f"phrase:{s}:{a}:{c['phrase']}", target_entity=f"concept:{c['concept']}")
                   .first())
            if rel is None:
                continue
            eff = effective(db, rel)
            # an unreviewed comparison carries no review fields; "draft" is the default
            want = ({"review_status": None, "reviewed_by": None, "reviewed_at": None} if eff.status == "draft"
                    else {"review_status": eff.status, "reviewed_by": eff.reviewer, "reviewed_at": eff.reviewed_at})
            if eff.status == "approved" and eff.explanation != c["explanation"]:
                c["explanation"] = eff.explanation
                dirty = True
            for k, v in want.items():
                if c.get(k) != v:
                    if v is None:
                        c.pop(k, None)
                    else:
                        c[k] = v
                    dirty = True
        if dirty:
            f.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
    return changed


def main(argv: list[str]) -> None:
    from .curation import CURATION_DIR
    from .db import SessionLocal, init_db

    if "--export" not in argv:
        print(__doc__)
        return
    init_db()
    db = SessionLocal()
    try:
        print(f"updated {export_to_curation(db, CURATION_DIR)} curation files")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
