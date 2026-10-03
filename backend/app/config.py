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
    # Examples to be confirmed by the project owner before first scientific ingestion:
    # "nasa.gov", "noaa.gov", "nature.com", "sciencedirect.com",
    # "*.edu", "ncbi.nlm.nih.gov",
]

# Minimum confidence required before a Relationship may be labeled POSSIBLE_CONNECTION
# in an answer (still always shown with the explicit disclaimer regardless of score).
MIN_CONNECTION_CONFIDENCE = 0.0
