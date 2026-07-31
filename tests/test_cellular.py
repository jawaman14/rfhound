from rfhound.modules import cellular


def test_simulated_catcher_is_flagged():
    obs = cellular.simulate_observations()
    alerts = cellular.detect_rogue_bts(obs, known_lacs={4120})
    indicators = {a.indicator for a in alerts}
    assert "encryption-downgrade" in indicators
    assert "empty-neighbor-list" in indicators
    assert "lac-anomaly" in indicators
    assert cellular.score(alerts) >= 50


def test_clean_network_no_alerts():
    obs = [
        cellular.CellObservation("GSM", "310", "260", lac=4120, cid=1, arfcn=128,
                                 rxlev=-80, cipher="A5/3", neighbors=[131, 140]),
    ]
    alerts = cellular.detect_rogue_bts(obs, known_lacs={4120})
    assert alerts == []


def test_unexpected_operator_flagged():
    obs = [cellular.CellObservation("GSM", "999", "99", lac=4120, cid=1, arfcn=128,
                                    rxlev=-80, cipher="A5/1", neighbors=[131])]
    alerts = cellular.detect_rogue_bts(obs, expected_operators=[("310", "260")],
                                       known_lacs={4120})
    assert any(a.indicator == "unexpected-operator" for a in alerts)


def test_cid_arfcn_reuse_flagged():
    obs = [
        cellular.CellObservation("GSM", "310", "260", lac=4120, cid=7, arfcn=100,
                                 rxlev=-80, cipher="A5/1", neighbors=[1]),
        cellular.CellObservation("GSM", "310", "260", lac=4120, cid=7, arfcn=200,
                                 rxlev=-80, cipher="A5/1", neighbors=[1]),
    ]
    alerts = cellular.detect_rogue_bts(obs, known_lacs={4120})
    assert any(a.indicator == "cid-arfcn-mismatch" for a in alerts)
