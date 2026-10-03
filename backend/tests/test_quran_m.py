import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.ingest_quran_m import EXCERPT_CHARS, excerpt_of, import_posts
from app.models import ArticleVerse, Base, ExternalArticle, Source, Verse
from app.rag.answer_builder import build_answer
from app.trust import TrustCategory

VERSES = [  # (surah, name, ayah, uthmani, imlaei) — real KFGQPC strings
    (21, "الأَنبِيَاءِ", 33, "وَهُوَ ٱلَّذِي خَلَقَ ٱلَّيۡلَ وَٱلنَّهَارَ وَٱلشَّمۡسَ وَٱلۡقَمَرَۖ كُلࣱّ فِي فَلَكࣲ يَسۡبَحُونَ ۝٣٣",
     "وهو الذي خلق الليل والنهار والشمس والقمر كل في فلك يسبحون"),
    (36, "يسٓ", 40, "لَا ٱلشَّمۡسُ يَنۢبَغِي لَهَآ أَن تُدۡرِكَ ٱلۡقَمَرَ وَلَا ٱلَّيۡلُ سَابِقُ ٱلنَّهَارِۚ وَكُلࣱّ فِي فَلَكࣲ يَسۡبَحُونَ ۝٤٠",
     "لا الشمس ينبغي لها أن تدرك القمر ولا الليل سابق النهار وكل في فلك يسبحون"),
    (27, "النَّمۡلِ", 18, "حَتَّىٰٓ إِذَآ أَتَوۡاْ عَلَىٰ وَادِ ٱلنَّمۡلِ ... ۝١٨", "حتى إذا أتوا على واد النمل"),
    (27, "النَّمۡلِ", 19, "فَتَبَسَّمَ ضَاحِكࣰا ... ۝١٩", "فتبسم ضاحكا من قولها"),
]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    src = Source(title="KFGQPC", publisher="KFGQPC", source_type="quran_dataset", url="u",
                 trust_category=TrustCategory.QURANIC_TEXT)
    s.add(src)
    s.flush()
    for sn, name, a, text, iml in VERSES:
        s.add(Verse(surah_number=sn, surah_name=name, ayah_number=a, arabic_text=text, text_imlaei=iml,
                    reading="hafs", source_id=src.id))
    s.commit()
    yield s
    s.close()


def post(pid, title, content, excerpt=""):
    return {"id": pid, "link": f"https://quran-m.com/p{pid}/", "title": {"rendered": title}, "date": "2026-09-01T10:00:00",
            "categories": [7], "excerpt": {"rendered": excerpt}, "content": {"rendered": content}}


def links(db, pid):
    art = db.query(ExternalArticle).filter_by(external_id=pid).one()
    return sorted((db.get(Verse, x.verse_id).surah_number, db.get(Verse, x.verse_id).ayah_number, x.match_method)
                  for x in db.query(ArticleVerse).filter_by(article_id=art.id))


def test_citations_with_ranges_and_quotes_are_linked(db):
    content = ("<p>قال تعالى: ﴿كُلٌّ فِي فَلَكٍ يَسْبَحُونَ﴾ وفي النمل <b>[النمل: ١٨-١٩]</b>"
               " وأيضًا (سورة البقرة: 999) و[المجهولة: 3]</p>")
    assert import_posts(db, [post(1, "عنوان", content)], {7: "الاعجاز العلمي في القرآن"}) == (1, 4)
    assert links(db, 1) == [(21, 33, "quote"), (27, 18, "citation"), (27, 19, "citation"), (36, 40, "quote")]
    art = db.query(ExternalArticle).one()
    assert art.categories == "الاعجاز العلمي في القرآن" and art.published == "2026-09-01"


def test_short_or_too_common_quotes_are_not_linked(db):
    import_posts(db, [post(2, "t", "﴿فِي فَلَكٍ﴾ ﴿وَهُوَ﴾")], {})
    assert links(db, 2) == []  # under 3 words


def test_reimport_refreshes_links_without_duplicating(db):
    import_posts(db, [post(3, "t", "[النمل: 18]")], {})
    assert import_posts(db, [post(3, "t2", "[النمل: 19]")], {}) == (0, 1)
    assert links(db, 3) == [(27, 19, "citation")]
    assert db.query(ExternalArticle).one().title == "t2"


def test_only_a_short_excerpt_is_stored_never_the_article():
    long = "كلمة " * 400
    ex = excerpt_of(post(4, "t", f"<p>{long}</p>"))
    assert len(ex) <= EXCERPT_CHARS + 1 and ex.endswith("…")
    assert excerpt_of(post(5, "t", "x", excerpt="<p>ملخص الموقع [&hellip;]</p>")) == "ملخص الموقع"


def test_answer_ranks_focused_articles_first_and_labels_them(db):
    survey = "".join(f"[النمل: {a}]" for a in (18, 19)) + "﴿كُلٌّ فِي فَلَكٍ يَسْبَحُونَ﴾" + "".join(
        f"[الأنبياء: {a}]" for a in range(1, 8))
    import_posts(db, [post(10, "مقال مسحي", survey),
                      post(11, "“كُلٌّ فِي فَلَكٍ يَسْبَحُونَ” بين التفسير والفلك", "﴿كُلٌّ فِي فَلَكٍ يَسْبَحُونَ﴾")], {})
    a = build_answer(db, 21, 33)
    assert a.ijaz["total"] == 2
    assert [x["title"][:6] for x in a.ijaz["articles"]] == ["“كُلٌّ", "مقال م"]
    assert a.ijaz["articles"][0]["focused"] is True
    assert all(x["trust_category"] == "POSSIBLE_CONNECTION" for x in a.ijaz["articles"])
    assert "لم يتحقق آفاق" in a.ijaz["label"]
    assert a.verified_tafsir == []  # never merged into tafsir
