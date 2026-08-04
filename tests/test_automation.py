from rfhound.config import Config
from rfhound.modules import automation as auto


def test_add_remove_enable(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    auto.add_automation(cfg, "watch433", "monitor", interval_s=30,
                        params={"start": 433, "stop": 435})
    assert cfg.automations[0]["name"] == "watch433"
    assert auto.set_enabled(cfg, "watch433", False)
    assert cfg.automations[0]["enabled"] is False
    assert auto.remove_automation(cfg, "watch433")
    assert cfg.automations == []


def test_run_task_all_types_simulate():
    cfg = Config()
    for task in auto.TASKS:
        a = {"name": task, "task": task, "params": {"start": 433, "stop": 435}}
        res = auto.run_task(cfg, a, simulate=True)
        assert isinstance(res, auto.AutoResult)
        assert res.summary


def test_monitor_alerts_on_jamming():
    cfg = Config()
    a = {"name": "m", "task": "monitor", "params": {"start": 433, "stop": 435},
         "alert_on": "threat"}
    res = auto.run_task(cfg, a, simulate=True)
    assert res.alert is True  # simulated jammer switches on
    assert auto.should_alert(a, res)


def test_alert_modes():
    a_always = {"name": "x", "task": "hop", "alert_on": "always"}
    res = auto.AutoResult(False, "nothing", {})
    assert auto.should_alert(a_always, res) is True
    a_threat = {"name": "x", "task": "hop", "alert_on": "threat"}
    assert auto.should_alert(a_threat, res) is False


def test_run_due_respects_interval(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    auto.add_automation(cfg, "d", "drone", interval_s=100)
    state = {}
    ev1 = auto.run_due(cfg, simulate=True, state=state, now=1000.0)
    assert len(ev1) == 1                       # first run (force via 0 last_run)
    ev2 = auto.run_due(cfg, simulate=True, state=state, now=1050.0)
    assert ev2 == []                            # not due yet
    ev3 = auto.run_due(cfg, simulate=True, state=state, now=1200.0)
    assert len(ev3) == 1                        # due again


def test_fire_writes_log(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    a = {"name": "d", "task": "drone"}
    res = auto.AutoResult(True, "1 drone-band detection(s)", {"hits": ["2.4G"]})
    auto.fire(cfg, a, res, alerting=True)
    log = auto.automations_log()
    assert log.exists() and "drone-band" in log.read_text()


def test_scheduler_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    auto.add_automation(cfg, "d", "drone", interval_s=1)
    # max_ticks bounds the loop so the test terminates.
    auto.run_scheduler(cfg, simulate=True, tick_s=0.01, max_ticks=2)
