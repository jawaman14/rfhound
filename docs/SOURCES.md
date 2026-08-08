# Multiple RF sources & RSSI locating

RFHound isn't limited to the HackRF. It can also use the **host PC's built-in
Wi-Fi and Bluetooth adapters** as passive RF sources, so you get RSSI (signal
strength) from three kinds of emitters at once — sweep peaks, Wi-Fi APs, and BLE
devices — and can use that RSSI to work out *where a signal is coming from*.

> **Passive only.** Wi-Fi and Bluetooth support here is scan/observe only.
> RFHound does **no** Wi-Fi deauth, packet injection, monitor-mode attack, or
> evil-twin creation, and **no** BLE spoofing, pairing attacks, or jamming — the
> same no-Electronic-Attack rule as the rest of the toolkit. See
> [LEGAL.md](LEGAL.md).

## What sources are available? — `sources`

```bash
rfhound sources          # HackRF present? Wi-Fi adapter? Bluetooth? + how to scan each
```

## Wi-Fi — `wifi scan`

Enumerate access points with RSSI (dBm), band, channel and security, via the
host adapter (`iw` for real dBm, or `nmcli`). `--analyze` flags defensive
signatures: **evil-twin** (one SSID on multiple BSSIDs), **open** networks, and
**new/rogue** APs vs a baseline.

```bash
rfhound wifi scan --analyze
rfhound wifi scan --json          # for a SIEM
rfhound wifi scan --simulate      # demo with no adapter
```

## Bluetooth LE — `ble scan`

Discover nearby BLE devices with RSSI, via BlueZ (`btmgmt`/`bluetoothctl`).
`--analyze` flags likely **location trackers** (AirTag/Tile/SmartTag…) and
devices that **persist across scans** (something staying near you).

```bash
rfhound ble scan --analyze
rfhound ble scan --seconds 12 --json
rfhound ble scan --simulate
```

## Locate a signal by RSSI

RSSI is a proximity cue for **any** source. Two ways to use it:

**Single node — foxhunt** (`hunt`): sample a target's RSSI and walk toward
"hotter". It shows a coarse distance from a log-distance path-loss model.

```bash
rfhound hunt --source wifi --target HomeNet --rounds 20 --interval 2
rfhound hunt --source ble  --target AirTag  --rounds 20
rfhound hunt --source hackrf --target 433.92 --rounds 20      # sweep-peak RSSI
# Calibrate: --tx-power (RSSI at 1 m) and --path-loss (2 free space, 2.5-4 indoors)
```

A single receiver's RSSI gives range (a ring), not a point — walk it in to a fix.

**Multiple nodes — geolocation**: feed each positioned receiver's RSSI for the
same target into the multi-node centroid. Several laptops each running a Wi-Fi
scan, or several HackRF nodes, sharpen the fix.

```bash
rfhound sigint locate --file reports.json    # [{"node","lat","lon","rssi"}, ...]
rfhound sigint locate --tdoa --file nodes.json   # precise, if the nodes are synced
```

Pair with the [multi-node hub](MULTINODE.md) to collect RSSI from several nodes,
and export a fix to a map with `sigint locate --geojson`.
