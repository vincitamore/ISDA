"""
The compression floor: a one-sided mechanical bound on the ledger.

K is uncomputable, so no estimate of it can be validated. A real compressor
still bounds it from above: whatever zlib achieves, the true minimum is no
larger. That one-sided fact is the only mechanical anchor this framework has:
it catches cores claimed too large and cannot detect cores claimed too small.
"""

from __future__ import annotations

import zlib

ZDICT_CAP = 32768  # zlib compressobj zdict hard limit


def as_utf8_bytes(value: object, field_name: str) -> bytes:
    """Accept str or bytes for the optional ledger document/substrate fields."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    raise TypeError(f"{field_name} must be str or bytes")


def compress_upper_bound(data: bytes, substrate: bytes | None = None) -> tuple[int, str]:
    """
    A lossless upper bound on K(d | substrate), via zlib level 9.

    Container overhead is not subtracted: the bound is an achievable encoding
    length, and stripping the header would report a number no encoder can hit.

    Returns (length, mode) where mode is 'primed' or 'unconditioned'.
    """
    if substrate:
        # Raw deflate (wbits=-15), not the zlib wrapper. The wrapped form costs
        # 10 extra bytes per measurement (a 2-byte header, a 4-byte DICTID and
        # a 4-byte Adler-32 trailer), and the DICTID re-identifies a dictionary
        # the caller has already declared as a parameter. Raw deflate plus the
        # declared substrate reconstructs the document exactly, so it is a
        # decodable encoding and therefore a valid upper bound, 10 B tighter
        # than the wrapped form. The saving matters where the margin between
        # the core and the bound is small.
        co = zlib.compressobj(9, zlib.DEFLATED, -15, 8,
                              zlib.Z_DEFAULT_STRATEGY, substrate[:ZDICT_CAP])
        return len(co.compress(data) + co.flush()), "primed"
    return len(zlib.compress(data, 9)), "unconditioned"
