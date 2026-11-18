"""
The measurement corpus: hash-pinned and buildable from manifests.

The corpus is an artifact: it can be reconstructed from manifests, so findings
measured on it can be re-run and checked. What is authored is a manifest, what
is derived is hash-pinned, and a changed document is reported as stale instead
of being re-measured as different text.

Two blocks, two provenance models:

- public: block A (public-domain prose, genre-varied) is chapters of the
  Berean Standard Bible: genre varies maximally while translator and markup
  stay constant. The repo carries only a manifest of chapter references
  (`block-a.json`, authored) and a lock file of content hashes
  (`block-a.lock.json`, derived). The text itself is fetched and built into
  `corpus/cache/`, which is never committed. An upstream text change surfaces
  as a hash mismatch at build time, so the numbers cannot change without an
  error.

- private: block B (working markdown) is the kind of document the tool is run
  against, sampled from a private document tree. The repo carries only opaque
  ids, genre labels, content hashes and sizes (`block-b.json`, derived); the
  id-to-path map and the frozen text snapshots stay in gitignored local files.
  Findings about block B are checkable by anyone holding the private corpus;
  the corpus itself is not published.

Authored intent and derived state never share a file: `block-a.json` and the
local `block-b.config.json` are edited by hand, and the builders write
everything they derive (the lock file, `block-b.json`, `block-b.local.json` and
the caches).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core.tokens import words as _prose_words

# ---------------------------------------------------------------- paths

def repo_root(start: Path | None = None) -> Path:
    """The repo root: the nearest ancestor containing corpus/."""
    p = (start or Path(__file__)).resolve()
    for cand in (p, *p.parents):
        if (cand / "corpus").is_dir():
            return cand
    raise FileNotFoundError("no corpus/ directory found above " + str(p))


def _corpus_dir(root: Path | None = None) -> Path:
    return repo_root(root) / "corpus"


# ---------------------------------------------------------------- model

@dataclass(frozen=True)
class CorpusDoc:
    id: str
    genre: str
    text: str
    block: str


class CorpusUnavailable(RuntimeError):
    """The block's cache is not built on this machine. The message says how."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- block A

_VERSE = re.compile(r"^((?:[1-3] )?[A-Za-z ]+?) (\d+):(\d+)\t(.*?)\s*$")

BSB_URL = "https://bereanbible.com/bsb.txt"


def _fetch_bsb(cache: Path) -> Path:
    """Return the cached BSB source, downloading it first if it is absent."""
    target = cache / "bsb.txt"
    if not target.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(BSB_URL, timeout=60) as resp:  # noqa: S310
            target.write_bytes(resp.read())
    return target


def _parse_bsb(path: Path) -> dict[tuple[str, int], list[tuple[int, str]]]:
    """Chapter -> [(verse_number, verse_text)], in file order."""
    chapters: dict[tuple[str, int], list[tuple[int, str]]] = {}
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            m = _VERSE.match(line)
            if not m:
                continue
            book, chap, verse, text = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            if text:
                chapters.setdefault((book, chap), []).append((verse, text))
    return chapters


def _ref_to_id(genre: str, ref: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    return f"a-{genre}-{slug}"


def build_block_a(root: Path | None = None) -> int:
    """Materialize block A from the authored manifest; pin or verify hashes."""
    cdir = _corpus_dir(root)
    manifest = _read_json(cdir / "block-a.json")
    cache = cdir / "cache"
    source = _parse_bsb(_fetch_bsb(cache))
    outdir = cache / "block-a"
    outdir.mkdir(parents=True, exist_ok=True)

    lock_path = cdir / "block-a.lock.json"
    old_lock: dict[str, dict[str, Any]] = {}
    if lock_path.is_file():
        old_lock = {e["id"]: e for e in _read_json(lock_path)["documents"]}

    entries: list[dict[str, object]] = []
    stale: list[str] = []
    for genre, refs in manifest["genres"].items():
        for ref in refs:
            m = re.match(r"^(.*) (\d+)$", ref)
            if not m:
                raise ValueError(f"malformed chapter ref: {ref!r}")
            book, chap = m.group(1), int(m.group(2))
            verses = source.get((book, chap))
            if not verses:
                raise ValueError(f"chapter not found in source: {ref!r}")
            text = " ".join(v for _, v in verses) + "\n"
            doc_id = _ref_to_id(genre, ref)
            digest = _sha256(text)
            if doc_id in old_lock and old_lock[doc_id]["sha256"] != digest:
                stale.append(doc_id)
            (outdir / f"{doc_id}.txt").write_text(text, encoding="utf-8", newline="\n")
            entries.append({
                "id": doc_id, "ref": ref, "genre": genre, "sha256": digest,
                "bytes": len(text.encode("utf-8")),
                "words": len(_prose_words(text)),
            })

    if stale:
        print(f"STALE: {len(stale)} chapter(s) differ from the recorded lock: "
              f"the upstream text changed. Delete block-a.lock.json to "
              f"re-pin on purpose, or investigate: {', '.join(stale[:5])}")
        return 1

    _write_json(lock_path, {"source": manifest["source"], "documents": entries})
    print(f"block A built: {len(entries)} documents, lock written")
    return 0


# ---------------------------------------------------------------- block B

def build_block_b(root: Path | None = None) -> int:
    """
    Sample the private document tree named in the local config; snapshot and
    hash each document and emit the public metadata. Requires
    `corpus/block-b.config.json` (never committed).
    """
    cdir = _corpus_dir(root)
    cfg_path = cdir / "block-b.config.json"
    if not cfg_path.is_file():
        print(f"no {cfg_path.name}: block B builds only on the machine "
              "holding the private corpus")
        return 64
    cfg = _read_json(cfg_path)
    tree = Path(cfg["root"]).expanduser()
    if not tree.is_dir():
        print(f"configured root does not exist: {tree}")
        return 64

    seed = int(cfg["seed"])
    min_bytes = int(cfg.get("min_bytes", 500))
    exclude = set(cfg.get("exclude_basenames", ["README.md"]))
    outdir = cdir / "cache" / "block-b"
    outdir.mkdir(parents=True, exist_ok=True)

    public: list[dict[str, object]] = []
    local: list[dict[str, object]] = []
    for genre, spec in cfg["genres"].items():
        pool: set[Path] = set()
        for pattern in spec["globs"]:
            pool.update(p for p in tree.glob(pattern) if p.is_file())
        candidates = sorted(
            p for p in pool
            if p.name not in exclude and p.stat().st_size >= min_bytes
        )
        k = int(spec.get("k", 30))
        if len(candidates) > k:
            chosen = sorted(random.Random(seed).sample(candidates, k))
            whole_pool = False
        else:
            chosen, whole_pool = candidates, True
        for i, path in enumerate(chosen, 1):
            text = path.read_text(encoding="utf-8")
            doc_id = f"b-{genre}-{i:03d}"
            (outdir / f"{doc_id}.md").write_text(text, encoding="utf-8", newline="\n")
            public.append({
                "id": doc_id, "genre": genre, "sha256": _sha256(text),
                "bytes": len(text.encode("utf-8")),
                "words": len(_prose_words(text)),
            })
            local.append({"id": doc_id, "path": path.relative_to(tree).as_posix()})
        note = " (whole pool)" if whole_pool else ""
        print(f"  {genre}: {len(chosen)}/{len(candidates)} docs{note}")

    _write_json(cdir / "block-b.json", {
        "seed": seed, "min_bytes": min_bytes,
        "selection": "deterministic seeded sample per genre over the sorted candidate pool",
        "documents": public,
    })
    _write_json(cdir / "block-b.local.json", {"root": str(tree), "documents": local})
    print(f"block B built: {len(public)} documents across {len(cfg['genres'])} genres")
    return 0


# ---------------------------------------------------------------- load/verify

def _load_cached(cdir: Path, block: str, meta: Iterable[Mapping[str, object]],
                 suffix: str) -> tuple[CorpusDoc, ...]:
    docs: list[CorpusDoc] = []
    missing: list[str] = []
    stale: list[str] = []
    for e in meta:
        doc_id, genre, digest = str(e["id"]), str(e["genre"]), str(e["sha256"])
        path = cdir / "cache" / block / f"{doc_id}{suffix}"
        if not path.is_file():
            missing.append(doc_id)
            continue
        text = path.read_text(encoding="utf-8")
        if _sha256(text) != digest:
            stale.append(doc_id)
            continue
        docs.append(CorpusDoc(doc_id, genre, text, block))
    if missing or stale:
        raise CorpusUnavailable(
            f"{block}: {len(missing)} missing, {len(stale)} stale of "
            f"{len(docs) + len(missing) + len(stale)}; run "
            f"`python -m isda.corpus build-{block[-1]}` on this machine"
        )
    return tuple(docs)


def load_block(block: str, root: Path | None = None) -> tuple[CorpusDoc, ...]:
    """
    Load a built block, checking every document against its pinned hash.
    Raises CorpusUnavailable if the block is not built or any document is
    missing or stale.
    """
    cdir = _corpus_dir(root)
    if block == "block-a":
        lock = cdir / "block-a.lock.json"
        if not lock.is_file():
            raise CorpusUnavailable("block-a: no lock file; run `python -m isda.corpus build-a`")
        return _load_cached(cdir, "block-a", _read_json(lock)["documents"], ".txt")
    if block == "block-b":
        meta = cdir / "block-b.json"
        if not meta.is_file():
            raise CorpusUnavailable(
                "block-b: not built; it builds only on the machine holding "
                "the private corpus")
        return _load_cached(cdir, "block-b", _read_json(meta)["documents"], ".md")
    raise ValueError(f"unknown block: {block!r}")


def verify(root: Path | None = None) -> int:
    """Recompute every cached document's hash against its recorded pin."""
    failures = 0
    for block in ("block-a", "block-b"):
        try:
            docs = load_block(block, root)
            print(f"{block}: OK, {len(docs)} documents, all hashes match")
        except CorpusUnavailable as exc:
            print(f"{block}: {exc}")
            failures += 1
    from .specimens import verify_specimens  # local: specimens imports repo_root
    failures += verify_specimens(root)
    return 1 if failures else 0


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    verb = argv[0] if argv else "verify"
    if verb == "build-a":
        return build_block_a()
    if verb == "build-b":
        return build_block_b()
    if verb == "verify":
        return verify()
    print("usage: python -m isda.corpus [build-a | build-b | verify]")
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
