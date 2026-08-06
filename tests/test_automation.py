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


def test_run_task_all_types_simulate(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))  # emitters writes a catalog
    cfg = Config()
    for task in auto.TASKS:
        a = {"name": task, "task": task, "params": {"start": 433, "stop": 435}}
        res = auto.run_task(cfg, a, simulate=True)
        assert isinstance(res, auto.AutoResult)
        assert res.summary


def test_gnss_task_alerts_on_spoofing():
    cfg = Config()
    a = {"name": "g", "task": "gnss",
         "params": {"scenario": "spoofing", "static": True}, "alert_on": "threat"}
    res = auto.run_task(cfg, a, simulate=True)
    assert res.alert is True
    assert res.data["status"] == "spoofing"


def test_gnss_task_nominal_no_alert():
    cfg = Config()
    a = {"name": "g", "task": "gnss", "params": {"scenario": "nominal"}}
    res = auto.run_task(cfg, a, simulate=True)
    assert res.alert is False


def test_emitters_task_flags_new(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    a = {"name": "eob", "task": "emitters", "params": {"start": 430, "stop": 440}}
    first = auto.run_task(cfg, a, simulate=True)
    assert first.data["emitters"]          # found some
    assert first.data["new"]               # all new the first time
    second = auto.run_task(cfg, a, simulate=True)
    assert second.data["new"] == []        # already in the catalogue => not new


def test_email_alert_sent_on_fire(tmp_path, monkeypatch):
    import smtplib
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0):
            sent["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    cfg = Config(smtp_host="mail.test", smtp_user="u", smtp_password="p")
    a = {"name": "j", "task": "gnss", "params": {"scenario": "jamming"},
         "alert_on": "threat", "email": "you@test", "webhook": ""}
    res = auto.run_task(cfg, a, simulate=True)
    auto.fire(cfg, a, res, alerting=True)
    assert sent.get("to") == "you@test"
    assert "RFHound alert" in sent.get("subject", "")


def test_email_not_sent_without_config():
    # No smtp_host => send_email is a no-op returning False.
    assert auto.send_email(Config(), "x@y", "s", "b") is False


def test_ndjson_scheduler_stream(tmp_path, monkeypatch, capsys):
    import json as _json
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    auto.add_automation(cfg, "jam", "gnss", interval_s=0, params={"scenario": "jamming"})
    auto.run_scheduler(cfg, simulate=True, tick_s=0, max_ticks=1, ndjson=True)
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert out
    ev = _json.loads(out[0])  # every line is valid JSON
    assert ev["name"] == "jam" and "summary" in ev


def test_alert_cooldown_suppresses_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    auto.add_automation(cfg, "jam", "gnss", interval_s=0,
                        params={"scenario": "jamming"}, alert_cooldown_s=100)
    state = {}
    ev1 = auto.run_due(cfg, simulate=True, state=state, now=1000.0, force=True)
    ev2 = auto.run_due(cfg, simulate=True, state=state, now=1010.0, force=True)
    ev3 = auto.run_due(cfg, simulate=True, state=state, now=1200.0, force=True)
    assert ev1[0]["alert"] is True     # first detection alerts
    assert ev2[0]["alert"] is False    # within cooldown => suppressed
    assert ev3[0]["alert"] is True     # after cooldown => alerts again


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
