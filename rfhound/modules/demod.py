"""Software demodulation + decode primitives, and a registry mods can extend.

Unlike the external-tool decoder *recipes* in ``decode.py`` (which shell out to
rtl_433, dump1090, …), these run **in-process** on a payload you already have —
raw IQ samples, a list of bits, or bytes. That makes it easy to add your own
protocol decoder or a bespoke demodulator as a mod, without wrapping a CLI tool.

Two layers:

* **Bit/byte primitives** (`manchester_decode`, `differential_decode`,
  `bits_to_bytes`, `crc8`) — dependency-free, so a custom decoder built from them
  needs nothing extra.
* **IQ demodulators** (`ook_bits`, `fsk_bits`) — turn complex IQ into a bitstream;
  these need numpy (``pip install 'rfhound[iq]'``).

Register a decoder so it shows up in ``rfhound mods decoders`` and can be run
with ``rfhound mods run``::

    demod.register("my_proto", "My protocol", my_fn, kind="bits",
                   description="Manchester + CRC8")

A decoder is just ``fn(payload, **opts) -> Any``. ``kind`` documents what
``payload`` is: ``"bits"`` (list of 0/1), ``"bytes"``, or ``"iq"`` (complex
samples, with a ``sample_rate`` option).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


# --------------------------------------------------------------------------- #
# Bit / byte primitives — no numpy required.
# --------------------------------------------------------------------------- #
def manchester_decode(bits: Sequence[int]) -> list:
    """IEEE 802.3 Manchester: ``10`` → 1, ``01`` → 0.

    Consumes bit pairs; a pair that is neither (``00``/``11``) is a coding
    violation and decodes to ``None``. A trailing odd bit is dropped.
    """
    out: list = []
    for i in range(0, len(bits) - 1, 2):
        a, b = bits[i], bits[i + 1]
        if a and not b:
            out.append(1)
        elif not a and b:
            out.append(0)
        else:
            out.append(None)
    return out


def differential_decode(bits: Sequence[int], *, initial: int = 0) -> list:
    """NRZI / differential decode: output bit = current XOR previous."""
    out: list = []
    prev = 1 if initial else 0
    for b in bits:
        cur = 1 if b else 0
        out.append(cur ^ prev)
        prev = cur
    return out


def bits_to_bytes(bits: Sequence[int], *, msb_first: bool = True) -> bytes:
    """Pack a bit sequence into bytes (whole octets only; a partial tail is dropped)."""
    out = bytearray()
    n = (len(bits) // 8) * 8
    for i in range(0, n, 8):
        byte = 0
        for j in range(8):
            b = 1 if bits[i + j] else 0
            if msb_first:
                byte = (byte << 1) | b
            else:
                byte |= b << j
        out.append(byte)
    return bytes(out)


def crc8(data: bytes, *, poly: int = 0x07, init: int = 0x00) -> int:
    """Compute a CRC-8 (default poly 0x07, the SMBus/CCITT variant)."""
    crc = init & 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


# --------------------------------------------------------------------------- #
# IQ demodulators — need numpy (rfhound[iq]).
# --------------------------------------------------------------------------- #
def _np():
    try:
        import numpy as np
        return np
    except ImportError as exc:  # pragma: no cover - exercised only without numpy
        raise RuntimeError("IQ demodulation needs numpy: pip install 'rfhound[iq]'") from exc


def ook_bits(iq, sample_rate: int, baud: float, *, threshold: float | None = None) -> list:
    """OOK/ASK slicer: envelope → threshold → sample at symbol centres → 0/1 bits."""
    np = _np()
    amp = np.abs(np.asarray(iq, dtype=complex))
    if amp.size == 0:
        return []
    thr = threshold if threshold is not None else float((amp.max() + amp.min()) / 2.0)
    sps = max(1, int(round(sample_rate / float(baud))))
    centres = np.arange(sps // 2, amp.size, sps)
    return [1 if amp[i] > thr else 0 for i in centres.astype(int)]


def fsk_bits(iq, sample_rate: int, baud: float) -> list:
    """2-FSK slicer: sign of instantaneous frequency, sampled at the baud rate."""
    np = _np()
    x = np.asarray(iq, dtype=complex)
    if x.size < 2:
        return []
    inst = np.diff(np.unwrap(np.angle(x)))
    inst = inst - float(np.mean(inst))          # centre around 0
    sps = max(1, int(round(sample_rate / float(baud))))
    centres = np.arange(sps // 2, inst.size, sps)
    return [1 if inst[i] > 0 else 0 for i in centres.astype(int)]


# --------------------------------------------------------------------------- #
# Registry — built-ins plus anything a mod registers.
# --------------------------------------------------------------------------- #
@dataclass
class SoftDecoder:
    id: str
    name: str
    kind: str                 # "bits" | "bytes" | "iq"
    fn: Callable
    description: str = ""
    source: str = "built-in"  # "built-in" or a mod name


REGISTRY: dict = {}


def register(id: str, name: str, fn: Callable, *, kind: str = "bits",
             description: str = "", source: str = "built-in") -> SoftDecoder:
    """Register a software decoder. Later registrations override an existing id."""
    if kind not in ("bits", "bytes", "iq"):
        raise ValueError(f"kind must be bits|bytes|iq, got {kind!r}")
    dec = SoftDecoder(id, name, kind, fn, description, source)
    REGISTRY[id] = dec
    return dec


def get(id: str) -> SoftDecoder | None:
    return REGISTRY.get(id)


def names() -> list:
    return sorted(REGISTRY)


def run(id: str, payload: Any, **opts) -> Any:
    """Run a registered decoder by id. Raises KeyError if unknown."""
    dec = REGISTRY.get(id)
    if dec is None:
        raise KeyError(id)
    return dec.fn(payload, **opts)


def _register_builtins() -> None:
    register("manchester", "Manchester decode (10→1, 01→0)",
             lambda bits, **_: manchester_decode(bits), kind="bits",
             description="IEEE 802.3 bi-phase; pairs of bits → one bit")
    register("nrzi", "Differential / NRZI decode",
             lambda bits, **o: differential_decode(bits, **o), kind="bits",
             description="Output = current XOR previous bit")
    register("bytes", "Pack bits → bytes",
             lambda bits, **o: list(bits_to_bytes(bits, **o)), kind="bits",
             description="MSB-first by default (msb_first=False to flip)")
    register("ook", "OOK/ASK envelope slicer (IQ → bits)",
             lambda iq, sample_rate=0, baud=1000, **o: ook_bits(iq, sample_rate, baud, **o),
             kind="iq", description="Needs numpy; sample_rate + baud options")
    register("fsk", "2-FSK slicer (IQ → bits)",
             lambda iq, sample_rate=0, baud=1000, **_: fsk_bits(iq, sample_rate, baud),
             kind="iq", description="Needs numpy; sample_rate + baud options")


_register_builtins()
