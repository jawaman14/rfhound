# Legal & ethical use — read before transmitting

RFHound is built for **authorized security research, RF education, and
pentesting engagements you have written permission to perform.** Radio spectrum
is a shared, regulated public resource. Misusing it is a criminal offence in
most countries.

## The short version

- **Receiving** most signals is broadly permitted in many places, but *acting on
  the contents* of some transmissions (e.g. decoding others' private messages,
  cellular, or pager traffic) may be restricted where you live. Know your local
  law (e.g. FCC Part 15 / the US Wiretap Act / the ECPA in the US, the Wireless
  Telegraphy Act in the UK, and equivalents elsewhere).
- **Transmitting** on frequencies you are not licensed for is illegal almost
  everywhere. RFHound keeps transmit **off by default** and makes you declare an
  explicit frequency allow-list before it will key the radio.
- Only test devices and systems **you own or are contractually authorized to
  assess.** "It was interesting" is not authorization.
- Prefer a **shielded enclosure / Faraday bag / RF-tight lab** for any transmit
  testing so you don't radiate into the real world.

## What RFHound deliberately does NOT do

These are excluded by design because they are primarily harmful, are illegal in
normal use, or map to denial-of-service:

- ❌ **Jamming / broadband noise / continuous-wave denial-of-service.**
- ❌ **Protocol deauthentication or disassociation floods.**
- ❌ **Rolling-code / key-fob brute-force or "code-grabbing" replay tooling
  designed to defeat security.**
- ❌ **Automated over-the-air fuzzing of third-party devices.**

RFHound's only transmit path is **replaying an exact IQ file you captured, at the
frequency it was captured on, for authorized testing of your own equipment** —
and even that is gated behind consent + an allow-list + a per-command
`--authorized` flag. If you have a legitimate need to craft new frames for a
sanctioned test, use a tool built for that (e.g. Universal Radio Hacker)
knowingly and deliberately.

These exclusions are **not** conditional on your environment or credentials. A
shielded RF enclosure and operator training make TX *resilience testing* safe and
legal — which is why RFHound supports gated replay of your own captures — but
they do not turn a general-purpose jammer / RollJam / brute-forcer into something
RFHound will ship. A defence programme reaches its goal through **detection and
hardening** (`rfhound defense`), not by fielding those attack primitives. See
[`DEFENSE.md`](DEFENSE.md).

## Sensitive bands — extra care

- **GPS / GNSS (≈1575 MHz):** never transmit. Interfering with navigation is
  dangerous and heavily prosecuted.
- **Aviation & maritime (ADS-B, ACARS, AIS, VHF air/marine):** receive-only.
  Transmitting spoofed aircraft/ship data endangers lives and is a serious crime.
- **Cellular (GSM/2G+):** analysis is legally sensitive and transmitting is
  illegal without being a licensed operator. RFHound provides no cellular TX.
- **Emergency / public-safety services:** never interfere.

## Your responsibility

By using RFHound you accept that **you** are solely responsible for operating
within the law and your rules of engagement. The authors provide this software
for lawful research and education and disclaim liability for misuse.

If you're unsure whether something is legal where you are: **don't transmit, and
ask a licensed operator or your legal counsel first.**
