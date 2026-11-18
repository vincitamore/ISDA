---
name: isda
description: Irreducible Semantic Density Analysis. Decomposes text into seven strata from the seven liberal arts, three Trivium (Grammatica, Dialectica, Rhetorica) plus four Quadrivium (Arithmetica, Geometria, Musica, Astronomia) organized by the Nicomachan-Boethian 2x2, relative to a stated purpose (telos) and a named retrieval substrate. Each stratum gets a conditional-complexity measure plus a dominant intensity tag (Stock, Implied, Selected, Original). An analysis without a stated telos AND a named substrate is not a weak result but a meaningless one; if the request supplies neither, ask, or state the inferred pair explicitly and analyze against it. Never report SCR/ND/RI as eyeballed figures: compute them from the ledger (`isda_preprocess.py --ledger`), because they are weighted sums that do not survive estimation. Use when asked to analyze text density, measure originality, check if something could be shorter, assess semantic compression, audit a reflex-loaded surface (memory index, skill, checklist, runbook) for bytes that do not fire, or plan an edit against a specific telos and substrate. SKIP for plain copyediting, grammar or style fixes, and generic shortening requests that carry no density, compression, or originality framing; SKIP for code-quality passes. NOT a code simplifier or code reviewer (those hunt reuse, efficiency, or bugs in a diff and then edit it): ISDA measures telos-relative semantic density across the seven strata and hands back an analysis, it does not rewrite the text.
allowed-tools: Read, Glob, Grep, Bash
---

# Irreducible Semantic Density Analysis

Estimate how much of a text is doing irreducible work toward its purpose. Answer three questions in sequence.

First: what is this text trying to do? The *telos*. Second: against what knowledge base is "retrievable" defined? The *substrate*. Third: given telos and substrate, across which of the seven strata does the text's work live, and at what intensity? The *stratum profile*.

All three answers must be explicit before the analysis means anything. Without a stated telos, the framework compresses toward an undefined target. Without a named substrate, it treats every fact as irreducible. Without stratum profiling, it collapses distinct kinds of textual work into a single number.

## What the numbers mean

A *stratum* is a ledger row populated by your judgment; a *measure* is mechanical evidence that may or may not exist for it. A stratum with no measure is normal: the analyst's judgment is the framework's substance and the numbers are anchoring evidence. `isda measures` (full package) lists every registered measure with its status, its falsifiers and its null model.

- **Solid:** byte/word/sentence/paragraph counts, shape, markup exclusion, and the `--ledger` arithmetic (SCR/ND/RI over an analyst's ledger).
- **Read with care:**
  - `stratum_raw_features.arithmetica.content_word_ratio` is a lexical ratio, **not propositional density**. It is unchanged by a global word scramble and correlates negatively with CPIDR on working markdown (ρ −0.44). Propositional density is the package's `arithmetica.propositional-density` (`[nlp]` extra).
  - `sentences.avg_length_words` and Musica's `sentence_length_mean` are the same number.
  - `structure.median_paragraph_words` measures layout-chunk size (words between blank lines, list items and headings included), not prose paragraphs.
  - Musica's `anaphora_candidates` is `status: unvalidated` (no null model, no discrimination test): a pointer for a human, never evidence.
- **No mechanical feature:** Dialectica and Rhetorica. These are judgment-only strata.
- **Package only:** Astronomia. The standalone file emits no trajectory number; the package's `astronomia.surprisal-slope` and `astronomia.surprisal-peak-position` (`[surprisal]` extra) read order and direction, and are read against the same document with its paragraphs shuffled.

Two calibration facts:

- **Lexical statistics do not see prosody.** Hopkins's "Pied Beauty", the Musica-Original worked example, is unremarkable on sentence-length and repetition counts. The package's `musica.surprisal-variance` (`[surprisal]` extra) places it at quantile 0.96 of a working-markdown corpus and moves by 0.53–0.67 of its spread when local syntax is destroyed. It carries **no genre-discrimination claim**: anchoring evidence for your Musica judgment, never a genre classifier.
- **On working markdown, three shape statistics separate genres:** section-size dispersion (ω² 0.23), skipped heading levels (0.20) and layout-chunk size (0.13), each at p = 5e-4 on a corpus of 198 documents in seven genres (dispersion is defined on 157 of them). Prose-paragraph size does not (0.01), so a paragraph statistic computed over blank-line chunks is reading layout.

## Maintaining this skill

This skill is five coupled files: `SKILL.md`, `reference.md`, `theory.md`, `examples.md`, and `isda_preprocess.py`. The vocabulary must stay identical across all five: a term renamed in one and not the others surfaces as a contradiction at the point of use. Each update below is made together with the change that causes it:

- Rename a stratum or an intensity-tag term → grep all five files for the old term and update every hit, including the preprocessor's docstring, warning strings, `--help` text, and any output notes.
- Change a formal measure, add, or remove a stratum → update the Seven Strata tables here, the per-stratum formal definitions in `reference.md`, and the treatment in `theory.md`.
- Change the preprocessor's flags or JSON output shape, or add/remove a package CLI verb → update the Preprocessing Tool section's invocation line, the verb paragraph, and the Provides / Does-not-provide table here. The canonical flag reference is `python isda_preprocess.py --help`; when the prose and `--help` disagree, `--help` is ground truth and the prose is reconciled to it.
- Change what counts as prose (`strip_markup`) or a measurement threshold (`MAX_CANDIDATES_PER_TYPE`) → say so here, because every downstream number moves and prior analyses stop being comparable. A threshold is stated with the reason for its value.
- Add a worked example → add it to `examples.md` and update the References section's example list here. Its metrics come from `--ledger`; a hand-estimated ND or RI is not admissible.
- Change an intensity weight in `ND_WEIGHT` or `RI_WEIGHT` → re-score every ledger in `examples.md` through `--ledger` in the same change, or the worked examples stop matching the tool.

## Core Concept

ISDA measures telos-relative semantic complexity decomposed across seven strata. The strata come from the Septem Artes Liberales, the seven classical liberal arts, organized via the Nicomachan-Boethian 2x2 classification of discrete versus continuous quantity crossed with at-rest versus in-motion state.

Formally:

```
K_τ(d, t) ≈ Σᵢ wᵢ(t) · Sᵢ(d)
```

where `d` is a document, `t` is the stated task, `Sᵢ` is the stratum-i conditional complexity, and `wᵢ(t)` is the telos-weight for stratum `i` (weights sum to 1). Under unspecified telos the weights are uniform. Under specific telos the weights shift toward the strata that carry the telos-relevant work.

Three consequences follow. Different telos yields different answers: a 5,000-word essay may be bloated for "summarize the thesis" and lean for "teach this to a novice." Different substrates yield different answers: a sentence that looks original against the open web may be near-duplicate of content in your own knowledge base. And novelty is not a seventh stratum; it is a per-stratum intensity tag. A text can be Musica-Original (originated rhythm), Dialectica-Original (originated inference), Astronomia-Original (originated trajectory), or any combination. The intensity ladder reports *where* the origination lives.

## Preprocessing Tool

Run the preprocessor when precision matters:

```bash
python isda_preprocess.py <file_path> --telos "<task>" --substrate "<kb>" --pretty
```

The `--telos` and `--substrate` flags are optional, strongly recommended. They get recorded in output metadata so downstream analysis carries the interpretive frame.

**Degenerate cases emit `null`, never `0.0`.** A zero reads as a measured emptiness rather than an absent measurement, and downstream arithmetic consumes it silently.

**Word tokenization is Unicode-aware** (`café` is one word).

**Markdown is excluded from prose statistics by default.** Frontmatter, fenced and inline code, HTML comments, table rows, and link targets are stripped before any word, sentence, lexical, Arithmetica, Musica, or candidate figure is computed; `total_bytes`, the paragraph statistics and section detection still read the source, and the `preprocessing` block reports exactly what was removed. On a table-heavy document, counting markup would add code tokens to the word total and fill the candidate list with syntax fragments like `| |---|---|`. Pass `--keep-markup` to measure the source verbatim.

Two consequences worth knowing before reading any number:

- **Sentence segmentation is block-aware.** A heading or list item is its own unit whether or not it ends in a period. Splitting on terminal punctuation alone would merge a whole list into one pseudo-sentence and distort every sentence-length statistic.
- **The standalone file emits no Astronomia number.** Trajectory is a property of order, and set statistics over segments are unchanged when the segments are reordered. The per-segment content-word ratio at `local_density.segments[].content_word_ratio` is inventory and says nothing about trajectory. Read the document and describe the arc yourself, or use the package's Astronomia measures.

The same tool scores a completed ledger. Once Step 2 and Step 4 are done, write the seven rows to JSON and let it do the arithmetic:

```bash
python isda_preprocess.py --ledger ledger.json --pretty
```

```json
{"raw_bytes": 14304,
 "strata": {"grammatica":  {"compressed": 85,   "intensity": "Selected"},
            "dialectica":  {"compressed": 230,  "intensity": "Implied"},
            "rhetorica":   {"compressed": 2400, "intensity": "Selected"},
            "arithmetica": {"compressed": 25,   "intensity": "Stock"},
            "geometria":   {"compressed": 95,   "intensity": "Selected"},
            "musica":      {"compressed": 70,   "intensity": "Selected"},
            "astronomia":  {"compressed": 90,   "intensity": "Selected"}}}
```

It returns SCR, ND, RI, the arithmetic behind each, every stratum's share of the core, and which stratum dominates. Accepts `-` for stdin.

**Exit codes:** `0` clean · `64` usage error (an unknown flag, a malformed ledger, a missing stratum, an unrecognized intensity tag, a zero core, an unreadable or non-UTF-8 input file). `1` is deliberately unused: it is left for *ran clean, found something actionable*, so bad input never reads as a successful run.

**Philosophy: measurement, not judgment.** The preprocessor provides hard numbers; the analyst supplies the stratum classification and intensity tags. Scoring a ledger is arithmetic over judgments already made, so it belongs on the measurement side of that line.

| Provides (facts) | Does not provide (requires judgment) |
|------------------|--------------------------------------|
| Byte, word, sentence, paragraph counts | Stratum-level classification |
| Section detection and per-section rollups | Which intensity tag applies |
| Sentence length distribution (Musica raw feature) | Whether repetition is redundancy or rhetorical device |
| Lexical statistics (TTR, hapax) | Novelty assessment |
| Content-word ratio (a lexical ratio; propositional density is the package's CPIDR measure, `[nlp]` extra) | How the stratum interacts with telos |
| Candidates flagged for review | What those candidates mean |
| SCR, ND, RI from a completed ledger (`--ledger`) | The compressed sizes and intensity tags the ledger is built from |

Anchor your analysis with the hard numbers. Do not let them constrain your judgment.

**Where the full package is installed**, four verbs sit on top of the same arithmetic: `isda measure FILE` (counts plus every active measure, source-level and prose-view facts kept separate), `isda analyze FILE --ledger L` (the stratum profile as headline, metrics beneath with the measured inter-rater interval and its scope stamped at the point of the numbers, ledger/document byte-coupling enforced), `isda score LEDGER` (the arithmetic alone), `isda measures` (the registry: every measure's status, falsifiers and null model). All take `--json` for the ok-first envelope. Some measures ride optional backends: `arithmetica.propositional-density` (`[nlp]`: spaCy + ideadensity), and `musica.surprisal-variance` and the two Astronomia measures (`[surprisal]`: GPT-2-small on CPU). On a machine without the extra they report `unavailable`, never an error or a guess. Corpus values are cached by content hash, so a warm cache answers without the backend. The single-file invocation above works on every install; reach for the package only after confirming it is present.

## The Seven Strata

Any text decomposes into seven strata, organized into two groupings.

### Trivium: form (arts of the word)

| # | Stratum | English gloss | Formal measure |
|---|---------|---------------|----------------|
| 1 | **Grammatica** ¹ | sentence-level form | `K(sentence-forms(d) \| G_grammar)` |
| 2 | **Dialectica** | derived inference | `K(claims(d) \| Closure(KB, R))` |
| 3 | **Rhetorica** ² | curatorial decisions | `H(decisions(d) \| Δ)` |

### Quadrivium: substance (arts of number), via the Nicomachan-Boethian 2x2

| # | Stratum | English gloss | Boethian sense | Formal measure |
|---|---------|---------------|----------------|----------------|
| 4 | **Arithmetica** | propositional density | discrete at rest | `\|propositions(d)\|` via CPIDR |
| 5 | **Geometria** | document architecture | continuous at rest | `K(architecture(d) \| G_geometry)` |
| 6 | **Musica** | rhythm and prosody | discrete in motion | `K(prosody(d) \| Π_local)`, local-scale UID |
| 7 | **Astronomia** | argumentative trajectory | continuous in motion | `K(trajectory(d) \| Τ_global)`, global-scale UID |

**Note on the quadrivium 2x2.** The four quadrivium strata are the four cells of a discrete/continuous × at-rest/in-motion classification that Nicomachus of Gerasa makes explicit in *Introduction to Arithmetic* I.2-3 (c. 100 CE) and that Boethius transmits verbatim in *De Institutione Arithmetica* I.1 (c. 500 CE). See `reference.md` and `theory.md` for full historical and formal treatment.

**Note on "in motion".** The rest/motion axis is not kinematic. "At rest" means the measured property is static: a proposition count, a shape whose definition does not require time. "In motion" means the measured property is temporal. In prose, reading-time is the text's motion. Musica measures rhythm at local scale (syllable, clause, sentence); Astronomia measures trajectory at global scale (document). Both are conditional-complexity measures against a Uniform Information Density baseline. See the UID unification section in `theory.md`.

---

*¹ Grammatica footnote: we use Grammatica in the narrow sense of sentence-level form. Medieval usage (Donatus, Isidore, the broader grammatica tradition) covered phonology, morphology, figures of speech, poetics, and literary-ethical criticism, much of which we split into Musica and Rhetorica here. The shrinkage is pragmatic: we preserve the name for the familiar association and narrow its scope to make the seven strata non-overlapping.*

*² Rhetorica substructure: when Rhetorica dominates an analysis, the report can drill down to the classical five canons of rhetoric, **inventio** (discovery of material), **dispositio** (arrangement), **elocutio** (style and diction), **memoria** (the orator's mental treasury), **pronuntiatio** (delivery). These are not separate top-level strata; they are the operational stages of Rhetorica. "Memoria" in the reader-side sense, meaning what the reader already holds, is handled by the substrate parameter that conditions every stratum.*

## The Intensity Ladder

Each stratum carries a dominant intensity tag from a four-level gradient. Novelty is not a seventh stratum; it is a property any stratum can have.

| Level | Name | Meaning | Conditioning |
|---|---|---|---|
| 1 | **Stock** | cheap to specify given the named substrate | `K(·\|KB)` is small |
| 2 | **Implied** | in the deductive closure of substrate and inference rules | `K(·\|Closure(KB, R))` is small, content is derivable but not stated |
| 3 | **Selected** | chosen from a visible option space | `H(·\|Δ)`, curatorial decision rather than derivation |
| 4 | **Original** | irreducible against full context | `K(·\|C) ≥ \|·\|`, algorithmic randomness relative to everything |

The progression reads as a path. Stock is what you already had. Implied is what the stock implied. Selected is what you picked from options. Original is what you made from nothing the substrate held. Each stratum gets one tag per analysis, reflecting which intensity dominates.

**Reading the tag grid.** A text where every stratum reads Stock is fully conventional: a well-written textbook passage, a reference document, a standard form letter. A text where one stratum reads Original and the others vary has a specific-origin novelty: Hopkins reads Musica-Original with Dialectica at Implied. A text where multiple strata read Original is doing several kinds of irreducible work at once, which is rare.

**Per-stratum dominant tag, not full matrix.** Intensity gets reported as a single dominant tag per stratum. Seven strata, seven tags per analysis. A full 7x4 cross-tabulation (28 cells) is rejected as output format. Reliability compounds multiplicatively across joint decisions, several cells collapse empirically, and 28 cells overflow working memory. One dominant tag per stratum, seven-row output table.

## The Retrieval Substrate

Arithmetica (propositional density against a substrate) and Dialectica (claims in the deductive closure of substrate plus rules) are defined relative to a named substrate. Three canonical tiers.

| Tier | Substrate | Example | Use when |
|------|-----------|---------|----------|
| Public | Global web, canonical texts, widely-shared priors | "The Pythagorean theorem" | Analyzing public writing, detecting derivativeness |
| Corpus | An organization's or author's knowledge base | "We established this pattern in `notes/foo.md`" | Editing against your own prior work |
| Context | Earlier in this document, conversation, or session | "As shown in section 2" | Detecting in-text redundancy |

State the tier explicitly at the start of the analysis.

## Analysis Protocol

### Step 0: state telos and substrate

Before measurement, state explicitly:

- **Telos (t):** what this text is trying to achieve (teach, argue, summarize, specify, persuade, inspire, catalog, transmit, preserve).
- **Substrate:** which of {public, corpus, context} you are evaluating retrievability against, and name the specific substrate.

If the user did not specify, ask. If asking is not possible, infer and state the assumption.

### Step 1: measure raw length and preprocessor features

Total bytes, words, sentences, paragraphs. Run the preprocessor if precision matters. Capture the sentence-length distribution (and syllable estimate), and for Arithmetica either real CPIDR (`isda measure`, `[nlp]` extra) or, where the package is absent, the content-word ratio reported under its own name.

### Step 2: build the seven-stratum ledger

```
| Stratum | Content summary | Compressed | Intensity |
|---------|-----------------|------------|-----------|
| Grammatica  |  |  | Stock/Implied/Selected/Original |
| Dialectica  |  |  | Stock/Implied/Selected/Original |
| Rhetorica   |  |  | Stock/Implied/Selected/Original |
| Arithmetica |  |  | Stock/Implied/Selected/Original |
| Geometria   |  |  | Stock/Implied/Selected/Original |
| Musica      |  |  | Stock/Implied/Selected/Original |
| Astronomia  |  |  | Stock/Implied/Selected/Original |
| TOTAL       |  |  | (n/a) |

Raw length stays a document-level figure from Step 1; it does not divide across strata.
```

### Step 3: encode each stratum

**Grammatica.** Describe the sentence-level form and any compound coinages or unusual syntactic patterns. Compress to a pointer ("standard argumentative essay sentence structure, 20-word average") or a specification for novel cases.

**Dialectica.** Encode derivable claims as `[method](inputs) → output`. Mark irreducible claims (Original intensity) separately. These are the text's originated inferential moves.

**Rhetorica.** Enumerate curatorial decisions with choice-space bits. Note which of the five canons dominates if Rhetorica is the dominant stratum.

**Arithmetica.** Report propositional density: propositions per word via CPIDR (`ideadensity`, the package's `arithmetica.propositional-density` measure, `[nlp]` extra; English-only, and it returns no value on input its guard cannot affirm as English prose). Typical ranges (`corpus/exhibits/propositional-density.json` in the package repo): working markdown (n = 193) median 0.46, IQR 0.44–0.48; public-domain prose across eight genres, medians 0.48–0.52; the expository worked example 0.51; the argumentative one 0.49. Adjective-dense lyric **exceeds** ordinary prose: Hopkins scores 0.60. Where the package is absent, report the standalone preprocessor's content-word ratio under its own name and say that it is not propositional density.

**Geometria.** Describe the document-level architecture in minimal notation. Static structure: section hierarchy, paragraph count, layout conventions.

**Musica.** Describe the rhythmic and prosodic structure. Measure deviation from the local-UID baseline: sentence-length variance, rhetorical figures (isocolon, anaphora, chiasmus, tricolon, periodic build, asyndeton), metrical patterns if present. For prose, flag rhetorical figures by location; for verse, mark meter, rhyme scheme, stress patterns.

The preprocessor does not detect isocolon or tricolon. Only an **anaphora candidate count** is emitted, explicitly tagged `status: unvalidated`: it has no null model and no discrimination test, and is a pointer for a human, never evidence of rhetorical density. Detecting rhetorical figures is an open research problem (the best supervised chiasmus classifiers reach F1 ≈ 0.78 *with* training data), so do the prosodic reading yourself.

In documents read under time pressure, typographic stress (ALL-CAPS or bold at the exact word where a rule bites) is prosodic work: it raises information at the point of highest surprisal, which is local-UID deviation in the same sense as a metrical stress. It sits on the Musica/Rhetorica-elocutio boundary; assign it and say which side you chose.

**Astronomia.** Describe the global trajectory. Measure deviation from the global-UID baseline: does information intensity flow uniformly over document position, or does it peak at specific points? Is the argumentative or narrative arc conventional for the genre or originated by the author? For narrative texts, map the dramatic curve; for argumentative texts, map the thesis-unfolding pattern.

### Step 4: assign intensity tags

For each stratum, ask: against the stated substrate and telos, is the stratum's content at Stock, Implied, Selected, or Original intensity? Apply the conservative discipline. If a move could be retrieved from the substrate, it is Stock; so is anything else that is cheap to specify from the substrate, such as the plain negation of something it says. If it could be derived from substrate plus standard rules, it is Implied. If it is a curatorial choice from a visible option space, it is Selected. Only content that survives all three tests is Original.

### Step 5: compute metrics

**Semantic Compression Ratio (SCR):**
```
SCR(d, t) = |d| / K_τ(d, t)
         ≈ |d| / (S₁ + S₂ + S₃ + S₄ + S₅ + S₆ + S₇)_compressed
```

Compute all three from the ledger rather than estimating them:

```bash
python isda_preprocess.py --ledger ledger.json --pretty
```

SCR is a ratio an analyst can carry in their head; ND and RI are **byte-weighted sums over the compressed ledger** and do not survive estimation. If a report states ND or RI, it states the arithmetic that produced them.

**How much precision to claim.** Three independent raters given the same 20 documents disagree on compressed-size estimates by roughly a factor of 1.2 either way (per-stratum log2 SD 0.28–0.42; `corpus/exhibits/inter-rater.json` in the package repo). Propagated through the ledger arithmetic that is **SCR ±0.26 · ND ±0.05 · RI ±0.07**, the medians over the 19 documents whose rated ledgers score. When comparing documents, quote SCR to one decimal and ND/RI to two: a difference in the third decimal is far inside rater disagreement. Three caveats travel with those figures. It is **reliability, not validity**: raters landing near each other says nothing about landing near the truth, since `K` is uncomputable and raters can agree and be wrong together. It is **within one model family**, so read it as a floor on disagreement. And it is a **median over a wide spread**: per-document SCR SD runs from 0.04 to 1.81, so a document the raters read unevenly carries a much larger interval than the headline.

**Novelty Density (ND):** the share of the *compressed core* carried by higher-intensity strata, weighted by compressed bytes rather than by stratum count.
```
ND(d, C) = Σᵢ (intensity_weight(Sᵢ) · |Sᵢ|_compressed) / Σᵢ |Sᵢ|_compressed
```
where `intensity_weight` maps Stock → 0.0, Implied → 0.1, Selected → 0.3, Original → 1.0.

**Retrievability Index (RI):** the share of the *compressed core* that is nonetheless substrate-retrievable, weighted by compressed bytes.
```
RI(d, KB, R) = Σᵢ (retrievable_weight(Sᵢ) · |Sᵢ|_compressed) / Σᵢ |Sᵢ|_compressed
```
where `retrievable_weight` maps Stock → 1.0, Implied → 0.7, Selected → 0.0, Original → 0.0.

Three properties of RI to state whenever you report it. It is defined over **compressed** sizes, so it answers "how much of the irreducible core is a pointer into the substrate", not "how much of this text could be looked up". The second is the question the word *retrievability* suggests, and the ledger cannot answer it, because strata overlap and raw bytes do not partition across them. Because Stock content compresses to a pointer by definition, Stock strata contribute little to the denominator; RI is therefore pulled toward 0 on most documents and reaching 1.0 requires an all-Stock ledger. An all-Stock ledger scores exactly 1.0.

And **read it as substrate specifiability, not as truth-directionality.** The ladder measures how cheap content is to *specify* given the substrate, never whether the substrate *asserts* it, so a document that systematically negates its substrate scores high RI while being maximally contributory. Cheap-to-say is not agrees-with. Do not read high RI with a Stock-dominant profile as low contribution; the ladder prices specification cost, not agreement.

The same overlap is why the ledger carries no per-stratum raw-byte column: one sentence feeds Grammatica, Arithmetica, and Musica at once, so any raw allocation across strata double-counts. Raw length is a document-level quantity only.

### Step 6: local density rollup

Global metrics lie about uneven texts. Report per-segment density. Segment the text by detected sections, or by equal chunks if no structure. For each segment, report the dominant stratum and intensity. Report the median dominant intensity, the peak stratum, the trough segment, and the range.

### Step 7: compression curve

For each target `L ∈ {280, 800, 2000, 5000}`, extract the `L` highest-intensity bytes (Original first, then Selected, then Implied, then Stock). Check whether the extracted bytes achieve telos `t`. Report the curve.

## Interpretation Guide

### SCR (Semantic Compression Ratio)

The bands below are calibrated for argumentative and original prose: essays, reports, analyses. They do not apply uniformly to expository and pedagogical prose (textbook passages, tutorials, reference documentation), where elaboration is part of the telos. A passage teaching a novice needs many more bytes than the minimum pointer-set identifying the same content against a reference substrate, and that elaboration is correct, not bloat. When the telos is pedagogy, read SCR as a scaffolding ratio, not a bloat indicator.

| Value | Argumentative or originated prose | Expository or pedagogical prose |
|-------|-----------------------------------|----------------------------------|
| < 2 | Extremely dense (Hopkins "Pied Beauty" sits near 1.8) | Aphoristic; likely insufficient for teaching |
| 2-5 | Well-developed, efficient ("The Problem of Defaults" sits near 4.1) | Terse; suitable as reference or reminder |
| 5-10 | Expansive, could be condensed | Well-developed explanatory prose |
| 10-20 | Verbose; core buried in padding | Expansive teaching with examples and motivation |
| > 20 | Severely bloated for an argument | Full introduction with scaffolding, correct for pedagogy ("How Photosynthesis Works" sits near 30) |

Read the number alongside the stated telos and the dominant-intensity profile.

### Reflex-loaded prose: a third reading, where retrievability inverts

A third genre sits outside both columns: text whose telos is **pre-retrieval availability**. A memory index, a skill body, a checklist, a runbook's reflex section, a system prompt. These are *loaded*, not read: paid for on every load, consulted under time pressure, and written to fire before the reader would think to look anything up.

For this genre the standard reading of RI is backwards. A high RI normally says "this text restates its substrate and could be cut." But a reflex surface exists precisely to put substrate content in front of the reader *without a retrieval*, so duplication is the function, not the waste. Do not cut a byte because it is retrievable.

Cut on a different test instead.

> **The firing test.** Can this byte change what the reader does next, *without* their consulting the thing it points at? If it cannot, it belongs in the target, not in the index.

Bytes that fail the firing test are the real waste in reflex prose, and they are invisible to SCR, ND, and RI alike. Three recurring failure shapes:

- **Opaque compression.** A phrase that means something only after you have read its target ("check the second column first"). It costs bytes every load and fires for nobody.
- **Incident provenance.** The measurement or date that generated the rule, carried alongside the rule: the latency figure that prompted "warm the cache first", the date a rule was broken. The rule fires; the story behind it does not. Provenance belongs in the target.
- **Procedural narration.** Descriptions of how the surface is maintained, sitting inside the surface it maintains.

When analyzing a reflex surface, report a **fire rate** alongside the standard metrics: what fraction of raw bytes passes the firing test. That is the number an editor can act on, and unlike RI it is computed over raw bytes, so it speaks about the text rather than about its irreducible core.

### ND (Novelty Density), read with intensity tags

| Dominant intensity | Meaning |
|---|---|
| Mostly Stock | Fully conventional; the text transmits known content |
| Mostly Implied | Derivative but richly connected; makes known inferences from known substrate |
| Mostly Selected | Curatorial work dominates; value is in arrangement and framing, not new claims or rhythms |
| One stratum Original, others lower | Specific-origin originality; the contribution lives in one stratum |
| Multiple strata Original | Multi-axis originality; the text does several kinds of irreducible work at once. Rare. |

### Stratum profile shapes (common cases)

| Genre | Expected profile |
|---|---|
| Lyric poetry | Musica-Original or Selected, Rhetorica-Selected, Arithmetica-Stock, others vary |
| Textbook passage | Seven Stock |
| Argumentative essay | Dialectica-Selected or Original, Rhetorica-Selected, Musica-Selected, others Stock |
| Research paper | Dialectica-Original, Geometria-Selected or Stock (IMRaD), Arithmetica higher-density, others Stock |
| Legal brief | Grammatica-Selected (long periodic clauses), Geometria-Selected (hierarchical), Dialectica-Original or Implied, others Stock |
| Sacred text translation | Musica-Original (translator's rhythm choices), Rhetorica-Original, others inherit from source |
| Reflex index (memory store, skill, checklist) | Rhetorica-Selected dominant and carrying most of the mass (the curation *is* the artifact), Geometria-Selected, Dialectica and Arithmetica-Stock against the targets it points at. Read with the firing test, not with RI |

**Read this table as expectations, not as discriminators, and know which cells are near-constant.** Across 20 documents rated by three independent raters (ten specimens and ten working-markdown documents), the seven strata differ sharply in how much their tag varies:

| Stratum | Tag agreement | What that means for your ledger |
|---|---|---|
| **Rhetorica** | **59 of 60 ratings read `Selected`** | The tag is effectively a constant. Writing "Rhetorica: Selected" discriminates almost nothing: the *compressed size* is where Rhetorica carries information, not the intensity tag |
| Grammatica | 0.90 unanimous, mostly `Stock` | Stable and usually conventional; a non-Stock reading is a real signal worth justifying |
| Arithmetica, Musica | 0.75 / 0.70 unanimous | Reliable; these tags mean what they say |
| Geometria, Astronomia | 0.65 / 0.70 unanimous | Moderate; expect disagreement at the margins |
| **Dialectica** | **0.45 unanimous, tags spread across all four** | The hardest call in the framework. Two careful analysts often disagree, so say what you relied on |

A tag that never varies is not evidence of anything, however confidently assigned; a tag analysts split on is where your reasoning has to be visible.

## Output Template

```
## ISDA Analysis: [Title]

Telos:      [what this text is trying to achieve]
Substrate:  [public / corpus / context], [named substrate]
Raw length: X bytes, X words, X paragraphs
Genre:      [type]

### Stratum Ledger

| Stratum     | Content summary        | Compressed | Intensity |
|-------------|------------------------|------------|-----------|
| Grammatica  | [sentence-level form]  | X B        | Stock/Implied/Selected/Original |
| Dialectica  | [inferences]           | X B        | ... |
| Rhetorica   | [curatorial decisions] | X B        | ... |
| Arithmetica | [propositional density]| X prop/word| ... |
| Geometria   | [architecture]         | X B        | ... |
| Musica      | [prosody, rhythm]      | X B        | ... |
| Astronomia  | [trajectory]           | X B        | ... |

### Global Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| SCR    | X.X ±0.26 | [telos-contextualized reading] |
| ND     | X.XX ±0.05 | [dominant-intensity reading; name the dominant stratum's share of the core] |
| RI     | X.XX ±0.07 | [substrate-contextualized; "of the core", not "of the text"] |

All three from `--ledger`. The intervals are the measured inter-rater spread: reliability, not accuracy. Carry the caveats from Step 5 whenever you quote them. Add one row for a reflex-loaded surface:

| Fire rate | X% of raw bytes | [what fails the firing test, and where those bytes belong instead] |

### Local Density (optional, for uneven texts)

[Per-segment dominant stratum and intensity]

### Compression Curve

| Target | Preserves telos? | Which intensity levels fit |
|--------|------------------|---------------------------|
| 280 c  | YES/NO/PARTIAL | Original only |
| 800 c  | YES/NO/PARTIAL | Original plus top Selected |
| 2000 c | YES/NO/PARTIAL | Original, Selected, Implied anchors |
| 5000 c | YES/NO/PARTIAL | All of the above plus Stock scaffolding |

### Key Findings

[2-4 sentences on what the analysis reveals. Always relative to the stated telos and substrate. Name the dominant-intensity profile.]
```

## Caveats

Telos is the biggest variable. Any result without one is ambiguous at best, misleading at worst.

Substrate matters as much as telos. A paragraph is not retrievable; a paragraph against substrate X is.

Intensity tags are per-stratum dominant readings, not full matrices. A 28-cell cross-tabulation is the wrong output format. One dominant tag per stratum.

The Musica and Astronomia unified-UID spine means both temporal strata are measured as deviation from a uniform information-density expectation, at local (prosodic) and global (trajectory) scales. One theoretical framework, two scale instantiations, grounded in Aylett and Turk 2004 (local) and Wilmot and Keller 2020 (global). See `reference.md` section on UID-at-dual-scales.

The Grammatica and Musica boundary can fuzz on metrical texts. Metrical form belongs to Musica; syntactic form belongs to Grammatica. A sonnet's iambic pentameter is Musica; its 14-line-with-volta structure is Grammatica (or Geometria, a single-line-vs-multi-line boundary that is itself fuzzy). Be explicit about where you draw the line.

Rhetorica shrinks the medieval art. Classical rhetorica is the full persuasive enterprise (Cicero's five canons and so on); we use it narrowly for curatorial decisions. The five canons live as internal substructure when Rhetorica dominates.

Cross-stratum interactions exist. Original claims (Dialectica-Original) can retroactively change what is Stock (Arithmetica). The decomposition is approximate, not exact. Name the caveat, report the dominant cell, move on.

`K` and `K_τ` are uncomputable. You are producing principled estimates, not measurements. Say so.

## References

- [`reference.md`](reference.md): formal conditional-complexity treatment, Nicomachan-Boethian 2x2 detail, per-stratum formal definitions, UID-at-dual-scales unification.
- [`theory.md`](theory.md): consolidated paper with prior-art survey, Solomonoff-Hutter compression-intelligence link, LLM-as-decompressor hypothesis.
- [`examples.md`](examples.md): three worked examples. Hopkins "Pied Beauty" (Musica-Original lyric), "The Problem of Defaults" (Dialectica-Original argumentative essay), "How Photosynthesis Works" (seven Stock textbook passage).
- `isda_preprocess.py`: the measurement tool this skill drives; its `--help` is the canonical flag reference. It sits beside this file in the skill directory.

Keep the five files' vocabulary identical; see Maintaining this skill.
