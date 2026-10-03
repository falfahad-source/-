import copy
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.curation import CURATION_DIR, CurationError, load_document
from app.models import (
    Base,
    ScientificEvidence,
    Source,
    TafsirEntry,
    Topic,
    Verse,
    VerseTopic,
    WordAnalysis,
    WordMeaning,
)
from app.rag.answer_builder import build_answer
from app.rag.layers import era_of
from app.trust import TrustCategory

REAL_DOC = json.loads((CURATION_DIR / "24-40.json").read_text(encoding="utf-8"))
# the tests below exercise the rules from an unverified starting point
DOC = copy.deepcopy(REAL_DOC)
for _c in DOC["claims"]:
    _c.update(verified_at=None, quote_origin="search_excerpt")
WORDS = ["أَوْ", "كَظُلُمَاتٍ", "فِي", "بَحْرٍ", "لُجِّيٍّ", "يَغْشَاهُ", "مَوْجٌ", "مِنْ", "فَوْقِهِ", "مَوْجٌ", "مِنْ",
         "فَوْقِهِ", "سَحَابٌ", "ظُلُمَاتٌ", "بَعْضُهَا", "فَوْقَ", "بَعْضٍ", "إِذَا", "أَخْرَجَ", "يَدَهُ", "لَمْ", "يَكَدْ",
         "يَرَاهَا"]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    q = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset", url="u",
               trust_category=TrustCategory.QURANIC_TEXT)
    qac = Source(title="QAC", publisher="QAC", source_type="linguistic_dataset", url="https://corpus.quran.com",
                 trust_category=TrustCategory.TAFSIR_VERIFIED)
    s.add_all([q, qac])
    s.flush()
    v = Verse(surah_number=24, surah_name="النُّورِ", ayah_number=40, arabic_text="أَوۡ كَظُلُمَٰتࣲ ...",
              reading="hafs", source_id=q.id)
    other = Verse(surah_number=25, surah_name="الفُرۡقَانِ", ayah_number=53, arabic_text="...", reading="hafs",
                  source_id=q.id)
    s.add_all([v, other])
    s.flush()
    for i, w in enumerate(WORDS, start=1):
        s.add(WordAnalysis(verse_id=v.id, source_id=qac.id, word_number=i, text=w))

    def book(cid, title, author, year, stype="tafsir_book"):
        src = Source(title=title, publisher="Quranpedia.net", author=author, source_type=stype, url="u",
                     citation_identifier=f"quranpedia:book:{cid}", author_year=year,
                     trust_category=TrustCategory.TAFSIR_VERIFIED)
        s.add(src)
        s.flush()
        return src

    for cid, title, author, year in [(136, "تفسير القرآن العظيم", "ابن كثير", 774), (2012, "التفسير الميسر", "مجمع", None),
                                     (4, "جامع البيان", "الطبري", 310)]:
        s.add(TafsirEntry(verse_id=v.id, source_id=book(cid, title, author, year).id, scholar=author,
                          category="verse_tafsir", original_text=f"تفسير {author}"))
    s.add(TafsirEntry(verse_id=v.id, source_id=book(309, "التبيان", "العكبري", 616, "e3rab_book").id,
                      scholar="العكبري", category="e3rab", original_text="إعراب", is_excerpt=True))
    gharib = book(1424, "كلمات القرآن", "مخلوف", None, "gharib_book")
    s.add_all([WordMeaning(verse_id=v.id, source_id=gharib.id, word_text="بحر لجّي", meaning="عميق كثير الماء"),
               WordMeaning(verse_id=v.id, source_id=gharib.id, word_text="فوقه أي من فوق الموج", meaning="m")])
    s.add_all([Topic(id=897, name="البحار", source_id=q.id), Topic(id=900, name="السَّحاب", source_id=q.id),
               Topic(id=3520, name="الموج", source_id=q.id)])
    s.flush()
    s.add_all([VerseTopic(verse_id=v.id, topic_id=897), VerseTopic(verse_id=other.id, topic_id=897),
               VerseTopic(verse_id=v.id, topic_id=900), VerseTopic(verse_id=v.id, topic_id=3520)])
    s.commit()
    yield s
    s.close()


def test_era_of_centuries_and_groups():
    assert era_of(310, None) == {"year": 310, "century": 4, "century_label": "القرن الرابع الهجري", "era": "المتقدمون"}
    assert era_of(774, None)["era"] == "المتوسطون"
    assert era_of(None, 2012)["era"] == "المعاصرون"
    assert era_of(None, 999)["era"] == "غير محدد"


def test_tafsir_is_chronological_and_excludes_irab(db):
    a = build_answer(db, 24, 40)
    assert [t["scholar"] for t in a.verified_tafsir] == ["الطبري", "ابن كثير", "مجمع"]
    assert a.verified_tafsir[0]["century_label"] == "القرن الرابع الهجري"
    assert all(t["category"] != "e3rab" for t in a.verified_tafsir)
    assert a.linguistic["e3rab"][0]["author"] == "العكبري" and a.linguistic["e3rab"][0]["is_excerpt"] is True
    assert len(a.linguistic["words"]) == len(WORDS) and "corpus.quran.com" in a.linguistic["attribution"]


def test_topics_list_related_verses(db):
    t = next(t for t in build_answer(db, 24, 40).topics if t["name"] == "البحار")
    assert t["related_total"] == 1
    assert t["related"][0] == {"surah_number": 25, "ayah_number": 53, "surah_name": "الفُرۡقَانِ"}


def test_uncurated_verse_says_no_concept_map(db):
    a = build_answer(db, 24, 40)
    assert a.concepts == [] and a.scientific_knowledge == []
    assert any("خريطة مفاهيم" in m for m in a.not_established)
    assert [n["type"] for n in a.graph["nodes"]] == ["verse", "topic", "topic", "topic"]


def test_curated_verse_layers(db):
    load_document(db, DOC)
    a = build_answer(db, 24, 40)
    phrases = {p["key"]: p for p in a.concepts}
    assert phrases["bahr_lujji"]["text"] == "بَحْرٍ لُجِّيٍّ"
    assert [m["meaning"] for m in phrases["bahr_lujji"]["meanings"]] == ["عميق كثير الماء"]
    assert phrases["zulumat"]["meanings"] == []          # «فوق» alone must not pull in the waves entry
    assert phrases["mawj"]["meanings"][0]["meaning"] == "m"
    links = phrases["zulumat"]["connections"]
    assert {c["concept"] for c in links} == {"light_attenuation", "ocean_zones"}
    assert all(c["trust_category"] == "POSSIBLE_CONNECTION" and c["review_status"] == "draft" for c in links)
    assert all("ليست تفسيرًا" in c["label"] for c in a.possible_connections)
    # claims copied from the concept document are not facts until checked against NOAA itself
    claims = [c for s in a.scientific_knowledge for c in s["claims"]]
    assert claims and all(c["trust_category"] == "UNVERIFIED_CLAIM" for c in claims)
    assert any("لم تُطابَق" in m for m in a.not_established)
    types = {n["type"] for n in a.graph["nodes"]}
    assert types == {"verse", "phrase", "concept", "topic"}
    assert all(n["trust_category"] == "UNVERIFIED_CLAIM" for n in a.graph["nodes"] if n["type"] == "concept")


def test_reloading_curation_replaces_rather_than_duplicates(db):
    load_document(db, DOC)
    load_document(db, DOC)
    a = build_answer(db, 24, 40)
    assert len(a.concepts) == len(DOC["phrases"])
    assert db.query(ScientificEvidence).count() == len(DOC["claims"])


def test_verified_claim_requires_url_and_quote(db):
    doc = copy.deepcopy(DOC)
    doc["claims"][0].update(verified_at="2026-10-03", url=None, quote=None)
    with pytest.raises(CurationError, match="without a url and a verbatim quote"):
        load_document(db, doc)
    doc["claims"][0].update(url="https://example.noaa.gov/page", quote="exact words from the page")
    load_document(db, doc)
    a = build_answer(db, 24, 40)
    cats = {s["concept"]: [c["trust_category"] for c in s["claims"]] for s in a.scientific_knowledge}
    assert cats["ocean_zones"] == ["SCIENTIFIC_FACT"] and cats["light_attenuation"] == ["UNVERIFIED_CLAIM"]
    assert db.query(Source).filter_by(citation_identifier="curation:noaa").one().trust_category == \
        TrustCategory.SCIENTIFIC_FACT


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d["phrases"][0].update(words=[20, 99]), "outside verse"),
    (lambda d: d["connections"][0].update(concept="nope"), "unknown phrase/concept"),
    (lambda d: d["connections"][0].update(explanation=" "), "no explanation"),
    (lambda d: d.update(verse=[1, 999]), "not in the database"),
])
def test_invalid_curation_is_rejected_before_writing(db, mutate, match):
    doc = copy.deepcopy(DOC)
    mutate(doc)
    with pytest.raises(CurationError, match=match):
        load_document(db, doc)
    assert db.query(ScientificEvidence).count() == 0


def test_every_curation_file_is_valid_and_uses_allowed_sources():
    from app.curation import allowed_url
    for f in sorted(CURATION_DIR.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        assert f.stem == f"{doc['verse'][0]}-{doc['verse'][1]}", f.name
        for c in doc["claims"]:
            assert c["url"] and allowed_url(c["url"]), (f.name, c["url"])
            assert c["quote"], f.name
            assert not c.get("verified_at") or c.get("quote_origin") == "page", f.name
            assert c.get("quote_origin") in {"page", "page_reading", "search_excerpt"}, f.name


def test_claim_url_outside_allowlist_is_rejected(db):
    doc = copy.deepcopy(DOC)
    doc["claims"][0]["url"] = "https://some-blog.example.com/miracles"
    with pytest.raises(CurationError, match="SCIENTIFIC_SOURCE_ALLOWLIST"):
        load_document(db, doc)


def test_allowed_url_matches_domain_and_subdomains_only():
    from app.curation import allowed_url
    assert allowed_url("https://oceanservice.noaa.gov/facts/x.html")
    assert allowed_url("https://medlineplus.gov/ency/article/000133.htm")
    assert not allowed_url("http://www.noaa.gov/")            # https only
    assert not allowed_url("https://noaa.gov.evil.example/")  # suffix trick
    assert not allowed_url("https://notnasa.gov/")


def test_verify_marks_only_quotes_found_on_the_page():
    from app.curation import verify_document
    doc = copy.deepcopy(DOC)
    doc["claims"][0]["quote"] = "the “sunlight” zone"
    doc["claims"][1]["quote"] = "a sentence that is not there"
    page = "<html><script>var x='the sunlight zone'</script><p>The upper 200 meters is the\n" \
           " &ldquo;sunlight&rdquo;   zone.</p></html>"
    report = dict(verify_document(doc, lambda url: page, today="2026-10-03"))
    assert report == {"ocean_zones": "verified", "light_attenuation": "quote NOT found on page"}
    assert doc["claims"][0]["verified_at"] == "2026-10-03" and doc["claims"][0]["quote_origin"] == "page"
    assert "طوبق" in doc["claims"][0]["provenance_note"]
    assert doc["claims"][1]["verified_at"] is None


def test_verify_reports_fetch_failures_and_keeps_claims_unverified():
    from app.curation import verify_document
    doc = copy.deepcopy(DOC)

    def blocked(url):
        raise ConnectionError("egress blocked")

    report = verify_document(doc, blocked)
    assert all(outcome.startswith("fetch failed") for _, outcome in report)
    assert all(c["verified_at"] is None for c in doc["claims"])


def test_real_curation_file_loads_verified_claims_as_facts(db):
    load_document(db, REAL_DOC)
    a = build_answer(db, 24, 40)
    claims = [c for s in a.scientific_knowledge for c in s["claims"]]
    assert claims and all(c["trust_category"] == "SCIENTIFIC_FACT" and c["verified_at"] for c in claims)
    assert not any("لم تُطابَق" in m for m in a.not_established)


def test_related_comparisons_follow_declared_topics_only(db):
    from app.models import Topic, VerseTopic
    doc = copy.deepcopy(DOC)
    doc["related_topics"] = ["البحار"]
    load_document(db, doc)
    other = db.query(Verse).filter_by(surah_number=25, ayah_number=53).one()
    db.add(Topic(id=5, name="الدِّين", source_id=other.source_id))
    db.flush()
    db.add(VerseTopic(verse_id=other.id, topic_id=5))
    db.commit()
    rel = build_answer(db, 25, 53).related_comparisons
    assert [(r["surah_number"], r["ayah_number"], r["shared_topics"]) for r in rel] == [(24, 40, ["البحار"])]
    assert "تناقص الضوء مع العمق" in rel[0]["concepts"]


def test_related_topic_must_belong_to_the_verse(db):
    doc = copy.deepcopy(DOC)
    doc["related_topics"] = ["موضوع ليس للآية"]
    with pytest.raises(CurationError, match="not one of verse"):
        load_document(db, doc)
