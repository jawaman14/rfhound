from rfhound.modules import wifi, bluetooth as ble, rssi, sigint, oui, sightings


# --- RSSI linked to identifiers (sightings) ---
def test_ingest_wifi_links_rssi_to_bssid(tmp_path):
    store = sightings.SightingsStore(path=tmp_path / "s.json")
    sightings.ingest_wifi(store, wifi.simulate_wifi())
    homenet = store.get("wifi", "aa:bb:cc:00:00:01")
    assert homenet is not None
    assert homenet.label == "HomeNet"          # SSID linked to the BSSID
    assert homenet.rssi_dbm == -42.0
    assert homenet.rssi_best == -42.0


def test_ingest_ble_links_rssi_and_name(tmp_path):
    store = sightings.SightingsStore(path=tmp_path / "s.json")
    sightings.ingest_ble(store, ble.simulate_ble())
    tag = store.get("ble", "11:22:33:44:55:66")
    assert tag.label == "AirTag" and tag.rssi_dbm == -58.0


def test_rssi_best_tracks_strongest(tmp_path):
    store = sightings.SightingsStore(path=tmp_path / "s.json")
    store.record("wifi", "aa:bb", label="Net", rssi_dbm=-70.0, save=False)
    store.record("wifi", "aa:bb", label="Net", rssi_dbm=-55.0, save=False)  # closer
    store.record("wifi", "aa:bb", label="Net", rssi_dbm=-62.0, save=False)
    s = store.get("wifi", "aa:bb")
    assert s.rssi_dbm == -62.0 and s.rssi_best == -55.0 and s.count == 3
    assert s.rssi_history == [-70.0, -55.0, -62.0]


def test_rssi_history_capped(tmp_path):
    store = sightings.SightingsStore(path=tmp_path / "s.json")
    for i in range(sightings.RSSI_HISTORY_MAX + 15):
        store.record("wifi", "aa:bb", rssi_dbm=float(-i), save=False)
    s = store.get("wifi", "aa:bb")
    assert len(s.rssi_history) == sightings.RSSI_HISTORY_MAX   # rolling window


def test_sparkline():
    assert sightings.sparkline([]) == ""
    assert sightings.sparkline([-50]) == ""          # needs >=2 points
    spark = sightings.sparkline([-80, -60, -40])
    assert len(spark) == 3 and spark[0] < spark[-1]  # rising


# --- OUI vendor lookup ---
def test_oui_known_vendor():
    assert oui.lookup("B8:27:EB:11:22:33") == "Raspberry Pi"
    assert oui.lookup("246F28aabbcc") == "Espressif (ESP32)"


def test_oui_locally_administered():
    # 0x02 bit set in the first octet => randomized/private.
    assert oui.is_locally_administered("aa:bb:cc:00:00:01") is True
    assert oui.lookup("aa:bb:cc:00:00:01") == "random/private"
    assert oui.lookup("zz") == ""


# --- Wi-Fi channel report ---
def test_wifi_channel_report():
    reports = wifi.channel_report(wifi.simulate_wifi())
    bands = {r.band for r in reports}
    assert "2.4GHz" in bands
    r24 = [r for r in reports if r.band == "2.4GHz"][0]
    assert set(r24.recommended) <= {1, 6, 11}


# --- Wi-Fi ---
def test_wifi_simulate_and_evil_twin():
    aps = wifi.simulate_wifi()
    assert len(aps) == 4
    findings = wifi.analyze_wifi(aps)
    kinds = {f.indicator for f in findings}
    assert "evil-twin?" in kinds          # HomeNet on two BSSIDs
    assert "open-network" in kinds


def test_wifi_baseline_flags_new_ap():
    aps = wifi.simulate_wifi()
    baseline = {aps[0].bssid}
    findings = wifi.analyze_wifi(aps, baseline_bssids=baseline)
    assert any(f.indicator == "new-ap" for f in findings)


def test_wifi_band_classification():
    assert wifi.WifiAp("x", "y", -50, freq_mhz=2437.0).band == "2.4GHz"
    assert wifi.WifiAp("x", "y", -50, freq_mhz=5180.0).band == "5GHz"


def test_wifi_parse_iw():
    text = (
        "BSS aa:bb:cc:dd:ee:ff(on wlan0)\n"
        "\tfreq: 2437\n\tsignal: -45.00 dBm\n\tSSID: TestNet\n\tRSN:\n"
        "BSS 11:22:33:44:55:66(on wlan0)\n"
        "\tfreq: 5180\n\tsignal: -70.00 dBm\n\tSSID: Other\n"
    )
    aps = wifi._parse_iw(text)
    assert len(aps) == 2
    assert aps[0].bssid == "aa:bb:cc:dd:ee:ff" and aps[0].rssi_dbm == -45.0
    assert aps[0].ssid == "TestNet" and aps[0].security == "WPA2/3"
    assert aps[1].security == "open"


# --- BLE ---
def test_ble_simulate_and_tracker():
    devices = ble.simulate_ble()
    findings = ble.analyze_ble(devices)
    assert any(f.indicator == "tracker" and f.severity == "high" for f in findings)


def test_ble_persistent_device():
    devices = ble.simulate_ble()
    seen = {"aa:11:bb:22:cc:33"}   # Fitbit seen before, strong
    findings = ble.analyze_ble(devices, seen_before=seen)
    assert any(f.indicator == "persistent" for f in findings)


def test_ble_parse_btmgmt():
    text = (
        "hci0 dev_found: 11:22:33:44:55:66 type LE Random rssi -62 flags 0x0\n"
        "name AirTag\n"
        "hci0 dev_found: aa:bb:cc:dd:ee:ff type LE Public rssi -80 flags 0x0\n"
    )
    devices = ble._parse_btmgmt(text)
    assert len(devices) == 2
    tag = [d for d in devices if d.addr == "11:22:33:44:55:66"][0]
    assert tag.rssi_dbm == -62 and tag.name == "AirTag" and tag.kind == "tracker?"


# --- RSSI ---
def test_rssi_distance_monotonic():
    near = rssi.estimate_distance_m(-40)
    far = rssi.estimate_distance_m(-80)
    assert far > near > 0


def test_rssi_hunt_trend_hotter():
    t = rssi.hunt_trend([-85, -78, -70, -62])
    assert t.trend == "hotter"
    assert t.best_dbm == -62.0
    assert t.est_distance_m > 0


def test_rssi_multinode_locate():
    nodes = [
        {"node": "n1", "lat": 51.50, "lon": -0.12, "rssi_dbm": -45},
        {"node": "n2", "lat": 51.51, "lon": -0.10, "rssi_dbm": -60},
        {"node": "n3", "lat": 51.49, "lon": -0.13, "rssi_dbm": -70},
    ]
    est = sigint.geolocate(rssi.reports_from_nodes(nodes))
    assert est.lat is not None and est.n_receivers == 3
    # Weighted toward the strongest (n1) node.
    assert abs(est.lat - 51.50) < abs(est.lat - 51.49)
