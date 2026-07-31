"""Defensive analysis: detect attacks and assess device resilience.

This module is the "build protections" half of RFHound. It is entirely
receive-and-analyse plus (for the resilience harness) the existing *gated*
replay-of-your-own-capture. It contains **no** jamming/DoS transmitter, no
RollJam capture-and-replay attack, and no brute-force code generator — those are
out of scope by design (see ``docs/LEGAL.md``). Everything here helps a defender
*detect* those attacks and *harden* against them.

Capabilities:
  * Interference / jamming detection (noise-floor + signal-loss monitoring)
  * RollJam-pattern detection (jamming coincident with a device transmission)
  * Replay-attack detection (duplicate payloads / impossible timing)
  * Rolling-code posture assessment (fixed vs rolling, replay-resilience score)
  * Lab resilience harness (replay your own capture at your own device, report)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from .. import console
from ..config import Config
from . import sweep as sweep_mod


# --------------------------------------------------------------------------- #
# 1. Interference / jamming detection
# --------------------------------------------------------------------------- #
@dataclass
class InterferenceSample:
    t: float
    noise_floor_db: float
    peak_db: float
    active_peaks: int


@dataclass
class InterferenceReport:
    band_low_hz: int
    band_high_hz: int
    baseline_floor_db: float
    threshold_db: float
    samples: list[InterferenceSample] = field(default_factory=list)
    alarms: list[str] = field(default_factory=list)
    simulated: bool = False

    @property
    def jammed(self) -> bool:
        return bool(self.alarms)


def monitor_interference(
    cfg: Config,
    start_mhz: float,
    stop_mhz: float,
    *,
    iterations: int = 12,
    interval_s: float = 1.0,
    threshold_db: float = 10.0,
    baseline_samples: int = 3,
    simulate: bool = False,
    on_sample=None,
) -> InterferenceReport:
    """Watch a band and alarm when the noise floor rises (classic jamming) or
    previously-present signals vanish (desense).

    A baseline noise floor is learned from the first *baseline_samples* sweeps;
    subsequent sweeps that exceed baseline + *threshold_db* raise an alarm. This
    is exactly the signal a defender needs to detect an RF DoS / jamming attack.
    """
    report = InterferenceReport(
        band_low_hz=int(start_mhz * 1e6),
        band_high_hz=int(stop_mhz * 1e6),
        baseline_floor_db=0.0,
        threshold_db=threshold_db,
        simulated=simulate,
    )
    rng = random.Random(7)
    baseline: list[float] = []
    baseline_peaks: int | None = None

    for i in range(iterations):
        if simulate:
            # Quiet baseline, then a jammer switches on ~60% through the run.
            jamming = i >= int(iterations * 0.6)
            floor = -95 + rng.uniform(-2, 2) + (35 if jamming else 0)
            peak = floor + (5 if jamming else 25)  # jammer floods, drowns signals
            active = 0 if jamming else 3
            sample = InterferenceSample(time.time(), round(floor, 1), round(peak, 1), active)
        else:
            result = sweep_mod.sweep(cfg, start_mhz, stop_mhz, simulate=False)
            sample = InterferenceSample(
                time.time(),
                result.noise_floor_db,
                max((b.power_db for b in result.bins), default=result.noise_floor_db),
                len(result.peaks),
            )

        report.samples.append(sample)
        if on_sample:
            on_sample(sample)

        if len(baseline) < baseline_samples:
            baseline.append(sample.noise_floor_db)
            if len(baseline) == baseline_samples:
                report.baseline_floor_db = round(sum(baseline) / len(baseline), 1)
                baseline_peaks = max(1, sample.active_peaks)
        else:
            rise = sample.noise_floor_db - report.baseline_floor_db
            if rise >= threshold_db:
                report.alarms.append(
                    f"t+{i}: noise floor +{rise:.1f} dB over baseline "
                    f"({sample.noise_floor_db} dB) — possible jamming/interference."
                )
            elif baseline_peaks and sample.active_peaks == 0 and baseline_peaks >= 2:
                report.alarms.append(
                    f"t+{i}: expected signals disappeared (desense) — possible jamming."
                )

        if not simulate and interval_s > 0 and i < iterations - 1:
            time.sleep(interval_s)

    return report


# --------------------------------------------------------------------------- #
# 2. Replay-attack detection
# --------------------------------------------------------------------------- #
@dataclass
class Observation:
    t: float
    payload: str
    freq_hz: int | None = None
    rssi_db: float | None = None


@dataclass
class ReplayFinding:
    payload: str
    count: int
    first_t: float
    last_t: float
    min_gap_s: float
    reason: str


def detect_replays(
    observations: list[Observation],
    *,
    window_s: float = 8.0,
    rolling_expected: bool = True,
) -> list[ReplayFinding]:
    """Flag likely replay attacks in a stream of decoded transmissions.

    For devices expected to use rolling codes, *any* exact payload repeat is
    suspicious. For fixed-code devices, we flag repeats that arrive implausibly
    close together (a human can't press a button many times in one window).
    """
    by_payload: dict[str, list[Observation]] = {}
    for obs in sorted(observations, key=lambda o: o.t):
        by_payload.setdefault(obs.payload, []).append(obs)

    findings: list[ReplayFinding] = []
    for payload, obs_list in by_payload.items():
        if len(obs_list) < 2:
            continue
        gaps = [obs_list[i + 1].t - obs_list[i].t for i in range(len(obs_list) - 1)]
        min_gap = min(gaps)
        close_repeats = sum(1 for g in gaps if g <= window_s)
        if rolling_expected:
            reason = (
                "identical payload seen more than once on a device expected to "
                "roll its code every press — classic replay signature."
            )
            findings.append(
                ReplayFinding(payload, len(obs_list), obs_list[0].t,
                              obs_list[-1].t, round(min_gap, 3), reason)
            )
        elif close_repeats >= 1:
            reason = (
                f"identical payload repeated within {window_s:.0f}s "
                f"({close_repeats}x) — faster than plausible human input."
            )
            findings.append(
                ReplayFinding(payload, len(obs_list), obs_list[0].t,
                              obs_list[-1].t, round(min_gap, 3), reason)
            )
    findings.sort(key=lambda f: f.count, reverse=True)
    return findings


# --------------------------------------------------------------------------- #
# 3. Rolling-code posture assessment
# --------------------------------------------------------------------------- #
@dataclass
class RollingCodeAssessment:
    samples: int
    unique: int
    unique_ratio: float
    classification: str  # "fixed", "rolling", "unknown"
    likely_counter: bool
    mean_bit_change: float
    resilience_score: int  # 0 (trivially replayable) .. 100 (strong)
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def _hamming(a: str, b: str) -> int:
    n = min(len(a), len(b))
    return sum(1 for i in range(n) if a[i] != b[i]) + abs(len(a) - len(b))


def assess_rolling_code(payloads: list[str]) -> RollingCodeAssessment:
    """Passively classify a device's code scheme from captured payloads.

    Input is a list of payloads (hex or bit strings) captured from repeated
    presses of the *same* button on a device you are authorized to assess. This
    reports posture and weaknesses — it does not produce any attack.
    """
    payloads = [p.strip() for p in payloads if p.strip()]
    n = len(payloads)
    if n == 0:
        return RollingCodeAssessment(0, 0, 0.0, "unknown", False, 0.0, 0,
                                     ["No payloads provided."], [])
    unique = len(set(payloads))
    ratio = unique / n
    changes = [_hamming(payloads[i], payloads[i + 1]) for i in range(n - 1)]
    mean_change = round(sum(changes) / len(changes), 2) if changes else 0.0

    findings: list[str] = []
    recs: list[str] = []
    likely_counter = False

    if unique == 1:
        classification = "fixed"
        score = 5
        findings.append("All captured payloads are identical — this is a FIXED code.")
        findings.append("A fixed code is trivially replayable: a single capture reopens it.")
        recs += [
            "Replace with a rolling-code / hopping-code scheme (e.g. KeeLoq-class "
            "or better) or a challenge-response protocol.",
            "Add a monotonically increasing, authenticated counter the receiver "
            "validates and never re-accepts.",
        ]
    elif ratio > 0.9 and mean_change >= max(2.0, 0.1 * len(payloads[0])):
        classification = "rolling"
        # Heuristic: small, regular bit changes suggest a plain counter (weaker
        # than a well-diffused cryptographic hop).
        small_regular = changes and (sum(1 for c in changes if c <= 3) / len(changes) > 0.6)
        likely_counter = bool(small_regular)
        score = 70 if likely_counter else 90
        findings.append("Payloads change every press — consistent with a ROLLING code.")
        if likely_counter:
            findings.append(
                "Bit changes are small/regular — may be a lightly-obscured counter "
                "rather than a well-diffused cryptographic hop."
            )
            recs.append(
                "Verify the code is cryptographically generated (good avalanche), "
                "not a thinly-masked incrementing counter."
            )
        recs.append(
            "Confirm the receiver enforces a forward-only window and rejects "
            "reused/old codes (defends against RollJam-style capture-and-hold)."
        )
    else:
        classification = "unknown"
        score = 40
        findings.append(
            f"Mixed pattern: {unique}/{n} unique payloads, mean bit-change "
            f"{mean_change}. Capture more presses for a confident classification."
        )
        recs.append("Collect 10+ clean captures of the same button and re-assess.")

    # Universal defensive recommendation.
    recs.append(
        "Regardless of scheme, monitor for RollJam patterns (jamming coincident "
        "with a fob press) and for exact-payload replays — see 'defense monitor' "
        "and 'defense replay-check'."
    )

    return RollingCodeAssessment(
        samples=n,
        unique=unique,
        unique_ratio=round(ratio, 3),
        classification=classification,
        likely_counter=likely_counter,
        mean_bit_change=mean_change,
        resilience_score=score,
        findings=findings,
        recommendations=recs,
    )


def simulate_payloads(kind: str = "fixed", count: int = 8) -> list[str]:
    """Generate synthetic captures for demos/tests: 'fixed', 'counter', 'rolling'."""
    rng = random.Random(2024)
    if kind == "fixed":
        code = "".join(rng.choice("01") for _ in range(24))
        return [code] * count
    if kind == "counter":
        base = rng.randrange(0, 1 << 20)
        return [format((base + i) & 0xFFFFFF, "024b") for i in range(count)]
    # rolling / cryptographic-ish: high entropy every press
    return ["".join(rng.choice("01") for _ in range(64)) for _ in range(count)]


# --------------------------------------------------------------------------- #
# 4. Lab resilience harness
# --------------------------------------------------------------------------- #
@dataclass
class ResilienceResult:
    device: str
    replay_vulnerable: bool | None
    rolling: RollingCodeAssessment | None
    steps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    simulated: bool = False

    @property
    def score(self) -> int:
        base = self.rolling.resilience_score if self.rolling else 50
        if self.replay_vulnerable:
            base = min(base, 15)
        return base


def run_resilience_test(
    cfg: Config,
    *,
    device: str,
    payloads: list[str] | None = None,
    replayed: bool = False,
    device_actuated: bool | None = None,
    simulate: bool = False,
) -> ResilienceResult:
    """Structure a resilience test of *your own* device and produce a hardening
    report.

    This does not itself transmit — replay uses the separate, gated
    ``rfhound replay ... --authorized`` path (inside your RF enclosure). The
    operator confirms whether the device actuated on replay; the harness turns
    that plus a rolling-code assessment into findings and recommendations.
    """
    steps: list[str] = []
    if simulate:
        payloads = payloads or simulate_payloads("fixed")
        device_actuated = True if device_actuated is None else device_actuated
        replayed = True
        steps.append("[sim] captured 8 button presses from the device under test")
        steps.append("[sim] replayed capture #1 inside RF enclosure")
        steps.append("[sim] operator reported the device ACTUATED on replay")

    rolling = assess_rolling_code(payloads) if payloads else None
    replay_vulnerable: bool | None
    if replayed and device_actuated is not None:
        replay_vulnerable = bool(device_actuated)
        steps.append(
            "replay test: device "
            + ("ACTUATED (replay-vulnerable)" if replay_vulnerable else "rejected the replay")
        )
    else:
        replay_vulnerable = None
        steps.append("replay test: not performed / outcome not reported")

    recs: list[str] = []
    if replay_vulnerable:
        recs.append(
            "Device accepted a replayed capture — it does not enforce freshness. "
            "Add an authenticated rolling counter / nonce the receiver validates."
        )
    if rolling:
        recs.extend(rolling.recommendations)
    recs.append(
        "Deploy runtime detection: alarm on exact-payload replays and on "
        "jam-then-press (RollJam) patterns."
    )
    # De-duplicate while preserving order.
    seen: set[str] = set()
    recs = [r for r in recs if not (r in seen or seen.add(r))]

    return ResilienceResult(
        device=device,
        replay_vulnerable=replay_vulnerable,
        rolling=rolling,
        steps=steps,
        recommendations=recs,
        simulated=simulate,
    )


# --------------------------------------------------------------------------- #
# Pretty printers
# --------------------------------------------------------------------------- #
def print_interference(report: InterferenceReport) -> None:
    tag = " [SIMULATED]" if report.simulated else ""
    console.rule(f"Interference / jamming monitor{tag}")
    console.print_(
        f"Band {report.band_low_hz/1e6:.1f}-{report.band_high_hz/1e6:.1f} MHz · "
        f"baseline floor {report.baseline_floor_db} dB · "
        f"alarm threshold +{report.threshold_db} dB"
    )
    if report.jammed:
        console.error(f"JAMMING/INTERFERENCE DETECTED ({len(report.alarms)} alarm(s)):")
        for a in report.alarms:
            console.print_(f"  • {a}")
    else:
        console.success("No jamming detected — band nominal.")


def print_rolling(a: RollingCodeAssessment) -> None:
    console.rule("Rolling-code posture assessment")
    console.print_(
        f"Samples {a.samples} · unique {a.unique} ({a.unique_ratio:.0%}) · "
        f"mean bit-change {a.mean_bit_change}"
    )
    console.print_(f"Classification: {a.classification.upper()}  ·  "
                   f"resilience score {a.resilience_score}/100")
    for f in a.findings:
        console.print_(f"  • {f}")
    if a.recommendations:
        console.rule("Recommendations")
        for r in a.recommendations:
            console.print_(f"  → {r}")


def print_resilience(r: ResilienceResult) -> None:
    tag = " [SIMULATED]" if r.simulated else ""
    console.rule(f"Resilience report: {r.device}{tag}")
    for s in r.steps:
        console.print_(f"  • {s}")
    verdict = (
        "REPLAY-VULNERABLE" if r.replay_vulnerable
        else "resisted replay" if r.replay_vulnerable is False
        else "replay outcome unknown"
    )
    console.print_(f"\nVerdict: {verdict}  ·  overall resilience {r.score}/100")
    if r.recommendations:
        console.rule("Hardening recommendations")
        for rec in r.recommendations:
            console.print_(f"  → {rec}")
