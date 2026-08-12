from rfhound.config import Config
from rfhound.modules import presence, wifi, bluetooth as ble, automation as auto, intel


def _obs():
    return presence.observations_from(aps=wifi.simulate_wifi(), devices=ble.simulate_ble())


def test_appear_fires_once_on_transition():
    watch = [presence.WatchItem("wifi", "HomeNet", on="appear")]
    findings, present = presence.check_presence(watch, _obs(), prev_present=set())
    assert any(f.event == "appeared" for f in findings)
    # Second evaluation with the same present-set: no repeat.
    findings2, _ = presence.check_presence(watch, _obs(), prev_present=present)
    assert findings2 == []


def test_disappear_fires_when_gone():
    watch = [presence.WatchItem("wifi", "HomeNet", on="disappear")]
    # Was present last round, now absent (empty observations).
    findings, present = presence.check_presence(watch, [], prev_present={"wifi:homenet"})
    assert any(f.event == "disappeared" for f in findings)


def test_near_respects_threshold():
    # AirTag simulated at -58 dBm; threshold -50 => not near; -70 => near.
    far = [presence.WatchItem("ble", "AirTag", on="near", rssi_threshold=-50.0)]
    f_far, _ = presence.check_presence(far, _obs(), prev_present=set())
    assert f_far == []
    near = [presence.WatchItem("ble", "AirTag", on="near", rssi_threshold=-70.0)]
    f_near, _ = presence.check_presence(near, _obs(), prev_present=set())
    assert any(f.event == "near" for f in f_near)


def test_match_by_id_and_label():
    obs = [{"kind": "wifi", "id": "aa:bb:cc:00:00:01", "label": "HomeNet", "rssi_dbm": -40}]
    assert presence._matches(presence.WatchItem("wifi", "HomeNet"), obs[0])   # by label
    assert presence._matches(presence.WatchItem("wifi", "aa:bb:cc:00:00:01"), obs[0])  # by id
    assert not presence._matches(presence.WatchItem("ble", "HomeNet"), obs[0])  # wrong kind


def test_presence_automation_task():
    cfg = Config(watchlist=[{"kind": "ble", "id": "AirTag", "on": "near", "rssi_threshold": -70.0}])
    r1 = auto.run_task(cfg, {"name": "p", "task": "presence"}, simulate=True, prev=None)
    assert r1.alert is True and "near:AirTag" in r1.summary
    r2 = auto.run_task(cfg, {"name": "p", "task": "presence"}, simulate=True, prev=r1.data["seen"])
    assert r2.alert is False   # already present => no new transition


def test_presence_empty_watchlist_no_alert():
    r = auto.run_task(Config(), {"name": "p", "task": "presence"}, simulate=True, prev=None)
    assert r.alert is False


def test_event_history_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    presence.clear_events()
    findings = [
        presence.PresenceFinding("ble", "AirTag", "AirTag", "near", "d", rssi_dbm=-58.0),
        presence.PresenceFinding("wifi", "HomeNet", "HomeNet", "appeared", "d"),
    ]
    assert presence.record_events(findings, when=1000.0) == 2
    events = presence.read_events()
    assert len(events) == 2
    assert events[0]["event"] == "near" and events[0]["rssi_dbm"] == -58.0
    assert events[1]["kind"] == "wifi" and events[1]["rssi_dbm"] is None
    assert events[0]["t"] == 1000.0
    assert presence.clear_events() == 2
    assert presence.read_events() == []


def test_read_events_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    presence.clear_events()
    for i in range(10):
        presence.record_events(
            [presence.PresenceFinding("ble", f"D{i}", "", "appeared", "d")], when=float(i))
    tail = presence.read_events(limit=3)
    assert len(tail) == 3 and [e["id"] for e in tail] == ["D7", "D8", "D9"]


def test_record_events_empty_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert presence.record_events([]) == 0
    assert presence.read_events() == []


# --- contacts (ADS-B / AIS) flow through the same presence engine ---
def test_observations_include_contacts():
    obs = presence.observations_from(contacts=intel.simulate_contacts())
    kinds = {o["kind"] for o in obs}
    assert kinds == {"contact"}
    ids = {o["id"] for o in obs}
    assert "abc123" in ids            # a simulated aircraft ICAO


def test_watch_specific_aircraft_appears():
    watch = [presence.WatchItem("contact", "abc123", on="appear", label="BAW117")]
    obs = presence.observations_from(contacts=intel.simulate_contacts())
    findings, present = presence.check_presence(watch, obs, prev_present=set())
    assert any(f.event == "appeared" and f.label == "BAW117" for f in findings)
    assert "contact:abc123" in present


def test_presence_task_alerts_on_watched_contact():
    cfg = Config(watchlist=[{"kind": "contact", "id": "235094810", "on": "near",
                             "rssi_threshold": -75.0}])
    r = auto.run_task(cfg, {"name": "p", "task": "presence"}, simulate=True, prev=None)
    assert r.alert is True and "near:" in r.summary
