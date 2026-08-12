from rfhound import cli


def run(argv):
    return cli.main(argv)


def test_defense_monitor_simulate_returns_jammed(capsys):
    rc = run(["defense", "monitor", "433", "435", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 1  # jamming detected -> non-zero
    assert "JAMMING" in out.upper()


def test_defense_rolling_assess_fixed(capsys):
    rc = run(["defense", "rolling-assess", "--simulate", "--kind", "fixed"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "FIXED" in out.upper()


def test_defense_rolling_assess_rolling(capsys):
    rc = run(["defense", "rolling-assess", "--simulate", "--kind", "rolling"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ROLLING" in out.upper()


def test_defense_replay_check_simulate(capsys):
    rc = run(["defense", "replay-check", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "replay" in out.lower()


def test_defense_resilience_simulate(capsys):
    rc = run(["defense", "resilience", "--device", "fob1", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "resilience" in out.lower()


def test_defense_imsi_detect_and_alias(capsys):
    rc = run(["defense", "imsi-detect", "--simulate"])
    out = capsys.readouterr().out
    assert rc == 1                       # rogue-BTS indicators found -> non-zero
    assert "IMSI" in out.upper()
    # The legacy name stays a working alias.
    rc2 = run(["defense", "imsi-catcher", "--simulate"])
    assert rc2 == 1
    assert "IMSI" in capsys.readouterr().out.upper()
