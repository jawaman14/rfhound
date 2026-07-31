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
