"""SQLAlchemy models mirroring the "Knowledge model" section of AFAQ_MASTER_SPEC.md.

Field names intentionally match the spec 1:1 so the mapping from spec -> schema is
auditable at a glance.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
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

    verse = relationship("Verse", back_populates="tafsir_entries")
    source = relationship("Source", back_populates="tafsir_entries")


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(Integer, primary_key=True)
    name_ar = Column(String, nullable=False)
    name_en = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    concept_type = Column(String, nullable=False)  # "quranic" | "scientific"


class ScientificEvidence(Base):
    __tablename__ = "scientific_evidence"

    id = Column(Integer, primary_key=True)
    concept_id = Column(Integer, ForeignKey("concepts.id"), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False)
    claim = Column(Text, nullable=False)
    evidence = Column(Text, nullable=False)
    publication_date = Column(String, nullable=True)
    url = Column(String, nullable=False)
    scientific_domain = Column(String, nullable=True)


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
