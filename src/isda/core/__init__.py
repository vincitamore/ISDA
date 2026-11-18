"""isda.core: the document model, one parse shared by every measure."""

from .blocks import Block, BlockKind, PROSE_KINDS, Span, parse_blocks
from .document import Document, ProseUnit, scrub_inline
from .features import FEATURES, FeatureContext, UndeclaredFeature, UnknownFeature
from .tokens import (
    WORD, paragraph_units, sections, sentence_units, word_spans, words,
)

__all__ = [
    "Block", "BlockKind", "PROSE_KINDS", "Span", "parse_blocks",
    "Document", "ProseUnit", "scrub_inline",
    "FEATURES", "FeatureContext", "UndeclaredFeature", "UnknownFeature",
    "WORD", "paragraph_units", "sections", "sentence_units", "word_spans", "words",
]
