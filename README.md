# ISDA: Irreducible Semantic Density Analysis

A framework, a Claude Code skill and a Python package for asking a precise question of any written text:

> **How much of this text is doing irreducible work toward its purpose, and across which strata does that work live?**

ISDA decomposes a text into seven strata taken from the classical liberal arts: three trivium strata for form (Grammatica, Dialectica, Rhetorica) and four quadrivium strata for substance (Arithmetica, Geometria, Musica, Astronomia), the latter organized by the Nicomachan-Boethian 2x2. Each stratum is a conditional Kolmogorov complexity against progressively richer context, and each carries one intensity tag from a four-level ladder (Stock, Implied, Selected, Original). The analysis is always relative to a stated telos (what the text is trying to achieve) and a named retrieval substrate (the knowledge base against which "retrievable" is defined). Change either and the same text gets a different answer.

The framework is grounded in Kolmogorov complexity (Kolmogorov 1965), Uniform Information Density (Aylett and Turk 2004; Wilmot and Keller 2020), propositional idea density (Kintsch 1974; CPIDR, Brown et al. 2008), and the result that language models are compressors (Delétang et al. 2023).

## The core idea

Kolmogorov complexity asks the wrong question. `K(x)` is the length of the shortest program producing string `x`. It is machine-independent, elegant, and uncomputable. It is also agnostic to purpose. A random string has maximum `K` and zero value; a cliché has low `K` and also zero value. Useful text occupies a middle region Kolmogorov cannot locate, because "useful" is not a property of the string.

Telos-relative complexity is the right question. Define `K_τ(d, t) = min{K(x) : achieves(x, t)}`: the length of the shortest document that achieves the same task as `d`. This binds meaning to purpose and makes the quantity tractable via task performance, embedding similarity, or human judgment. A 5,000-word essay may be bloated for "summarize the thesis" and lean for "teach this to a novice." The text is unchanged; the question is different.

Novelty is per-stratum, not global. A text's work lives across seven strata, and at each stratum its content sits at one of four intensities. A lyric poem can be Musica-Original while remaining Dialectica-Stock. An argumentative essay can be Dialectica-Original while remaining Musica-Stock. A textbook passage can read Stock across all seven strata. All three are valid and informative readings.

## The seven strata

The quadrivium strata recover a 2x2 classification that Nicomachus of Gerasa makes explicit in *Introduction to Arithmetic* I.2-3 (c. 100 CE) and Boethius transmits in *De Institutione Arithmetica* I.1 (c. 500 CE): discrete or continuous quantity, crossed with at-rest or in-motion state.

### Trivium: form (arts of the word)

| # | Stratum | Measure |
|---|---------|---------|
| 1 | **Grammatica** | `K(sentence-forms(d) | G_grammar)` |
| 2 | **Dialectica** | `K(claims(d) | Closure(KB, R))` |
| 3 | **Rhetorica** | `H(decisions(d) | Δ)`, with the five canons (inventio, dispositio, elocutio, memoria, pronuntiatio) as internal substructure |

### Quadrivium: substance (arts of number)

|  | **at rest** | **in motion** |
|---|---|---|
| **discrete** | **Arithmetica** (propositional density via Kintsch and CPIDR) | **Musica** (local prosody via Aylett-Turk UID) |
| **continuous** | **Geometria** (document architecture) | **Astronomia** (global trajectory via Wilmot-Keller UID) |

Musica and Astronomia share one backbone: deviation from Uniform Information Density, read at local scale (prosody) and at global scale (trajectory). The decomposition is approximate, since strata interact, and it is useful enough to structure both analysis and editing. [`theory.md`](theory.md) and [`reference.md`](reference.md) give the historical and formal treatment.

## The intensity ladder

Each stratum carries one dominant tag:

| Level | Name | Meaning |
|---|---|---|
| 1 | **Stock** | cheap to specify given the named substrate |
| 2 | **Implied** | in the deductive closure of substrate and inference rules |
| 3 | **Selected** | chosen from a visible option space |
| 4 | **Original** | irreducible against full context |

The ladder prices specification, not truth. A claim and its negation cost the same to specify given the same substrate, so a text that systematically negates its substrate reads Stock while being highly contributory. Read Stock as "the substrate makes this cheap to say", never as "the substrate says this."

## The metrics

```
K_τ(d, t)  ≈  Σᵢ wᵢ(t) · Sᵢ(d)                           telos-weighted complexity
SCR(d, t)  =  |d| / K_τ(d, t)                            how far length exceeds necessity
ND(d, C)   =  Σᵢ intensity_weight(Sᵢ) · |Sᵢ| / Σᵢ |Sᵢ|      share of the core at higher intensity
RI(d, KB)  =  Σᵢ retrievable_weight(Sᵢ) · |Sᵢ| / Σᵢ |Sᵢ|    share of the core the substrate makes cheap
```

An analyst writes a seven-row ledger (a compressed size and an intensity tag per stratum) and the tools compute the three metrics from it. ND and RI are byte-weighted sums and are always computed, never estimated by eye.

Independent raters given the same document disagree on compressed sizes by about a factor of 1.2 either way, which propagates to **SCR ±0.26 · ND ±0.05 · RI ±0.07** (medians over the 19 of 20 rated documents whose ledgers score, three raters of one model family; [`corpus/rating/`](corpus/rating)). That interval is reliability, not validity: `K` is uncomputable, and raters can agree and be wrong together.

## Judgment and measurement

A stratum is a row in the ledger, filled by the analyst's judgment. A measure is mechanical evidence, and a stratum may have none. The package keeps the two apart and holds every claim to one rule: **a measure that makes a claim must name a perturbation that destroys what it reads, and a null model that says what no signal looks like.** A trajectory measure has to move when paragraphs are shuffled and again when they are reversed. A propositional measure has to move when the words are scrambled. The registry refuses a claim whose declared falsifiers cannot touch the features it reads, and the falsifier harness runs each declaration against a corpus.

| Stratum | Registered measures | Needs |
|---|---|---|
| Arithmetica | `arithmetica.propositional-density` (CPIDR idea density, English) | `[nlp]` |
| Geometria | `shape.chunk-length-median`, `shape.paragraph-length-median`, `shape.heading-tree-depth`, `shape.heading-branching`, `shape.section-size-dispersion`, `shape.block-kind-entropy`, `shape.skipped-heading-levels` | nothing |
| Musica | `musica.surprisal-variance` (variance of per-token surprisal under GPT-2-small) | `[surprisal]` |
| Astronomia | `astronomia.surprisal-slope`, `astronomia.surprisal-peak-position` | `[surprisal]` |
| Grammatica, Dialectica, Rhetorica | none: these are read by the analyst | |

[`data/measures.json`](data/measures.json) is generated from the registry and records every measure's construct, falsifiers, null model, status and how to read it. The gate results behind each status are in [`corpus/exhibits/`](corpus/exhibits).

## Worked examples

Three worked examples in [`examples.md`](examples.md) exercise the framework across its range.

**Hopkins, "Pied Beauty"** (75 words, curtal sonnet, public domain). The case for Musica as a stratum of its own. Musica reads Original on four of eleven lines, and all four intensity levels appear in one short poem. `SCR = 1.80` and `ND = 0.570`: novelty concentrated in one stratum, with Musica alone 150 of the 320-byte core.

**"The Problem of Defaults"** (1,058 words, argumentative essay). Dialectica-Original in six of eleven paragraphs, Musica-Selected, Astronomia-Selected. `SCR = 4.07` and `ND = 0.893`. The originality is in the inferential claims, not the rhythm or the arc.

**"How Photosynthesis Works"** (861 words, expository passage). All seven strata read Stock. `SCR = 29.70`, `ND = 0`, `RI = 1.000`. A textbook passage doing its job has no originality at any stratum, and an SCR above 20 is right for pedagogical elaboration.

Every metric above is computed by `isda score`, and a test checks these figures against the specimens in [`corpus/specimens/`](corpus/specimens).

## Installation

As a Claude Code skill:

```bash
git clone https://github.com/vincitamore/ISDA.git ~/.claude/skills/isda
```

Then, in any Claude Code session: *"run ISDA on this text, telos is X, substrate is Y"*.

As a Python package, from a clone:

```bash
pip install -e .                    # the core, no dependencies
pip install -e ".[nlp]"             # adds CPIDR (then: python -m spacy download en_core_web_sm)
pip install -e ".[surprisal]"       # adds the GPT-2 surprisal measures
```

[`INSTALL.md`](INSTALL.md) covers Claude Desktop and standalone use.

## The command line

The package installs four verbs. Each takes `--json` for a machine-readable envelope: success is `{"ok": true, ...}` with `ok` first, failure is `{"ok": false, "error": {"code", "message"}}`. Exit codes are `0` success, `1` the run completed and found something to act on, `64` usage error or malformed input, `70` an internal bug.

```bash
isda measure  FILE [--telos T] [--substrate S] [--detail rows.jsonl]
isda analyze  FILE --ledger LEDGER [--telos T] [--substrate S]
isda score    LEDGER [--document FILE] [--substrate-file FILE]
isda measures [--write] [--check]
```

**`measure`** reports what is mechanically true of one document: source-level facts (bytes, block mix) and prose-view statistics (words, sentences, paragraphs) as separate blocks, plus the value of every active measure. A measure whose optional backend is not installed reports `unavailable`.

**`score`** is the ledger arithmetic: SCR, ND and RI over a completed seven-row ledger, with each metric's arithmetic shown. Pass `--document` to enable the compression floor, a one-sided check that refuses a core larger than a known lossless encoding of the text.

**`analyze`** is the full report: the seven-row stratum profile first, the scalars beneath it with the inter-rater interval beside them, then the mechanical evidence. It refuses a ledger whose `raw_bytes` disagrees with the document.

**`measures`** prints the registry. `--write` regenerates `data/measures.json`; `--check` exits 1 if the file differs from the registry.

The standalone [`isda_preprocess.py`](isda_preprocess.py) is a single file with no dependencies that the skill calls for counts and for `--ledger` scoring. It carries its own copy of the metric arithmetic, and a test scores every specimen ledger through both paths and requires identical output.

## The corpus

[`corpus/`](corpus) holds what the measures are tested on.

- **Block A** is 120 chapters of the public-domain Berean Standard Bible across eight genres: genre varies while translator and markup stay constant. The repository carries the chapter list and content hashes; `python -m isda.corpus build-a` fetches the text and builds the block.
- **Block B** is 198 documents of working markdown in seven genres, sampled from a private document tree. The repository carries opaque ids, genre labels, hashes and sizes. To test measures on your own documents, write a `corpus/block-b.config.json` and run `python -m isda.corpus build-b`.
- **Specimens** are ten short documents, each with a ledger and a set of executable assertions about it. `python -m isda.specimens run` evaluates them and reports how many pass, fail, or have no instrument.
- **Exhibits** are the recorded gate results for each measure, the inter-rater study, and a study of claims against their negations: compressors respond to how far a sentence departs from the substrate's wording, and a reading judge responds to whether the substrate supports it.

## What's in this repo

| Path | Purpose |
|------|---------|
| [`SKILL.md`](SKILL.md) | The Claude Code skill: analysis protocol, strata, intensity ladder, metrics, output template. |
| [`reference.md`](reference.md) | Formal definitions, the Nicomachan-Boethian 2x2 with primary-source attribution, caveats. |
| [`theory.md`](theory.md) | The longer theoretical paper, with prior-art survey and references. |
| [`examples.md`](examples.md) | Three worked examples analyzed end to end. |
| [`isda_preprocess.py`](isda_preprocess.py) | The standalone preprocessor and ledger scorer. |
| [`src/isda/`](src/isda) | The package: document model, measure kernel, registered measures, ledger arithmetic, CLI. |
| [`corpus/`](corpus) | Corpus blocks, specimens, the rating study and the exhibits. |
| [`scripts/`](scripts) | The gate script behind each exhibit, the rating tools and the entailment study. |
| [`data/measures.json`](data/measures.json) | The generated record of every registered measure. |
| [`INSTALL.md`](INSTALL.md) | Installation paths. |

## When to use ISDA

Editing your own writing. Find which stratum carries your novelty and which strata are scaffolding; cut at the right level.

Locating originality. See at which stratum a text adds something against a named corpus, and that the other strata read Stock where they should.

Compression targets. Produce tweet, paragraph, abstract, or essay versions that preserve the telos under the stratum profile.

Editorial feedback. "Your Dialectica is Original in ¶1, 3, 5, 7, 9; your Musica is Selected; your Astronomia is Stock; the essay's work lives in the inferential moves, not the rhythm or the arc" is actionable in a way "the paper is too long" is not.

Auditing loaded text. A memory index, a skill, a checklist or a runbook is billed on every load. The firing test in `SKILL.md` finds the bytes that cannot change what the reader does next.

Prompt compression. Treat the prompt as `d`, the desired completion as `t`, and minimize `K_τ(prompt, t)` empirically.

## When not to use ISDA

As a judgment on rhetorical or aesthetic value. The framework measures semantic load against a stated task. An efficient text can still be unpersuasive; an inefficient text can still be artful.

Without naming a telos and a substrate. The numbers will look rigorous and mean nothing.

As a rigid editor. The analysis informs judgment; it does not replace it. `K` and `K_τ` are uncomputable, and every reported number is an estimate with its inputs visible.

## References

- Kolmogorov, A. N. (1965). *Three approaches to the quantitative definition of information.*
- Shannon, C. E. (1948). *A mathematical theory of communication.*
- Nicomachus of Gerasa (c. 100 CE). *Introduction to Arithmetic*, I.2-3 (D'Ooge trans. 1926).
- Boethius (c. 500 CE). *De Institutione Arithmetica*, I.1 (Masi trans. 1983).
- Aylett, M. and Turk, A. (2004). *The smooth signal redundancy hypothesis.* Language and Speech 47(1).
- Levy, R. and Jaeger, T. F. (2007). *Speakers optimize information density through syntactic reduction.* NIPS.
- Kintsch, W. (1974). *The Representation of Meaning in Memory.*
- Brown, C. et al. (2008). *Automatic measurement of propositional idea density from part-of-speech tagging.* (**CPIDR**)
- Wilmot, D. and Keller, F. (2020). *Modelling suspense in short stories as uncertainty reduction over neural representation.* ACL.
- Schulz, P., Patrício, C. and Odijk, J. (2024). *Narrative Information Theory.* NeurIPS Workshop, arXiv:2411.12907.
- Reagan, A. J. et al. (2016). *The emotional arcs of stories are dominated by six basic shapes.* EPJ Data Science.
- Delétang, G. et al. (2023). *Language modeling is compression.* arXiv:2309.10668.
- Cilibrasi, R. and Vitányi, P. (2005). *Clustering by compression.*
- Barthes, R. (1970). *S/Z.*
- Coh-Metrix (Graesser, McNamara et al. 2004, 2011); Biber, D. (1988) *Variation Across Speech and Writing.*

The full reference list is in [`theory.md`](theory.md).

## License

MIT. See [`LICENSE`](LICENSE). One file, `src/isda/measures/arithmetica_cpidr.py`, is GPL-2.0: it is the only file that imports the GPL-2.0 `ideadensity` package, which it imports when the measure runs with the `[nlp]` extra installed.
