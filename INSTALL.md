# Installation

ISDA is a Claude Code skill, a standalone Python preprocessor, and a Python package. Install whichever you need.

## 1. As a Claude Code skill

Claude Code loads skills from `~/.claude/skills/<skill-name>/`. Clone this repo into that path:

```bash
git clone https://github.com/vincitamore/ISDA.git ~/.claude/skills/isda
```

On Windows:

```powershell
git clone https://github.com/vincitamore/ISDA.git "$env:USERPROFILE\.claude\skills\isda"
```

Open any Claude Code session and the skill is discovered automatically. Invoke it in natural language:

```
Run ISDA on the essay I just pasted. Telos: deliver the central claim to a
policy reader. Substrate: public.
```

Or by name:

```
/isda telos="teach this to a novice" substrate="standard biology textbook"
```

Claude Code loads `SKILL.md`, runs the analysis protocol, calls the preprocessor for counts and ledger scoring, and produces the output template. It reads `reference.md`, `theory.md` and `examples.md` on demand; the rest of the repository does not interfere with the skill loader.

## 2. With Claude Desktop or claude.ai

These have no skill loader. Paste the contents of [`SKILL.md`](SKILL.md) into a project's custom instructions or a conversation's system prompt, then ask for the analysis on any text you provide. For a short conversation, the core concept, the seven strata, the analysis protocol and the output template are enough.

Neither runs local code, so the preprocessor is unavailable there: the analysis proceeds without mechanical counts, and SCR, ND and RI have to be computed from the ledger by hand or left out.

## 3. The standalone preprocessor

`isda_preprocess.py` is a single Python 3.10+ file with no dependencies outside the standard library:

```bash
git clone https://github.com/vincitamore/ISDA.git
cd ISDA

python isda_preprocess.py path/to/text.md \
    --telos "deliver the thesis to a general reader" \
    --substrate "public web" \
    --pretty
```

| Flag | Purpose |
|------|---------|
| `<file>` | Path to the text file to analyze. |
| `--text "<inline text>"` | Analyze inline text instead of a file. |
| `--stdin` | Read text from stdin. |
| `--telos "<task>"` | Recorded in the output metadata; a warning is emitted without it. |
| `--substrate "<kb>"` | Recorded in the output metadata; a warning is emitted without it. |
| `--keep-markup` | Measure the source verbatim instead of excluding markup from prose statistics. |
| `--ledger <file>` | Score a completed seven-row ledger into SCR, ND and RI (`-` reads stdin). |
| `--ledger-document <file>` | With `--ledger`: the source document, which enables the compression floor. |
| `--ledger-substrate <file>` | With `--ledger`: substrate text for a tighter, substrate-primed floor. |
| `--pretty` | Pretty-print the JSON output. |

The report is JSON:

```
_meta                 Telos, substrate, warnings
measurements          Bytes, words, sentences, paragraphs
structure             Detected sections, paragraph lengths
sentences             Length distribution
lexical               Type-token ratio, hapax ratio, word length distribution
stratum_raw_features  Arithmetica (content-word ratio), Musica (sentence-length and syllable statistics)
local_density         Per-segment rollups
candidates_for_review Flagged items: quotes, citations, repeated phrases
preprocessing         What markup was excluded
```

The preprocessor does not classify strata or assign intensity tags. It gives a semantic analyst, human or model, hard numbers to anchor on.

## 4. The Python package

From a clone, with Python 3.10+:

```bash
pip install -e .                  # core: document model, shape measures, ledger arithmetic, CLI
pip install -e ".[nlp]"           # adds CPIDR propositional density
python -m spacy download en_core_web_sm
pip install -e ".[surprisal]"     # adds the GPT-2 surprisal measures (torch, transformers)
pip install -e ".[dev]"           # adds pytest
```

The core has no dependencies. A measure whose extra is not installed reports `unavailable`. The CPIDR measure pins `ideadensity` 0.5.1 and `en_core_web_sm` 3.8.0 (the model spaCy 3.8 downloads) and reports `unavailable` under other versions, because a tagger upgrade can move every value.

```bash
isda measure path/to/text.md
isda measures
python -m pytest tests/ -q
python -m isda.specimens run
```

## 5. Framework only

Read [`SKILL.md`](SKILL.md), [`reference.md`](reference.md), and [`theory.md`](theory.md) in that order. The framework is a way of thinking about text density and is independent of any implementation.

## Verification

After a Claude Code install:

```bash
ls ~/.claude/skills/isda/SKILL.md
```

For the preprocessor:

```bash
python isda_preprocess.py --text "The quick brown fox jumps over the lazy dog." --telos "demonstrate installation" --substrate "public" --pretty
```

The output is a JSON report whose `_meta` block records the telos and substrate you supplied.

## Uninstall

```bash
rm -rf ~/.claude/skills/isda       # the skill
pip uninstall isda                 # the package
```

## Troubleshooting

**Claude Code does not see the skill.** Restart the session; the skill loader reads at startup. The directory must be exactly `~/.claude/skills/isda/` and contain `SKILL.md`.

**A measure reports `unavailable`.** Its optional backend is missing or is not the pinned version. The message names what to install.

**Running against a private knowledge base as the substrate.** The tools never call out to a knowledge base. The substrate you name is recorded in the metadata and applied by you, or by Claude, during the semantic analysis.

## License

MIT. See [`LICENSE`](LICENSE). `src/isda/measures/arithmetica_cpidr.py` is GPL-2.0.
