"""Central configuration, including the scientific-source allowlist required by
AFAQ_MASTER_SPEC.md ("Scientific sources"). This list is intentionally short and
must be extended deliberately — the ingestion layer should reject any scientific
source whose domain is not in this list rather than silently accepting it.
"""

QURANPEDIA_API_BASE = "https://api.quranpedia.net/v1"
QURANPEDIA_LICENSE_URL = "https://quranpedia.net/dumps/LICENSE.md"
QURANPEDIA_DUMPS_URL = "https://quranpedia.net/dumps"

# Default Hafs mushaf id, per /mushafs listing.
DEFAULT_MUSHAF_ID = 1

# Scientific sources are for scientific knowledge/comparison only — never
# automatic tafsir (spec rule). Extend deliberately; do not widen silently.
SCIENTIFIC_SOURCE_ALLOWLIST: list[str] = [
    # Government scientific agencies used by the curated comparisons. A claim URL must
    # be on one of these domains (or a subdomain); extend deliberately, with the owner.
    "nasa.gov", "noaa.gov", "usgs.gov", "nih.gov", "medlineplus.gov", "usda.gov",
]

# Minimum confidence required before a Relationship may be labeled POSSIBLE_CONNECTION
# in an answer (still always shown with the explicit disclaimer regardless of score).
MIN_CONNECTION_CONFIDENCE = 0.0

# Quranpedia tafsir books left out of the default (`fundamental`) selection.
# They can still be requested explicitly with --books.
EXCLUDED_DEFAULT_TAFSIR_BOOKS: dict[int, str] = {
    # Quranpedia lists two editions of Ibn Kathir's تفسير القرآن العظيم as fundamental.
    # Keep 136 (دار طيبة، تحقيق سامي سلامة — the standard critical edition, text starts
    # at its ayah); drop 331 (دار الكتب العلمية), whose page-based chunks spill over
    # from neighbouring ayahs (e.g. its 2:255 entry opens with the end of 2:254).
    331: "duplicate Ibn Kathir edition; 136 is kept",
}

# Tafsir books whose author has no death year in Quranpedia's index but which are
# contemporary works, so the era timeline can place them instead of "unknown".
CONTEMPORARY_TAFSIR_BOOKS: dict[int, str] = {
    2012: "التفسير الميسر — مجمع الملك فهد (نُشر 1419هـ)",
    2003: "المختصر في تفسير القرآن الكريم — مركز تفسير للدراسات القرآنية",
    305: "الصحيح المسبور من التفسير بالمأثور — حكمت بشير ياسين",
}
