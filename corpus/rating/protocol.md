# Rater protocol

The instructions every model rater receives, verbatim from "The task" onward. A human rater answers the same questions through `python scripts/rate.py`.

## The task

You are rating ONE document. You are told its **telos** (what the text is trying to achieve) and its **substrate** (the knowledge base against which "retrievable" is defined). Judge independently: do not consult other raters, earlier analyses of this document, or any published example analyses.

Decompose the document's work into seven strata and, for each stratum, produce three things:

1. **compressed**: your estimate, in BYTES, of the smallest specification of that stratum's content that would suffice to regenerate its contribution toward the stated telos, GIVEN the substrate. Content the substrate already carries compresses to a short pointer; content the substrate cannot supply must be spelled out. This is an estimate of an uncomputable quantity: give a single point estimate, not a range.
2. **intensity**: exactly one of `Stock`, `Implied`, `Selected`, `Original` (definitions below).
3. **evidence**: the specific passages, features, or (for corpus-tier substrates) substrate locations your judgment relied on. Quote or name them concretely, in at most about 300 characters.

## The seven strata

- **Grammatica**: sentence-level form. Syntactic templates, sentence length and clause structure, coinages, register.
- **Dialectica**: inference. The claims the text derives or argues, and how far they follow from the substrate versus being new inferential moves.
- **Rhetorica**: curatorial decisions. What was selected, how it was ordered and framed, out of what visible option space.
- **Arithmetica**: propositional content. The atomic assertions the text carries, as a body of countable claims.
- **Geometria**: document architecture. Sectioning, hierarchy, layout, the shape of the page.
- **Musica**: rhythm and prosody at local scale. How information is paced within sentences and lines; stress, figures, cadence.
- **Astronomia**: trajectory at global scale. How the text's intensity and argument unfold from beginning to end; the arc.

One sentence can feed several strata at once. Do not partition the document's bytes across strata: each stratum's `compressed` is estimated independently.

## The intensity ladder

Apply conservatively, in this order:

- **Stock**: the stratum's content is retrievable from the stated substrate. If it could be looked up, it is Stock.
- **Implied**: not stated in the substrate, but follows mechanically from it by standard inference. If it could be derived, it is Implied.
- **Selected**: a curatorial choice from a visible option space. The value is in which and in what order, not in new content.
- **Original**: survives all three tests. Not retrievable, not derivable, not a selection: content that had to be made.

One dominant tag per stratum.

## Rules

- Judge THIS document against THE STATED telos and substrate, not against what the text might be for in general.
- Never compute or report any aggregate, ratio, or derived metric. Seven rows, nothing above them.
- For a `corpus` substrate you may search the substrate to check whether content is retrievable; record what you found in `evidence`. For `public` and `context` substrates, work from the document and general literacy alone.
- Every row carries evidence. A row without evidence is invalid.

## Output

Reply with one JSON object and nothing else:

```json
{
  "doc": "<the document id you were given>",
  "ledger": {
    "grammatica":  {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "dialectica":  {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "rhetorica":   {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "arithmetica": {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "geometria":   {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "musica":      {"compressed": 0, "intensity": "Stock", "evidence": ""},
    "astronomia":  {"compressed": 0, "intensity": "Stock", "evidence": ""}
  },
  "notes": "anything anomalous, one line"
}
```

All seven strata present, `compressed` a positive integer, `intensity` from the four-tag vocabulary exactly.
