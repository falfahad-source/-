"""SQLAlchemy models mirroring the "Knowledge model" section of AFAQ_MASTER_SPEC.md.

Field names intentionally match the spec 1:1 so the mapping from spec -> schema is
auditable at a glance.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, relationship

from .trust import TrustCategory

Base = declarative_base()


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    publisher = Column(String, nullable=False)          # e.g. "Quranpedia.net"
    author = Column(String, nullable=True)               # scholar / author if applicable
    source_type = Column(String, nullable=False)          # "quran_api" | "tafsir_book" | "scientific_paper" | ...
    url = Column(String, nullable=False)
    version = Column(String, nullable=True)               # e.g. dump version or API response date
    retrieval_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    trust_category = Column(SAEnum(TrustCategory), nullable=False)
    citation_identifier = Column(String, nullable=True)   # short citable key, e.g. "quranpedia:book:1"
    author_year = Column(Integer, nullable=True)          # author's death year (AH), for ordering by era

    verses = relationship("Verse", back_populates="source")
    tafsir_entries = relationship("TafsirEntry", back_populates="source")


class Verse(Base):
    __tablename__ = "verses"
    __table_args__ = (UniqueConstraint("surah_number", "ayah_number", "reading", name="uq_verse_reading"),)

    id = Column(Integer, primary_key=True)
    surah_number = Column(Integer, nullable=False)
    surah_name = Column(String, nullable=False)
    ayah_number = Column(Integer, nullable=False)
    arabic_text = Column(Text, nullable=False)             # stored verbatim from source, never LLM-generated
    reading = Column(String, nullable=False, default="hafs")  # riwayah
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    # Mushaf layout and plain spelling, when the source provides them (KFGQPC does).
    page_number = Column(Integer, nullable=True)
    juz_number = Column(Integer, nullable=True)
    text_imlaei = Column(Text, nullable=True)  # imla'i spelling, verbatim from source; for search only

    source = relationship("Source", back_populates="verses")
    tafsir_entries = relationship("TafsirEntry", back_populates="verse")


class TafsirEntry(Base):
    __tablename__ = "tafsir_entries"

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    scholar = Column(String, nullable=True)
    category = Column(String, nullable=False)   # surah_intro | rare_words | grammar | general_meaning |
                                                 # verse_tafsir | benefits | scientific_benefit | rhetoric
    original_text = Column(Text, nullable=False)        # verbatim, never invented
    normalized_summary = Column(Text, nullable=True)     # optional LLM-assisted summary, clearly separate from original_text
    source_location = Column(String, nullable=True)      # page/part reference
    disagreement_group = Column(String, nullable=True)   # groups entries that represent differing views of the same verse
    # True: original_text is this ayah's passage cut from a page-based chunk; False: the whole
    # chunk (may cover neighbouring ayahs); None: entry was stored per ayah by the source.
    is_excerpt = Column(Boolean, nullable=True)

    verse = relationship("Verse", back_populates="tafsir_entries")
    source = relationship("Source", back_populates="tafsir_entries")


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=True)            # stable curation key, e.g. "light_attenuation"
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    concept_type = Column(String, nullable=False)  # "quranic" | "scientific"


class ScientificEvidence(Base):
    """A scientific statement and where it comes from (spec: "Scientific sources").

    It counts as SCIENTIFIC_FACT only once `verified_at` is set, which requires a
    URL and a verbatim `quote` from that page (see app.curation). Until then it is
    shown as UNVERIFIED_CLAIM, so a claim copied from a secondary document never
    silently passes as an established fact.
    """
    __tablename__ = "scientific_claims"

    id = Column(Integer, primary_key=True)
    concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    claim = Column(Text, nullable=False)                 # Arabic statement shown to users
    quote = Column(Text, nullable=True)                  # verbatim excerpt from the source page
    url = Column(String, nullable=True)
    publication_date = Column(String, nullable=True)
    scientific_domain = Column(String, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    provenance_note = Column(Text, nullable=True)        # e.g. "cited in the AFAQ concept document"

    concept = relationship("Concept")
    source = relationship("Source")

    @property
    def trust_category(self) -> TrustCategory:
        return TrustCategory.SCIENTIFIC_FACT if self.verified_at else TrustCategory.UNVERIFIED_CLAIM


class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True)
    source_entity = Column(String, nullable=False)   # e.g. "verse:2:255"
    target_entity = Column(String, nullable=False)    # e.g. "concept:light_attenuation"
    relationship_type = Column(String, nullable=False)
    evidence_source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    trust_category = Column(SAEnum(TrustCategory), nullable=False)
    confidence = Column(Float, nullable=False)   # 0..1
    explanation = Column(Text, nullable=False)
    # "draft" until a researcher reviews the comparison; shown on the card either way.
    review_status = Column(String, nullable=True, default="draft")

    evidence_source = relationship("Source")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    claim_type = Column(String, nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)  # nullable only for status=UNVERIFIED
    evidence = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    status = Column(SAEnum(TrustCategory), nullable=False, default=TrustCategory.UNVERIFIED_CLAIM)


class HadithEntry(Base):
    """A hadith returned by a Dorar.net keyword search run for a verse.

    The link to the verse is only a text match on the search query, so it is
    always presented as a POSSIBLE_CONNECTION, never as tafsir. The scholar's
    grade (hukm) is stored verbatim and must be shown with the text: results
    include weak and fabricated narrations.
    """
    __tablename__ = "hadith_entries"
    __table_args__ = (
        UniqueConstraint("verse_id", "search_query", "result_rank", name="uq_hadith_verse_query_rank"),
    )

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    search_query = Column(String, nullable=False)       # the exact skey sent to the API
    result_rank = Column(Integer, nullable=False)       # 1-based position in the API response
    text = Column(Text, nullable=False)                 # hadith text, tags stripped, wording verbatim
    narrator = Column(String, nullable=True)            # الراوي
    muhaddith = Column(String, nullable=True)           # المحدث
    book = Column(String, nullable=True)                # المصدر
    reference = Column(String, nullable=True)           # الصفحة أو الرقم
    grade = Column(Text, nullable=True)                 # خلاصة حكم المحدث, verbatim
    raw_html = Column(Text, nullable=False)             # the API's HTML block for this hadith, for audit
    trust_category = Column(SAEnum(TrustCategory), nullable=False, default=TrustCategory.POSSIBLE_CONNECTION)

    verse = relationship("Verse")
    source = relationship("Source")


class WordAnalysis(Base):
    """Per-word morphology (Quranic Arabic Corpus via Quranpedia; GPL, attribution required)."""
    __tablename__ = "word_analyses"
    __table_args__ = (UniqueConstraint("verse_id", "word_number", name="uq_word_analysis"),)

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    word_number = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    root = Column(String, nullable=True)
    lemma = Column(String, nullable=True)
    pos = Column(String, nullable=True)            # part of speech of the stem
    description = Column(Text, nullable=True)      # the corpus' Arabic description of each segment
    translation_en = Column(String, nullable=True)

    verse = relationship("Verse")
    source = relationship("Source")


class WordMeaning(Base):
    """Meaning of a word or phrase from a غريب القرآن book, verbatim."""
    __tablename__ = "word_meanings"

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    word_text = Column(String, nullable=False)
    meaning = Column(Text, nullable=False)

    verse = relationship("Verse")
    source = relationship("Source")


class Topic(Base):
    """A Quranic topic from Quranpedia's index (e.g. البحار، السحاب)."""
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True)          # Quranpedia topic id
    name = Column(String, nullable=False)
    parent_name = Column(String, nullable=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)


class VerseTopic(Base):
    __tablename__ = "verse_topics"
    __table_args__ = (UniqueConstraint("verse_id", "topic_id", name="uq_verse_topic"),)

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)

    topic = relationship("Topic")


class VersePhrase(Base):
    """A key phrase of a verse that the concept map expands (e.g. «بحر لجي» in 24:40).

    Words are referenced by number so the phrase always points at the stored
    verse text; its meaning comes from WordMeaning rows that share its words,
    never from text written into this table.
    """
    __tablename__ = "verse_phrases"
    __table_args__ = (UniqueConstraint("verse_id", "key", name="uq_verse_phrase"),)

    id = Column(Integer, primary_key=True)
    verse_id = Column(Integer, ForeignKey("verses.id"), nullable=False)
    key = Column(String, nullable=False)            # stable id within the verse, e.g. "bahr_lujji"
    label = Column(String, nullable=False)          # display label, e.g. "بحر لجي"
    word_from = Column(Integer, nullable=False)
    word_to = Column(Integer, nullable=False)

    verse = relationship("Verse")
