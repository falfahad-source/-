export type Trust = "QURANIC_TEXT" | "TAFSIR_VERIFIED" | "SCIENTIFIC_FACT" | "POSSIBLE_CONNECTION" | "UNVERIFIED_CLAIM";

export type Era = { year: number | null; century: number | null; century_label: string; era: string };

export type Tafsir = Era & {
  scholar: string | null; category: string; text: string; source: string; page: string | null; trust_category: Trust;
};

export type Word = {
  number: number; text: string; root: string | null; lemma: string | null; pos: string | null;
  description: string | null; translation_en: string | null;
};
export type Meaning = { word: string; meaning: string; book: string; author: string | null };
export type Irab = Era & { book: string; author: string | null; text: string; is_excerpt: boolean | null; page: string | null };

export type Connection = {
  label: string; phrase: string; phrase_label: string; concept: string; concept_name_ar: string;
  concept_name_en: string | null; explanation: string; review_status: string; source: string; trust_category: Trust;
};
export type Phrase = { key: string; label: string; words: [number, number]; text: string; meanings: Meaning[]; connections: Connection[] };
export type Claim = {
  claim: string; trust_category: Trust; source: string; url: string | null; quote: string | null;
  domain: string | null; verified_at: string | null; provenance_note: string | null;
};
export type Science = { concept: string; name_ar: string; name_en: string | null; claims: Claim[] };
export type Topic = {
  id: number; name: string; parent: string | null; related_total: number;
  related: { surah_number: number; ayah_number: number; surah_name: string }[]; source: string;
};
export type GraphNode = {
  id: string; type: "verse" | "phrase" | "concept" | "topic"; label: string; label_en?: string | null;
  trust_category: Trust; related_total?: number; has_claims?: boolean;
};
export type Graph = { nodes: GraphNode[]; edges: { from: string; to: string; type: string }[] };
export type Hadith = {
  label: string; search_query: string; text: string; narrator: string | null; muhaddith: string | null;
  book: string | null; reference: string | null; grade: string | null; source: string;
};

export type Answer = {
  quranic_text: string; surah_number: number; ayah_number: number; surah_name: string;
  page_number: number | null; juz_number: number | null;
  verified_tafsir: Tafsir[];
  linguistic: { words: Word[]; meanings: Meaning[]; e3rab: Irab[]; attribution: string | null };
  concepts: Phrase[]; scientific_knowledge: Science[]; topics: Topic[]; graph: Graph;
  possible_connections: Connection[]; hadith_matches: Hadith[]; not_established: string[];
  sources: { title: string; publisher: string; url: string; trust_category: Trust }[];
  trust_legend: { category: Trust; label: string; description: string }[];
};

export type SearchResult = {
  query: string; total: number; offset: number;
  results: { surah_number: number; surah_name: string; ayah_number: number; text: string; page_number: number | null }[];
};

export type OpenVerse = (surah: number, ayah: number) => void;
