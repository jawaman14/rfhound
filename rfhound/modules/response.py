"""Counter-threat response playbooks (defensive actions).

When a threat is detected, an operator needs to know *what to do about it*. This
module maps each threat RFHound can detect to a structured **defensive** response
playbook: immediate actions, evidence to preserve, mitigations to harden the
target, and when to escalate.

These are blue-team / incident-response actions — alert, record, harden,
escalate. RFHound intentionally provides **no active RF countermeasures**
(jamming back, spoofing back, drone takeover); those are offensive and, for a
jammer/drone, usually illegal for non-government operators. Where an active
kinetic/RF response is appropriate, that is a decision for authorised personnel
using purpose-built, licensed equipment — not something this tool performs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Playbook:
    threat: str
    summary: str
    immediate: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    escalation: list[str] = field(default_factory=list)


PLAYBOOKS: dict[str, Playbook] = {
    "jamming": Playbook(
        "jamming",
        "Deliberate interference / RF denial-of-service on a band you depend on.",
        immediate=[
            "Confirm it's jamming, not a fault: check the noise-floor rise and "
            "whether multiple independent receivers see it (rfhound defense monitor).",
            "Switch affected systems to a fail-safe / degraded-but-safe mode.",
            "Note start time and affected frequency span.",
        ],
        evidence=[
            "Record an IQ capture of the interference (rfhound capture) with timestamp.",
            "Save the interference monitor log and baseline for comparison.",
            "If safe/legal, estimate bearing with a directional antenna for later DF.",
        ],
        mitigations=[
            "Frequency/route diversity: fail over to a different band or wired link.",
            "Add RF shielding / filtering on critical receivers.",
            "Deploy persistent jamming-detection alerting so future events are caught fast.",
        ],
        escalation=[
            "Report to the site security lead and the national spectrum regulator "
            "(deliberate jamming is a criminal offence) — provide your evidence pack.",
        ],
    ),
    "gps_spoof": Playbook(
        "gps_spoof",
        "GNSS spoofing: falsified GPS position/time being broadcast.",
        immediate=[
            "Cross-check GNSS against an independent time/position source (INS, "
            "network time, surveyed location).",
            "Flag/hold any automation that trusts GPS (timing, navigation, geofencing).",
        ],
        evidence=[
            "Log observed vs. expected position/time and C/N0 anomalies.",
            "Capture IQ around GPS L1 (1575.42 MHz) with timestamp.",
        ],
        mitigations=[
            "Use multi-constellation + authenticated GNSS (e.g. Galileo OSNMA) where available.",
            "Add an inertial / holdover clock so a spoof can't jump your time or position.",
            "Enable receiver anti-spoofing (RAIM / consistency checks).",
        ],
        escalation=[
            "Notify operations and, for safety-of-life systems, the relevant authority.",
        ],
    ),
    "adsb_spoof": Playbook(
        "adsb_spoof",
        "Ghost aircraft / falsified ADS-B being injected at 1090 MHz.",
        immediate=[
            "Treat suspect tracks as unverified; correlate with primary/secondary radar "
            "or MLAT before acting.",
            "Flag tracks failing kinematic/plausibility checks (rfhound defense spoof-check adsb).",
        ],
        evidence=[
            "Preserve the decoded message log with the flagged ICAOs and timestamps.",
            "Capture IQ at 1090 MHz during the event.",
        ],
        mitigations=[
            "Require multi-sensor confirmation (radar + MLAT) before a track drives any action.",
            "Deploy continuous ADS-B spoof-detection with alerting.",
        ],
        escalation=[
            "Report to the ANSP / aviation authority — spoofing aviation data is a serious crime.",
        ],
    ),
    "ais_spoof": Playbook(
        "ais_spoof",
        "Falsified vessel AIS (impossible motion, invalid MMSI, ghost ships).",
        immediate=[
            "Corroborate suspect vessels with radar / optical / independent AIS feeds.",
            "Flag tracks failing checks (rfhound defense spoof-check ais).",
        ],
        evidence=["Preserve flagged MMSI/track logs and an IQ capture with timestamps."],
        mitigations=[
            "Fuse AIS with radar/EO before trusting it operationally.",
            "Continuous AIS spoof-detection with alerting.",
        ],
        escalation=["Report to the maritime authority / coastguard."],
    ),
    "drone": Playbook(
        "drone",
        "Unauthorised UAS detected via its control/video RF.",
        immediate=[
            "Confirm and locate: which band, signal strength trend, likely bearing "
            "(rfhound defense drone-scan + a directional antenna).",
            "Alert site security and follow your facility's UAS-incursion procedure.",
        ],
        evidence=[
            "Log detection band, time, and RSSI history; capture IQ of the link.",
            "Note any correlated visual/acoustic sighting.",
        ],
        mitigations=[
            "Deploy persistent counter-UAS detection with alerting and zone mapping.",
            "Harden/relocate sensitive assets out of likely overflight lines.",
        ],
        escalation=[
            "Escalate to security/law-enforcement. Do NOT attempt RF takeover or jamming "
            "of the drone — that is offensive EW, usually illegal for non-government "
            "operators, and is out of scope for this tool. Mitigation is detection + "
            "authorised physical/legal response.",
        ],
    ),
    "rogue_emitter": Playbook(
        "rogue_emitter",
        "A new/unexpected transmitter appeared vs. your known-good baseline (possible bug).",
        immediate=[
            "Compare against the baseline to confirm it's genuinely new "
            "(rfhound defense baseline diff).",
            "Localise it with a directional antenna / signal-strength walk-down.",
        ],
        evidence=[
            "Record IQ of the emitter and note frequency, bandwidth, on/off pattern.",
            "Photograph the location once found; preserve chain of custody if it's a device.",
        ],
        mitigations=[
            "Physically remove/quarantine an identified rogue device.",
            "Re-baseline the area and schedule periodic TSCM sweeps.",
        ],
        escalation=["Involve physical security / counter-surveillance team for any found device."],
    ),
    "replay": Playbook(
        "replay",
        "A captured RF command is being replayed against a device (access control, sensor).",
        immediate=[
            "Flag duplicate/implausibly-timed payloads (rfhound defense replay-check).",
            "If it controls access, treat the credential as compromised and disable it.",
        ],
        evidence=["Preserve the observation log with the repeated payloads and timings."],
        mitigations=[
            "Move the device to authenticated rolling-code / challenge-response; reject reused codes.",
            "Deploy runtime replay + RollJam detection.",
        ],
        escalation=["Notify the system owner; rotate credentials/keys as needed."],
    ),
}


def list_threats() -> list[str]:
    return list(PLAYBOOKS.keys())


def get_playbook(threat: str) -> Playbook | None:
    return PLAYBOOKS.get(threat)
