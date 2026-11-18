#!/usr/bin/env python3
"""
ISDA preprocessor. Measurement, not judgment.

A single file with no dependencies outside the standard library. It gives a
semantic analysis hard numbers to anchor on. It does not classify content into
strata; that takes understanding.

What it does:
  - Measures bytes, words, sentences, paragraphs.
  - Maps structure: sections are exact markdown headings.
  - Computes lexical statistics: type-token ratio, hapax ratio, word lengths.
  - Reports the content-word ratio, sentence-length statistics and a syllable
    estimate.
  - Extracts candidates for review: quotes, repeated phrases, citation patterns.
  - Scores a completed stratum ledger into SCR / ND / RI (--ledger).
  - Excludes markup (frontmatter, code, tables, link targets) from prose statistics.
  - Rolls statistics up per segment so local density is visible.
  - Records telos and substrate as metadata for downstream analysis.

What it does not do:
  - Classify content into Grammatica / Dialectica / Rhetorica / Arithmetica /
    Geometria / Musica / Astronomia.
  - Assign Stock / Implied / Selected / Original intensity tags.
  - Decide whether a repetition is redundancy or a rhetorical device.
  - Measure propositional density, which needs a POS tagger (the isda package's
    `arithmetica.propositional-density` measure runs CPIDR), or trajectory,
    which is a property of order that set statistics cannot see.

Usage:
    python isda_preprocess.py <file_path>
    python isda_preprocess.py <file_path> --telos "teach category theory to a beginner"
    python isda_preprocess.py <file_path> --telos "..." --substrate "public web"
    python isda_preprocess.py --text "inline text" --telos "..."
    cat file.txt | python isda_preprocess.py --stdin --telos "..."
    python isda_preprocess.py --ledger ledger.json --pretty

The --telos and --substrate flags are optional and strongly recommended. They
are recorded in the output metadata so downstream analysis carries the
interpretive frame. If omitted, a warning is emitted.

Output: JSON with measurements, raw features, and candidates for human judgment.
"""

import argparse
import json
import re
import sys
import unicodedata
import zlib
from collections import Counter
from dataclasses import dataclass, asdict, field


# ---------- Dataclasses ----------


@dataclass
class Measurements:
    total_bytes: int
    total_chars: int
    total_words: int
    total_sentences: int
    total_paragraphs: int


@dataclass
class Structure:
    detected_sections: list[str]
    section_count: int
    paragraph_lengths: list[int]
    avg_paragraph_words: float | None
    median_paragraph_words: float | None


@dataclass
class SentenceProfile:
    avg_length_words: float | None
    median_length_words: float | None
    min_length: int | None
    max_length: int | None
    distribution: dict[str, int]
    lengths: list[int]


@dataclass
class LexicalProfile:
    unique_words: int
    type_token_ratio: float | None
    hapax_legomena: int
    hapax_ratio: float | None
    avg_word_length: float | None
    word_length_distribution: dict[int, int]


@dataclass
class SegmentStats:
    label: str
    start_offset: int
    end_offset: int
    bytes: int
    words: int
    sentences: int
    unique_words: int
    type_token_ratio: float | None
    hapax_ratio: float | None
    avg_sentence_length: float | None
    sentence_length_variance: float | None
    content_word_ratio: float | None


@dataclass
class ArithmeticaFeature:
    """Content-word ratio: the share of words outside the function-word list."""
    content_words: int | None
    content_word_ratio: float | None
    note: str


@dataclass
class MusicaFeature:
    """Sentence-length and syllable statistics. Descriptive; no null model."""
    sentence_length_mean: float | None
    sentence_length_variance: float | None
    sentence_length_cv: float | None  # coefficient of variation
    avg_syllables_per_word_est: float | None
    rhetorical_figure_candidates: dict
    note: str


@dataclass
class Candidate:
    type: str
    text: str
    position: int
    context: str
    note: str


# ---------- Function-word list for the content-word ratio ----------

# English function words: articles, auxiliaries, pronouns, conjunctions, etc.
# Every other token counts as a content word.
STOPWORDS = {
    # articles
    "a", "an", "the",
    # auxiliaries
    "am", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "shall", "should", "can", "could", "may", "might",
    "must", "ought",
    # pronouns
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "this", "that", "these", "those",
    "who", "whom", "whose", "which", "what",
    # conjunctions
    "and", "or", "but", "nor", "yet", "so", "for",
    "if", "then", "else", "when", "where", "while", "as", "because",
    "though", "although", "since", "unless", "until", "whether",
    # determiners
    "some", "any", "all", "every", "each", "no", "none",
    "many", "much", "more", "most", "few", "several", "such",
    # prepositions (arguably content-bearing in CPIDR but excluded here for simplicity)
    "of", "in", "on", "at", "to", "from", "by", "with", "about",
    "into", "onto", "upon", "over", "under", "through", "between",
    "among", "against", "before", "after", "during", "without", "within",
    # other function words
    "not", "only", "even", "also", "just", "very", "too",
    "there", "here", "now", "then",
}


# Exit codes. 1 is left for "ran clean, found something actionable"; bad input
# is 64, so a caller can tell a finding from a failure.
EXIT_OK = 0
EXIT_USAGE = 64      # malformed input: bad ledger, unreadable or non-UTF-8 file
EXIT_INTERNAL = 70   # a bug in this tool

# Per-type ceiling on flagged candidates. Without it a long, repetitive
# document can produce a report several times its own size.
MAX_CANDIDATES_PER_TYPE = 25


# ---------- Tokenization primitives ----------


def strip_markup(text: str) -> tuple[str, dict]:
    """
    Separate prose from markup before any prose statistic is computed.

    Fenced code, inline code, HTML comments, YAML frontmatter, and table rows
    are not prose. Counting them inflates word totals, depresses type-token
    ratio, and fills the candidate list with syntax fragments such as
    '| |---|---|'.

    Link syntax is unwrapped, not dropped: the visible text of a link is prose,
    its URL and path slug are not.

    Returns the prose text and a record of what was removed, so the report
    shows the exclusion.
    """
    stats = {
        'frontmatter_bytes': 0,
        'code_block_bytes': 0,
        'inline_code_bytes': 0,
        'table_row_bytes': 0,
        'html_comment_bytes': 0,
        'link_target_bytes': 0,
    }

    fm = re.match(r'\A---\r?\n.*?\r?\n---\r?\n', text, re.DOTALL)
    if fm:
        stats['frontmatter_bytes'] = len(fm.group(0).encode('utf-8'))
        text = text[fm.end():]

    def eat(pattern, key, repl='\n', flags=0):
        nonlocal text
        total = 0

        def sub(m):
            nonlocal total
            total += len(m.group(0).encode('utf-8'))
            return repl

        text = re.sub(pattern, sub, text, flags=flags)
        # Accumulate: the two fence styles (``` and ~~~) share the
        # code_block_bytes key.
        stats[key] = stats.get(key, 0) + total

    eat(r'<!--.*?-->', 'html_comment_bytes', flags=re.DOTALL)
    eat(r'^[ \t]*```.*?^[ \t]*```[ \t]*$', 'code_block_bytes',
        flags=re.DOTALL | re.MULTILINE)
    eat(r'^[ \t]*~~~.*?^[ \t]*~~~[ \t]*$', 'code_block_bytes',
        flags=re.DOTALL | re.MULTILINE)
    eat(r'`[^`\n]+`', 'inline_code_bytes', repl=' ')

    # Markdown and wiki links: keep the label, drop the target.
    def unlink(m):
        stats['link_target_bytes'] += len(m.group(0).encode('utf-8')) - len(
            m.group(1).encode('utf-8'))
        return m.group(1)

    text = re.sub(r'\[([^\]\n]+)\]\([^)\n]*\)', unlink, text)
    text = re.sub(r'\[\[([^\]\n|]+)(?:\|([^\]\n]+))?\]\]',
                  lambda m: m.group(2) or m.group(1).split('/')[-1], text)

    kept = []
    for line in text.split('\n'):
        if line.count('|') >= 2 and line.strip().startswith('|'):
            stats['table_row_bytes'] += len(line.encode('utf-8'))
            continue
        kept.append(line)
    text = '\n'.join(kept)

    # Emphasis markers are punctuation, not words, and left in place they read
    # as sentence openings. Keep the emphasized text, drop the marks.
    text = re.sub(r'(\*\*\*|\*\*|\*|___|__|_)(?=\S)(.*?)(?<=\S)\1', r'\2', text, flags=re.DOTALL)

    return text, stats


# Lines that are their own prosodic unit even without terminal punctuation:
# markdown headings, list items, blockquote markers, definition rows.
_BLOCK_LINE = re.compile(r'^[ \t]*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s*)')


def _mark_class() -> str:
    """The Unicode combining marks (Mn/Mc/Me) as a regex character class.

    Derived from the running interpreter's tables (~0.1 s at import, then
    cached in the compiled pattern) rather than hand-listed, so a Python
    upgrade that adds marks is picked up instead of silently missed.
    """
    marks = [cp for cp in range(sys.maxunicode + 1)
             if unicodedata.category(chr(cp)) in ('Mn', 'Mc', 'Me')]
    parts = []
    start = prev = marks[0]
    for cp in marks[1:]:
        if cp == prev + 1:
            prev = cp
            continue
        parts.append(re.escape(chr(start)) if start == prev
                     else '%s-%s' % (re.escape(chr(start)), re.escape(chr(prev))))
        start = prev = cp
    parts.append(re.escape(chr(start)) if start == prev
                 else '%s-%s' % (re.escape(chr(start)), re.escape(chr(prev))))
    return ''.join(parts)


_MARKS = _mark_class()
_WORD = re.compile(
    r'[^\W\d_][%s]*(?:[^\W\d_][%s]*)*' % (_MARKS, _MARKS), re.UNICODE)


def tokenize_words(text: str) -> list[str]:
    """
    Letter runs with their combining marks, Unicode-aware.

    `[^\\W\\d_]` is a Unicode letter: a word character that is not a digit or
    underscore. An ASCII-only class would drop every word containing a
    non-ASCII letter, since no word boundary exists between `f` and `é`.

    A letter run alone treats a combining mark as a word boundary, which no
    orthography does: pointed Hebrew, Arabic with harakat, Devanagari and
    NFD-normalized Latin would all split mid-word, and every fragment would
    count as its own type. UAX #29's word-boundary rule WB4 ignores Extend
    characters, so a mark attaches to its base. A word may not start with a
    mark; a stray mark after punctuation is not a word.

    Lowercasing can itself produce a mark: Turkish `İ` (U+0130) lowercases to
    `i` + COMBINING DOT ABOVE, and `İstanbul` stays one word.
    """
    return _WORD.findall(text.lower())


def tokenize_sentences(text: str) -> list[str]:
    """
    Split into sentences, treating markdown block starts as boundaries.

    A bulleted or headed line is a complete utterance whether or not it ends
    in a period. Splitting on terminal punctuation alone would merge a whole
    list into one pseudo-sentence and wreck every sentence-length statistic.
    """
    protected = text
    abbrevs = ['Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Inc', 'Ltd', 'Jr', 'Sr',
               'vs', 'etc', 'i.e', 'e.g']
    for abbr in abbrevs:
        protected = re.sub(rf'\b{abbr}\.\s', f'{abbr}<DOT> ', protected)

    units = []
    current: list[str] = []
    for line in protected.split('\n'):
        if _BLOCK_LINE.match(line) or not line.strip():
            if current:
                units.append(' '.join(current))
                current = []
            if line.strip():
                units.append(re.sub(r'^[ \t]*(?:#{1,6}|[-*+]|\d+[.)]|>)\s*', '', line))
        else:
            current.append(line.strip())
    if current:
        units.append(' '.join(current))

    sentences = []
    for unit in units:
        for s in re.split(r'[.!?]+\s+', unit):
            s = s.replace('<DOT>', '.').strip()
            if s:
                sentences.append(s)
    return sentences


def extract_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', text)
    return [p.strip() for p in paragraphs if p.strip()]


# One heading definition, shared by section detection and segmentation, so the
# two can never disagree about what a section is.
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$')


def extract_headings(text: str) -> list[str]:
    """
    Markdown headings, exactly. A heading is declared by syntax, so nothing
    here guesses from capitalization or line length.
    """
    return [
        m.group(2).strip()
        for line in text.split('\n')
        if (m := HEADING_RE.match(line.strip()))
    ]


# ---------- Content-word heuristic ----------


def count_content_words(words: list[str]) -> int:
    """Count the words outside the function-word list."""
    return sum(1 for w in words if w not in STOPWORDS)


def estimate_syllables(word: str) -> int:
    """
    Vowel-group heuristic for syllable estimation.
    Not linguistically precise; close enough for relative variance.
    """
    word = word.lower().strip()
    if not word:
        return 0
    count = 0
    prev_was_vowel = False
    vowels = "aeiouy"
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def detect_rhetorical_figure_candidates(sentences: list[str]) -> dict:
    """
    Count adjacent sentence pairs that open with the same two words.

    Anaphora is rare enough that a non-zero count is worth a human look. The
    count has no null model and no discrimination test, so it is reported as
    a candidate count, not as a measurement of rhetorical density. Reliable
    detection of rhetorical figures is an open research problem: the best
    supervised chiasmus classifiers reach F1 around 0.78 with training data.
    """
    anaphora = 0
    for i in range(len(sentences) - 1):
        s1 = sentences[i].lower().split()[:2]
        s2 = sentences[i + 1].lower().split()[:2]
        if s1 and s2 and s1 == s2:
            anaphora += 1

    return {
        'anaphora_candidates': anaphora,
        'adjacent_pairs': max(0, len(sentences) - 1),
        'status': 'unvalidated',
        'note': (
            'Anaphora is a candidate count for a human to inspect, not a measurement. '
            'It has no null model and no discrimination test. Do not read it as evidence '
            'of rhetorical density.'
        ),
    }


# ---------- Core measurement ----------


def measure(text: str) -> Measurements:
    paragraphs = extract_paragraphs(text)
    sentences = tokenize_sentences(text)
    words = tokenize_words(text)

    return Measurements(
        total_bytes=len(text.encode('utf-8')),
        total_chars=len(text),
        total_words=len(words),
        total_sentences=len(sentences),
        total_paragraphs=len(paragraphs)
    )


def analyze_structure(text: str) -> Structure:
    paragraphs = extract_paragraphs(text)
    sections = extract_headings(text)

    para_lengths = [len(tokenize_words(p)) for p in paragraphs]
    sorted_lengths = sorted(para_lengths)
    median_idx = len(sorted_lengths) // 2

    # A document with no paragraphs has no average, and None says so; a zero
    # would read as a measured emptiness.
    return Structure(
        detected_sections=sections,
        section_count=len(sections),
        paragraph_lengths=para_lengths,
        avg_paragraph_words=round(sum(para_lengths) / len(para_lengths), 2) if para_lengths else None,
        median_paragraph_words=sorted_lengths[median_idx] if sorted_lengths else None
    )


def analyze_sentences(text: str) -> SentenceProfile:
    sentences = tokenize_sentences(text)
    lengths = [len(tokenize_words(s)) for s in sentences]

    if not lengths:
        return SentenceProfile(None, None, None, None, {}, [])

    sorted_lengths = sorted(lengths)
    median_idx = len(sorted_lengths) // 2

    dist = {'short_1_10': 0, 'medium_11_20': 0, 'long_21_35': 0, 'very_long_36_plus': 0}
    for length in lengths:
        if length <= 10:
            dist['short_1_10'] += 1
        elif length <= 20:
            dist['medium_11_20'] += 1
        elif length <= 35:
            dist['long_21_35'] += 1
        else:
            dist['very_long_36_plus'] += 1

    return SentenceProfile(
        avg_length_words=round(sum(lengths) / len(lengths), 2),
        median_length_words=sorted_lengths[median_idx],
        min_length=min(lengths),
        max_length=max(lengths),
        distribution=dist,
        lengths=lengths
    )


def analyze_lexical(text: str) -> LexicalProfile:
    words = tokenize_words(text)
    if not words:
        return LexicalProfile(0, None, 0, None, None, {})

    word_counts = Counter(words)
    unique = len(word_counts)
    hapax = sum(1 for w, c in word_counts.items() if c == 1)

    length_dist = Counter(len(w) for w in words)

    return LexicalProfile(
        unique_words=unique,
        type_token_ratio=round(unique / len(words), 4),
        hapax_legomena=hapax,
        hapax_ratio=round(hapax / unique, 4),
        avg_word_length=round(sum(len(w) for w in words) / len(words), 2),
        word_length_distribution=dict(sorted(length_dist.items()))
    )


def analyze_arithmetica(text: str) -> ArithmeticaFeature:
    """
    The content-word ratio: words outside the function-word list, over all words.

    This is not propositional density. The ratio reads the word multiset only,
    so it is unchanged when word order is scrambled and every proposition in
    the text is destroyed. Propositional density needs a POS tagger: CPIDR
    (Brown et al. 2008), which the isda package runs as
    `arithmetica.propositional-density`.
    """
    words = tokenize_words(text)

    if not words:
        # None, not 0.0: a zero would read as a measured value.
        return ArithmeticaFeature(
            content_words=None,
            content_word_ratio=None,
            note="No words to analyze; no value emitted."
        )

    content_count = count_content_words(words)
    return ArithmeticaFeature(
        content_words=content_count,
        content_word_ratio=round(content_count / len(words), 4),
        note=(
            "A lexical ratio, not propositional density: it does not change when "
            "word order is scrambled. For propositional density use CPIDR "
            "(Brown et al. 2008)."
        ),
    )


def analyze_musica(text: str) -> MusicaFeature:
    """
    Sentence-length variance, average syllables per word, and the anaphora
    candidate count.

    These describe local rhythm; they do not estimate K(prosody | Pi_local),
    which would need a model of the genre's expected prosody.
    """
    sentences = tokenize_sentences(text)
    words = tokenize_words(text)

    if not sentences or not words:
        return MusicaFeature(
            sentence_length_mean=None,
            sentence_length_variance=None,
            sentence_length_cv=None,
            avg_syllables_per_word_est=None,
            rhetorical_figure_candidates={},
            note="Insufficient text for Musica feature extraction.",
        )

    sentence_lengths = [len(tokenize_words(s)) for s in sentences]
    mean_length = sum(sentence_lengths) / len(sentence_lengths)

    variance = sum((l - mean_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)
    cv = (variance ** 0.5 / mean_length) if mean_length > 0 else 0

    syllable_counts = [estimate_syllables(w) for w in words]
    avg_syllables = sum(syllable_counts) / len(syllable_counts) if syllable_counts else 0

    figure_count = detect_rhetorical_figure_candidates(sentences)

    return MusicaFeature(
        sentence_length_mean=round(mean_length, 2),
        sentence_length_variance=round(variance, 2),
        sentence_length_cv=round(cv, 4),
        avg_syllables_per_word_est=round(avg_syllables, 2),
        rhetorical_figure_candidates=figure_count,
        note=(
            "Descriptive statistics of sentence length and syllable count. They "
            "anchor a reading of local rhythm and do not classify it; reading "
            "them against the genre's expected rhythm requires judgment."
        ),
    )


# ---------- Segmentation and per-segment rollup ----------


def segment_by_markdown_headers(text: str) -> list[tuple[str, int, int]]:
    segments = []
    lines = text.split('\n')
    current_label = 'preamble'
    current_start = 0
    pos = 0

    for line in lines:
        line_with_nl = line + '\n'
        header_match = HEADING_RE.match(line)
        if header_match:
            if pos > current_start:
                segments.append((current_label, current_start, pos))
            current_label = header_match.group(2).strip()
            current_start = pos
        pos += len(line_with_nl)

    if pos > current_start:
        segments.append((current_label, current_start, min(pos, len(text))))

    if len(segments) == 1 and segments[0][0] == 'preamble':
        return [('(whole document)', 0, len(text))]

    return segments


def segment_equal_chunks(text: str, target_chunks: int = 5) -> list[tuple[str, int, int]]:
    total_len = len(text)
    if total_len == 0:
        return []

    chunk_size = max(1, total_len // target_chunks)
    segments = []
    pos = 0
    chunk_num = 1

    while pos < total_len and chunk_num <= target_chunks:
        end_target = min(pos + chunk_size, total_len)

        if chunk_num < target_chunks:
            next_break = text.find('\n\n', end_target)
            if next_break != -1 and next_break - end_target < chunk_size // 2:
                end_target = next_break + 2
        else:
            end_target = total_len

        segments.append((f'chunk {chunk_num}', pos, end_target))
        pos = end_target
        chunk_num += 1

    return segments


def analyze_segment(label: str, start: int, end: int, segment_text: str) -> SegmentStats:
    words = tokenize_words(segment_text)
    sentences = tokenize_sentences(segment_text)
    word_counts = Counter(words)
    unique = len(word_counts)
    hapax = sum(1 for _, c in word_counts.items() if c == 1)
    sentence_lengths = [len(tokenize_words(s)) for s in sentences]

    content_count = count_content_words(words)

    mean_sentence_length = (
        sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else None
    )
    variance = (
        sum((l - mean_sentence_length) ** 2 for l in sentence_lengths)
        / len(sentence_lengths)
        if mean_sentence_length is not None
        else None
    )

    return SegmentStats(
        label=label,
        start_offset=start,
        end_offset=end,
        bytes=len(segment_text.encode('utf-8')),
        words=len(words),
        sentences=len(sentences),
        unique_words=unique,
        type_token_ratio=round(unique / len(words), 4) if words else None,
        hapax_ratio=round(hapax / unique, 4) if unique else None,
        avg_sentence_length=(round(mean_sentence_length, 2)
                             if mean_sentence_length is not None else None),
        sentence_length_variance=round(variance, 2) if variance is not None else None,
        content_word_ratio=round(content_count / len(words), 4) if words else None,
    )


def compute_local_rollup(segments: list[SegmentStats]) -> dict:
    if not segments:
        return {}

    # A segment with no words has no ratio (None); it is left out of the
    # rollup, not counted as a zero.
    hapax_ratios = [s.hapax_ratio for s in segments if s.hapax_ratio is not None]
    ttrs = [s.type_token_ratio for s in segments if s.type_token_ratio is not None]
    content_ratios = [s.content_word_ratio for s in segments
                      if s.content_word_ratio is not None]

    def stats(values: list[float]) -> dict:
        if not values:
            return {'median': None, 'min': None, 'max': None, 'range': None}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        median = (
            sorted_vals[n // 2]
            if n % 2 == 1
            else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        )
        return {
            'median': round(median, 4),
            'min': round(min(values), 4),
            'max': round(max(values), 4),
            'range': round(max(values) - min(values), 4),
        }

    return {
        'segment_count': len(segments),
        'hapax_ratio': stats(hapax_ratios),
        'type_token_ratio': stats(ttrs),
        'content_word_ratio': stats(content_ratios),
        'note': (
            'hapax_ratio is a lexical novelty proxy, not semantic novelty density. '
            'content_word_ratio is a lexical ratio, not propositional density. '
            'A wide range across segments flags an uneven text that needs local analysis. '
            'Stratum intensity tagging (Stock/Implied/Selected/Original) requires semantic judgment.'
        ),
    }


# ---------- Candidate extraction ----------


def extract_candidates(text: str) -> list[Candidate]:
    candidates = []

    for match in re.finditer(r'["\u201C\u201D]([^"\u201C\u201D]{5,200})["\u201C\u201D]', text):
        start = max(0, match.start() - 30)
        end = min(len(text), match.end() + 30)
        candidates.append(Candidate(
            type='quoted_string',
            text=match.group(0),
            position=match.start(),
            context=text[start:end],
            note='May be citation, technical term, ironic usage, or emphasis; requires judgment'
        ))

    for match in re.finditer(r'https?://[^\s<>"{}|\\^`\[\]]+', text):
        candidates.append(Candidate(
            type='url',
            text=match.group(0),
            position=match.start(),
            context='',
            note='External reference, clearly retrievable (Memoria-substrate)'
        ))

    for match in re.finditer(r'\([A-Z][a-z]+(?:\s+(?:et al\.?|&|and)\s+[A-Z][a-z]+)?,?\s*\d{4}[a-z]?\)', text):
        candidates.append(Candidate(
            type='citation_pattern',
            text=match.group(0),
            position=match.start(),
            context='',
            note='Academic citation, likely Memoria-substrate pointer'
        ))

    for match in re.finditer(r'\[\d+\]', text):
        candidates.append(Candidate(
            type='citation_pattern',
            text=match.group(0),
            position=match.start(),
            context='',
            note='Numeric citation marker, likely Memoria-substrate pointer'
        ))

    words_lower = text.lower().split()
    seen_phrases = set()

    for n in range(3, 7):
        if n > len(words_lower):
            continue
        ngrams = [' '.join(words_lower[i:i + n]) for i in range(len(words_lower) - n + 1)]
        counts = Counter(ngrams)

        for phrase, count in counts.items():
            if count >= 2 and phrase not in seen_phrases:
                is_subset = any(phrase in p and phrase != p for p in seen_phrases)
                if not is_subset:
                    seen_phrases.add(phrase)
                    pos = text.lower().find(phrase)
                    candidates.append(Candidate(
                        type='repeated_phrase',
                        text=phrase,
                        position=pos,
                        context=f'Appears {count} times',
                        note=(
                            'May be redundancy OR intentional rhetorical device; requires judgment. '
                            'Repeated openings suggest anaphora (Musica); repeated structure '
                            'suggests isocolon (Musica); repeated content suggests Rhetorica emphasis '
                            'or redundancy.'
                        ),
                    ))

    return sorted(candidates, key=lambda x: x.position)


# ---------- Report assembly ----------


def generate_report(text: str, telos: str | None, substrate: str | None,
                    keep_markup: bool = False) -> dict:
    raw_text = text
    if keep_markup:
        prose, strip_stats = text, {}
    else:
        prose, strip_stats = strip_markup(text)

    # Document-level size, paragraph statistics and headings are reported over
    # the source; every other statistic is computed over prose only.
    measurements = measure(raw_text)
    measurements.total_words = len(tokenize_words(prose))
    measurements.total_sentences = len(tokenize_sentences(prose))

    structure = analyze_structure(raw_text)
    sentences = analyze_sentences(prose)
    lexical = analyze_lexical(prose)
    candidates = extract_candidates(prose)

    arithmetica = analyze_arithmetica(prose)
    musica = analyze_musica(prose)

    # Segment over prose, not source: headings inside fenced code blocks would
    # otherwise open segments of their own, and every segment's statistics would
    # be computed over markup.
    seg_ranges = segment_by_markdown_headers(prose)
    if len(seg_ranges) < 2:
        seg_ranges = segment_equal_chunks(prose, target_chunks=5)

    segments = [
        analyze_segment(label, start, end, prose[start:end])
        for label, start, end in seg_ranges
    ]
    rollup = compute_local_rollup(segments)

    candidates_by_type: dict[str, list] = {}
    candidate_totals: dict[str, int] = {}
    for c in candidates:
        candidate_totals[c.type] = candidate_totals.get(c.type, 0) + 1
        bucket = candidates_by_type.setdefault(c.type, [])
        if len(bucket) < MAX_CANDIDATES_PER_TYPE:
            bucket.append(asdict(c))
    candidates_truncated = {
        t: n for t, n in candidate_totals.items() if n > MAX_CANDIDATES_PER_TYPE
    }

    warnings = []
    if not telos:
        warnings.append(
            'No --telos provided. ISDA results without a stated telos compress '
            'toward an undefined target and are not interpretable. State the task '
            'this text is trying to achieve.'
        )
    if not substrate:
        warnings.append(
            'No --substrate provided. Arithmetica-density can be computed without a '
            'substrate, but Dialectica, Memoria-retrievability, and the intensity tags '
            '(Stock/Implied/Selected/Original) are meaningless without a named retrieval '
            'substrate (public / corpus / context). State which.'
        )

    return {
        '_meta': {
            'tool': 'ISDA Preprocessor',
            'framework': 'ISDA seven-stratum Nicomachan-Boethian',
            'philosophy': 'Measurement, not judgment. All intensity tags require human/LLM analysis.',
            'warning': (
                'Do not treat raw feature values as stratum classifications. '
                'Stock/Implied/Selected/Original tagging requires semantic judgment.'
            ),
            'telos': telos,
            'substrate': substrate,
            'warnings': warnings,
        },
        'measurements': asdict(measurements),
        'structure': {
            **asdict(structure),
            'paragraph_lengths': (
                structure.paragraph_lengths[:20]
                if len(structure.paragraph_lengths) > 20
                else structure.paragraph_lengths
            ),
            '_truncated': len(structure.paragraph_lengths) > 20,
        },
        'sentences': {
            **asdict(sentences),
            'lengths': sentences.lengths[:50] if len(sentences.lengths) > 50 else sentences.lengths,
            '_truncated': len(sentences.lengths) > 50,
        },
        'lexical': asdict(lexical),
        'stratum_raw_features': {
            'arithmetica': asdict(arithmetica),
            'musica': asdict(musica),
            'note': (
                'Raw features, not stratum readings. Dialectica, Rhetorica and '
                'Astronomia have no mechanical feature in this tool; the analyst '
                'reads them. Intensity tagging (Stock/Implied/Selected/Original) is '
                'semantic and not provided.'
            ),
        },
        'local_density': {
            'segments': [asdict(s) for s in segments],
            'rollup': rollup,
        },
        'candidates_for_review': {
            'total_flagged': len(candidates),
            'by_type': candidate_totals,
            'shown_per_type_cap': MAX_CANDIDATES_PER_TYPE,
            'truncated_types': candidates_truncated,
            'items': candidates_by_type,
        },
        'preprocessing': {
            'markup_excluded': not keep_markup,
            'excluded_bytes': strip_stats,
            'prose_bytes': len(prose.encode('utf-8')),
            'note': (
                'Word, sentence, lexical, Arithmetica, Musica and candidate figures are '
                'computed over prose with markup removed; total_bytes, paragraph '
                'statistics and section detection (exact markdown headings) read the '
                'source. Pass --keep-markup to measure the source verbatim instead.'
            ),
        },
    }


STRATA = [
    'grammatica', 'dialectica', 'rhetorica',
    'arithmetica', 'geometria', 'musica', 'astronomia',
]

ND_WEIGHT = {'Stock': 0.0, 'Implied': 0.1, 'Selected': 0.3, 'Original': 1.0}
RI_WEIGHT = {'Stock': 1.0, 'Implied': 0.7, 'Selected': 0.0, 'Original': 0.0}


ZDICT_CAP = 32768  # zlib compressobj zdict hard limit


def _as_utf8_bytes(value, field_name: str) -> bytes:
    """Accept str or bytes for the optional ledger document/substrate fields."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode('utf-8')
    raise TypeError(f'{field_name} must be str or bytes')


def compress_upper_bound(data: bytes, substrate: bytes | None = None) -> tuple[int, str]:
    """
    A lossless upper bound on K(d | substrate), via zlib level 9.

    K is uncomputable, so no estimate of it can be validated. A real compressor
    still bounds it from above: whatever zlib achieves, the true minimum is no
    larger. That one-sided fact is the mechanical anchor for a ledger.

    Container overhead is not subtracted. The bound is an achievable encoding
    length; stripping the header would report a number no encoder can hit.

    Returns (length, mode) where mode is 'primed' or 'unconditioned'.
    """
    if substrate:
        # Raw deflate (wbits=-15), not the zlib wrapper. The wrapper adds 10
        # bytes: a 2-byte header, a 4-byte DICTID and a 4-byte Adler-32 trailer,
        # and DICTID only re-identifies a dictionary the caller already supplies.
        # Raw deflate plus the declared substrate reconstructs the document
        # exactly, so its length is a decodable encoding and a valid upper bound.
        co = zlib.compressobj(9, zlib.DEFLATED, -15, 8,
                              zlib.Z_DEFAULT_STRATEGY, substrate[:ZDICT_CAP])
        return len(co.compress(data) + co.flush()), 'primed'
    return len(zlib.compress(data, 9)), 'unconditioned'


def score_ledger(ledger: dict) -> dict:
    """
    Compute SCR / ND / RI from a completed stratum ledger.

    Arithmetic only, no judgment: the analyst supplies the compressed sizes and
    intensity tags, and this computes the three metrics as SKILL.md Step 5
    defines them and shows the per-stratum contributions.

    ND and RI are byte-weighted sums over compressed sizes, not unweighted
    per-stratum averages, which is why they are computed and not estimated.

    Expected shape:
        {"raw_bytes": 14304,
         "strata": {"grammatica": {"compressed": 85, "intensity": "Selected"}, ...}}
    """
    errors = []

    raw_field = ledger.get('raw_bytes')
    raw = 0.0
    if isinstance(raw_field, (int, float)) and not isinstance(raw_field, bool) and raw_field > 0:
        raw = float(raw_field)
    else:
        errors.append('raw_bytes must be a positive number')

    strata = ledger.get('strata')
    if not isinstance(strata, dict):
        errors.append('strata must be an object keyed by the seven stratum names')
        strata = {}

    missing = [s for s in STRATA if s not in strata]
    if missing:
        errors.append(f'missing strata: {", ".join(missing)}')
    unknown = [s for s in strata if s not in STRATA]
    if unknown:
        errors.append(f'unknown strata: {", ".join(unknown)}')

    rows = {}
    for name in STRATA:
        row = strata.get(name)
        if not isinstance(row, dict):
            continue
        size = row.get('compressed')
        tag = row.get('intensity')
        if not isinstance(size, (int, float)) or size < 0:
            errors.append(f'{name}: compressed must be a non-negative number')
            continue
        if tag not in ND_WEIGHT:
            errors.append(
                f'{name}: intensity must be one of Stock, Implied, Selected, Original '
                f'(got {tag!r})'
            )
            continue
        rows[name] = (float(size), tag)

    if errors:
        return {'ok': False, 'errors': errors}

    total = sum(size for size, _ in rows.values())

    # A compressed core larger than the document it compresses is incoherent.
    # This is the weak form of the compression floor: K_tau <= |d|.
    if total > raw:
        return {'ok': False, 'errors': [
            f'total compressed ({total:g} B) exceeds raw_bytes ({raw:g} B). '
            'The telos-preserving core cannot be larger than the text; check the '
            'ledger rows or the measured raw length.'
        ]}
    if total <= 0:
        return {'ok': False, 'errors': ['total compressed size is zero']}

    # The compression floor: the sum of compressed sizes must not exceed C(d | D).
    # A violation is a provable estimation error: the analyst has claimed a
    # telos-preserving core larger than a known lossless encoding of the whole
    # document. The check binds on dense short text and is near-vacuous on
    # sparse prose, where the compressed length sits far above any plausible core.
    floor_info = {'checked': False,
                  'reason': 'no document supplied, so the floor was not checked'}
    doc_field = ledger.get('document')
    if doc_field is not None:
        try:
            doc_bytes = _as_utf8_bytes(doc_field, 'document')
        except TypeError as exc:
            return {'ok': False, 'errors': [str(exc)]}
        if len(doc_bytes) != int(raw):
            return {'ok': False, 'errors': [
                f'document is {len(doc_bytes)} bytes but raw_bytes is {raw:g}; '
                'the SCR numerator and the compression floor must describe the '
                'same object.'
            ]}
        sub_bytes = None
        sub_field = ledger.get('substrate_text')
        if sub_field is not None:
            try:
                sub_bytes = _as_utf8_bytes(sub_field, 'substrate_text')
            except TypeError as exc:
                return {'ok': False, 'errors': [str(exc)]}
        c_bound, mode = compress_upper_bound(doc_bytes, sub_bytes)
        if total > c_bound:
            return {'ok': False, 'errors': [
                f'total compressed ({total:g} B) exceeds the zlib {mode} upper bound '
                f'C(d|D)={c_bound} B. The telos-preserving core cannot exceed a lossless '
                f'compression of the document, so at least one ledger row is overstated. '
                f'(One-sided: this catches cores claimed too large and cannot detect '
                f'cores claimed too small.)'
            ]}
        floor_info = {
            'checked': True,
            'mode': mode,
            'C': c_bound,
            'margin_bytes': round(c_bound - total, 2),
            'SCR_lower_bound': round(raw / c_bound, 4),
            'note': ('Passing is necessary but not sufficient: it does not validate '
                     'any estimate, and only means no row is provably impossible.'),
        }

    contributions = {}
    nd_num = 0.0
    ri_num = 0.0
    for name, (size, tag) in rows.items():
        nd_c = size * ND_WEIGHT[tag]
        ri_c = size * RI_WEIGHT[tag]
        nd_num += nd_c
        ri_num += ri_c
        contributions[name] = {
            'compressed': size,
            'intensity': tag,
            'share_of_core': round(size / total, 4),
            'nd_contribution': round(nd_c, 3),
            'ri_contribution': round(ri_c, 3),
        }

    dominant = max(rows, key=lambda n: rows[n][0])

    return {
        'ok': True,
        'raw_bytes': raw_field,
        'total_compressed': round(total, 2),
        'metrics': {
            'SCR': round(raw / total, 2),
            'ND': round(nd_num / total, 3),
            'RI': round(ri_num / total, 3),
        },
        'arithmetic': {
            'SCR': f'{raw} / {round(total, 2)}',
            'ND': f'{round(nd_num, 2)} / {round(total, 2)}',
            'RI': f'{round(ri_num, 2)} / {round(total, 2)}',
        },
        'per_stratum': contributions,
        'dominant_stratum': dominant,
        'dominant_share_of_core': round(rows[dominant][0] / total, 4),
        'compression_floor': floor_info,
        'notes': [
            'ND and RI are byte-weighted over compressed sizes, not over raw bytes '
            'and not averaged per stratum.',
            'RI answers "how much of the irreducible core is a substrate pointer", '
            'not "how much of this text could be looked up". An all-Stock ledger '
            'scores exactly 1.0.',
            f'{dominant} carries {round(rows[dominant][0] / total * 100)}% of the core, '
            'so it dominates ND by construction; read the stratum profile alongside '
            'the number.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description='ISDA preprocessor. Measurement, not judgment.',
        epilog=(
            'Outputs raw data for semantic analysis. Does not classify strata. '
            '--telos and --substrate are recorded as metadata and emit warnings if missing. '
            '--ledger scores a completed ledger (SCR/ND/RI) and is pure arithmetic.'
        )
    )
    parser.add_argument('file', nargs='?', help='Path to text file')
    parser.add_argument('--text', '-t', help='Inline text to analyze')
    parser.add_argument('--stdin', '-s', action='store_true', help='Read from stdin')
    parser.add_argument('--pretty', '-p', action='store_true', help='Pretty-print JSON')
    parser.add_argument(
        '--telos',
        help='The task/purpose the text is trying to achieve. '
             'Recorded in output metadata. Strongly recommended.'
    )
    parser.add_argument(
        '--substrate',
        help='The retrieval substrate against which Arithmetica/Dialectica are evaluated '
             '(public / corpus / context + name). Strongly recommended.'
    )
    parser.add_argument(
        '--keep-markup', action='store_true',
        help='Measure the source verbatim instead of stripping markup first. '
             'Default is to exclude frontmatter, fenced and inline code, HTML '
             'comments, table rows, and link targets from every prose statistic, '
             'because counting them inflates word totals and floods the candidate '
             'list with syntax fragments.'
    )
    parser.add_argument(
        '--ledger',
        help='Score a completed stratum ledger instead of measuring text. Takes a JSON '
             'file (or - for stdin) of {"raw_bytes": N, "strata": {"grammatica": '
             '{"compressed": N, "intensity": "Stock|Implied|Selected|Original"}, ...}} '
             'and computes SCR/ND/RI with the arithmetic shown. Use this rather than '
             'estimating the metrics: ND and RI are byte-weighted sums.'
    )

    parser.add_argument(
        '--ledger-document',
        help='Path to the source document, enabling the compression-floor check when '
             'scoring a ledger. Without it the floor is skipped and says so in the output.'
    )
    parser.add_argument(
        '--ledger-substrate',
        help='Path to substrate text used as a zlib dictionary (capped at 32 KiB) for a '
             'tighter, substrate-primed bound. Without it the floor uses unconditioned C(d).'
    )

    try:
        args = parser.parse_args()
    except SystemExit as exc:
        # argparse exits 2 on a bad flag; this tool's usage exit is 64.
        sys.exit(EXIT_OK if exc.code in (0, None) else EXIT_USAGE)

    if args.ledger:
        if args.ledger == '-':
            ledger_raw = sys.stdin.read()
        else:
            try:
                with open(args.ledger, 'r', encoding='utf-8') as f:
                    ledger_raw = f.read()
            except (OSError, UnicodeDecodeError) as exc:
                print(json.dumps({'ok': False, 'errors': [f'--ledger: {exc}']}))
                sys.exit(EXIT_USAGE)
        try:
            ledger = json.loads(ledger_raw)
        except json.JSONDecodeError as exc:
            print(json.dumps({'ok': False, 'errors': [f'invalid JSON: {exc}']}))
            sys.exit(EXIT_USAGE)
        for flag, key in (('ledger_document', 'document'),
                          ('ledger_substrate', 'substrate_text')):
            path = getattr(args, flag)
            if not path:
                continue
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    ledger[key] = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                print(json.dumps({'ok': False,
                                  'errors': [f'--{flag.replace("_", "-")}: {exc}']}))
                sys.exit(EXIT_USAGE)
        result = score_ledger(ledger)
        print(json.dumps(result, indent=2) if args.pretty else json.dumps(result))
        # A malformed ledger is a usage error, not a finding: exit 64, and
        # leave 1 for "ran clean, found something actionable".
        sys.exit(EXIT_OK if result.get('ok') else EXIT_USAGE)

    if args.text:
        text = args.text
    elif args.stdin:
        text = sys.stdin.read()
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError as exc:
            # Input that is not valid UTF-8 gets a JSON error and exit 64, so
            # the tool emits a parseable report on every path.
            print(json.dumps({
                'ok': False,
                'errors': [
                    f'{args.file} is not valid UTF-8: {exc}. '
                    'Re-encode the file, or pipe it through a decoder and use --stdin.'
                ],
            }))
            sys.exit(EXIT_USAGE)
        except OSError as exc:
            print(json.dumps({'ok': False, 'errors': [f'cannot read {args.file}: {exc}']}))
            sys.exit(EXIT_USAGE)
    else:
        parser.print_help()
        sys.exit(EXIT_USAGE)

    report = generate_report(text, args.telos, args.substrate, keep_markup=args.keep_markup)

    if args.pretty:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps(report))


if __name__ == '__main__':
    main()
