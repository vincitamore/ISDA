"""
A content-hash disk cache for expensive measure backends.

Keyed by sha256 of the exact input text plus a fingerprint of the measure's
parameters, so it can never serve a stale value: changed text is a different
key, changed parameters invalidate the whole file. It is derived state, safe
to delete; each file records the parameters and fingerprint it was written
under.

Lives under corpus/cache/ (gitignored, machine-local). A package installed
outside the repo gets an in-memory cache only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence, cast


class HashCache:
    def __init__(self, filename: str, params: Mapping[str, object],
                 written_by: str):
        self._filename = filename
        self._params = dict(params)
        self._written_by = written_by
        self._fingerprint = hashlib.sha256(
            json.dumps(self._params, sort_keys=True).encode()).hexdigest()[:16]
        self._values: dict[str, list[float]] = {}
        self._loaded = False

    def _path(self) -> Path | None:
        try:
            from ..corpus import repo_root
            return repo_root() / "corpus" / "cache" / self._filename
        except FileNotFoundError:
            return None  # installed outside the repo: in-memory only

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path()
        if path is None or not path.is_file():
            return
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return  # an unreadable cache is an empty cache, never a crash
        if data.get("fingerprint") != self._fingerprint:
            return  # parameters moved; every cached value is a different quantity
        for sha, row in cast(dict[str, list[float]], data.get("values", {})).items():
            self._values[sha] = [float(x) for x in row]

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        self._load()
        return self._values.get(self.key(text))

    def put(self, text: str, row: Sequence[float]) -> None:
        self._load()
        self._values[self.key(text)] = list(row)
        path = self._path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "written_by": self._written_by,
            "fingerprint": self._fingerprint,
            "params": self._params,
            "values": {k: v for k, v in sorted(self._values.items())},
        }, indent=0), encoding="utf-8", newline="\n")
