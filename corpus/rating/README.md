# Inter-rater ratings

How far apart do independent analysts land on the same document? Twenty documents are each rated across the seven strata by several raters, and the spread of their ledgers is the interval `isda analyze` prints beside SCR, ND and RI. Nineteen of the twenty produce that interval: for the 577-byte poem every rater's compressed sizes total more than twice its length, the scorer refuses such a ledger, and the poem contributes size spread and tag agreement only.

```
documents.json                              the twenty documents, with the telos and substrate given to every rater
protocol.md                                 the instructions a model rater receives
ratings/<family>/<rater>/<document>.json    one ledger per rater per document
```

`python scripts/rating-agreement.py` recomputes the analysis from the rating files and writes `corpus/exhibits/inter-rater.json`.

## The ratings

`ratings/grok/r1`, `r2` and `r3` are three independent runs of one model (`grok-4.5-build`) over all twenty documents, each given the instructions in `protocol.md`. The protocol's test for Stock is that the content could be looked up in the substrate.

Ten of the documents are the corpus specimens, and their rows carry the rater's evidence. The other ten come from the private working-markdown block (`corpus/block-b.json`). Their rows carry compressed sizes and intensity tags only, because the evidence quotes private text. The analysis reads sizes and tags, and takes each private document's length from `block-b.json`, so the exhibit reproduces from the files in this repository.

## Adding a rater

A model, through any OpenAI-compatible endpoint:

```
python scripts/rate-with-model.py --base-url http://127.0.0.1:8080/v1 --model MODEL --family FAMILY --rater r1
```

It rates the ten specimens, whose substrate is public or carried in the document. A corpus-tier document is judged against a knowledge base the model cannot search through this script, and a rater who cannot check retrievability is pushed toward `Original`.

A person:

```
python scripts/rate.py                 # start, or resume at the next unrated document
python scripts/rate.py --tags-only     # skip the size question
```

The walk-through shows one document with its telos and substrate, asks one or two questions per stratum, and writes the file when the document is finished. `q` quits; finished documents are already saved and the one in progress is not. `?` skips a stratum, which is then left out of the file. Documents are interleaved by kind, so a rater who stops early has still rated a mix. Before rating a specimen, do not read its `analysis.md`, `ledger.json` or `expected.json`: they carry an existing reading of the same text.

## Reading the results

No rater is ground truth. `K` is uncomputable: there is no true compressed size for Musica in a Hopkins poem, and no rater, human or model, has access to one. Agreement between raters measures reliability, and raters can agree and be wrong together.

Raters of one family share its biases, so agreement within a family says less than agreement across families. Three runs of one model tighten a within-family mean. A second family, model or human, is what tests whether the reading holds outside it. Where two families agree on a stratum, their tags are interchangeable there; where they differ, neither is the reference.

A consensus across raters is a working point estimate. It is not a target to score individual raters against, since each rater agrees with a consensus of raters by construction.

Kappa is reported with raw agreement and the tag distribution beside it. On Rhetorica the raters agree on 19 of 20 documents and Fleiss' kappa is about zero, because nearly every rating is `Selected`: the coefficient falls as one tag takes over, although the raters almost always agree.
