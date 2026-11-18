"""
The isda CLI: four verbs over an ok-first JSON envelope.

    python -m isda measure  FILE [--telos T] [--substrate S] [--detail PATH] [--json]
    python -m isda analyze  FILE --ledger LEDGER [--telos T] [--substrate S] [--json]
    python -m isda score    LEDGER [--document FILE] [--substrate-file FILE] [--json]
    python -m isda measures [--write] [--check] [--json]

Contract:
- `--json` emits one envelope object to stdout. Success is `{"ok": true,
  "verb": ..., ...payload}` with `ok` the first key; failure is `{"ok": false,
  "error": {"code", "message"}, "verb": ...}` plus a one-line stderr summary.
  Without `--json`, a human rendering of the same payload goes to stdout and
  errors go to stderr only.
- Exit codes: 0 success; 1 the run completed and found something actionable
  (only `measures --check`, when the manifest has drifted); 64 usage error or
  malformed input; 70 a bug in this tool.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Mapping, NoReturn

from . import render, verbs
from .verbs import VerbError

EXIT_OK = 0
EXIT_FINDING = 1     # the run completed and found something actionable
EXIT_USAGE = 64      # malformed input: bad flags, bad ledger, unreadable file
EXIT_INTERNAL = 70   # a bug in this tool


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on bad usage; this CLI exits 64 (EXIT_USAGE) instead."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _build_parser() -> _Parser:
    p = _Parser(
        prog="isda",
        description="Telos-relative semantic density measurement. "
                    "Measurement, not judgment: stratum classification and "
                    "intensity tags remain the analyst's work.",
    )
    sub = p.add_subparsers(dest="verb", required=True)

    m = sub.add_parser("measure", parents=[], help="mechanical measurement of one document")
    m.add_argument("file", help="path to a UTF-8 text file, or - for stdin")
    m.add_argument("--telos", help="what the text is trying to achieve (recorded)")
    m.add_argument("--substrate", help="the named retrieval substrate (recorded)")
    m.add_argument("--detail", metavar="PATH",
                   help="also write per-block JSONL rows (the O(n) side) to PATH")
    m.add_argument("--json", action="store_true", help="emit the JSON envelope")

    a = sub.add_parser("analyze", help="full analysis: ledger-first, metrics beneath")
    a.add_argument("file", help="path to the analyzed document")
    a.add_argument("--ledger", required=True, metavar="LEDGER",
                   help="the analyst's seven-row ledger (JSON)")
    a.add_argument("--telos", help="what the text is trying to achieve")
    a.add_argument("--substrate", help="the named retrieval substrate")
    a.add_argument("--json", action="store_true", help="emit the JSON envelope")

    s = sub.add_parser("score", help="SCR/ND/RI arithmetic over a completed ledger")
    s.add_argument("ledger", help="path to the ledger JSON, or - for stdin")
    s.add_argument("--document", metavar="FILE",
                   help="the document the ledger describes; enables the compression floor")
    s.add_argument("--substrate-file", metavar="FILE",
                   help="priming dictionary for the floor's conditional bound")
    s.add_argument("--json", action="store_true", help="emit the JSON envelope")

    r = sub.add_parser("measures", help="the measure registry: the partition record")
    r.add_argument("--write", action="store_true",
                   help="render the manifest to data/measures.json (repo only)")
    r.add_argument("--check", action="store_true",
                   help="exit 1 if data/measures.json drifts from the registry")
    r.add_argument("--json", action="store_true", help="emit the JSON envelope")

    return p


_RENDERERS: dict[str, Callable[[Mapping[str, Any]], str]] = {
    "measure": render.render_measure,
    "analyze": render.render_analyze,
    "score": render.render_score,
    "measures": render.render_measures,
}


def _dispatch(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.verb == "measure":
        return verbs.measure(args.file, args.telos, args.substrate, args.detail)
    if args.verb == "analyze":
        return verbs.analyze(args.file, args.ledger, args.telos, args.substrate)
    if args.verb == "score":
        return verbs.score(args.ledger, args.document, args.substrate_file)
    if args.verb == "measures":
        return verbs.measures(args.write, args.check)
    raise AssertionError(f"unreachable verb {args.verb!r}")


def _emit_error(verb: str, code: str, message: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"ok": False,
                          "error": {"code": code, "message": message},
                          "verb": verb}))
    print(f"error [{code}]: {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    # Deterministic bytes on every platform: Windows consoles otherwise encode
    # stdout in the console's default (non-UTF-8) code page, mangling `·` and
    # failing on anything outside it. --json output must be byte-identical
    # across platforms for scripts to depend on it.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    as_json = bool(getattr(args, "json", False))
    try:
        payload, exit_code = _dispatch(args)
    except VerbError as exc:
        _emit_error(args.verb, exc.code, str(exc), as_json)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001
        # Every other failure exits 70: a CLI must not die with a traceback.
        _emit_error(args.verb, "internal", f"{type(exc).__name__}: {exc}", as_json)
        return EXIT_INTERNAL

    if as_json:
        print(json.dumps({"ok": True, "verb": args.verb, **payload},
                         ensure_ascii=False))
    else:
        print(_RENDERERS[args.verb](payload))
    return exit_code
