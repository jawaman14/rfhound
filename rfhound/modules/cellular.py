"""Rogue base station / IMSI-catcher DETECTION (defensive).

This is the defensive counterpart to an IMSI catcher — it does not impersonate a
network or intercept anyone. It ingests observed cellular broadcast parameters
(the kind SnoopSnitch / EFF's Crocodile Hunter analyse) and flags the classic
indicators of a fake base station so a defender knows a Stingray-class device may
be operating nearby.

RFHound does not itself demodulate cellular control channels (that needs
gr-gsm / a supported baseband); it consumes observations you provide as JSON and
does the analysis + alerting. It performs no active cellular transmission of any
kind.

Indicators (per public rogue-BTS research):
  * A5/0 or downgraded ciphering (no/weak encryption)
  * Missing / empty neighbor-cell list
  * Unusual or changing Location Area Code (LAC) forcing re-registration
  * A new cell appearing with an implausibly strong signal
  * MCC/MNC not matching an expected operator
  * Same Cell ID seen on a different ARFCN/frequency
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CellObservation:
    rat: str = "GSM"          # GSM | UMTS | LTE
    mcc: str = ""
    mnc: str = ""
    lac: int | None = None    # or TAC for LTE
    cid: int | None = None
    arfcn: int | None = None  # or EARFCN
    rxlev: int | None = None  # received level (dBm-ish or 0..63)
    cipher: str = ""          # e.g. "A5/1", "A5/3", "A5/0"
    neighbors: list = field(default_factory=list)
    t: float = 0.0


@dataclass
class CellAlert:
    indicator: str
    detail: str
    severity: str = "high"
    cid: int | None = None


def detect_rogue_bts(
    observations: list[CellObservation],
    *,
    expected_operators: list[tuple[str, str]] | None = None,
    known_lacs: set[int] | None = None,
    strong_rxlev: int = -50,
) -> list[CellAlert]:
    """Analyse cellular observations for rogue-BTS / IMSI-catcher indicators.

    *expected_operators* is a list of (mcc, mnc) you expect to see.
    *known_lacs* is a baseline set of legitimate Location Area Codes.
    """
    alerts: list[CellAlert] = []
    seen_lacs = set(known_lacs or set())
    cid_to_arfcn: dict[int, set] = {}

    for o in observations:
        # 1) Encryption downgrade / none.
        if o.cipher and o.cipher.upper().replace(" ", "") in ("A5/0", "A50", "NONE", "EEA0"):
            alerts.append(CellAlert(
                "encryption-downgrade",
                f"cell CID={o.cid} advertises no/weak ciphering ({o.cipher}). "
                f"IMSI catchers commonly disable encryption.", "high", o.cid))

        # 2) Empty / missing neighbor list.
        if o.rat in ("GSM", "UMTS") and not o.neighbors:
            alerts.append(CellAlert(
                "empty-neighbor-list",
                f"cell CID={o.cid} broadcasts no neighbor cells — common for a "
                f"fake base station isolating a target.", "medium", o.cid))

        # 3) Unexpected operator.
        if expected_operators and o.mcc and o.mnc:
            if (o.mcc, o.mnc) not in expected_operators:
                alerts.append(CellAlert(
                    "unexpected-operator",
                    f"cell CID={o.cid} MCC/MNC {o.mcc}/{o.mnc} is not an expected "
                    f"operator.", "medium", o.cid))

        # 4) New/unusual LAC.
        if o.lac is not None:
            if seen_lacs and o.lac not in seen_lacs:
                sev = "high" if (o.rxlev is not None and o.rxlev >= strong_rxlev) else "medium"
                alerts.append(CellAlert(
                    "lac-anomaly",
                    f"cell CID={o.cid} uses LAC/TAC {o.lac} not in the known set — "
                    f"a LAC change forces phones to re-register (IMSI disclosure).",
                    sev, o.cid))
            seen_lacs.add(o.lac)

        # 5) Implausibly strong new cell.
        if o.rxlev is not None and o.rxlev >= strong_rxlev:
            alerts.append(CellAlert(
                "excessive-signal",
                f"cell CID={o.cid} rxlev {o.rxlev} is unusually strong — a nearby "
                f"catcher often overpowers legitimate cells.", "medium", o.cid))

        # 6) Same CID on a different ARFCN.
        if o.cid is not None and o.arfcn is not None:
            arfcns = cid_to_arfcn.setdefault(o.cid, set())
            if arfcns and o.arfcn not in arfcns:
                alerts.append(CellAlert(
                    "cid-arfcn-mismatch",
                    f"CID={o.cid} seen on multiple ARFCNs {sorted(arfcns | {o.arfcn})} "
                    f"— identity reuse across frequencies.", "high", o.cid))
            arfcns.add(o.arfcn)

    return alerts


def score(alerts: list[CellAlert]) -> int:
    """Coarse 0..100 rogue-likelihood from the alert mix."""
    weight = {"high": 34, "medium": 15, "low": 6}
    return min(100, sum(weight.get(a.severity, 6) for a in alerts))


def simulate_observations() -> list[CellObservation]:
    """A synthetic scan containing one obvious IMSI catcher among real cells."""
    return [
        CellObservation("GSM", "310", "260", lac=4120, cid=10111, arfcn=128,
                        rxlev=-71, cipher="A5/1", neighbors=[131, 135, 140], t=0),
        CellObservation("GSM", "310", "260", lac=4120, cid=10112, arfcn=131,
                        rxlev=-79, cipher="A5/1", neighbors=[128, 140], t=1),
        # The catcher: new LAC, no encryption, empty neighbors, very strong.
        CellObservation("GSM", "310", "260", lac=9999, cid=55501, arfcn=133,
                        rxlev=-41, cipher="A5/0", neighbors=[], t=2),
    ]
