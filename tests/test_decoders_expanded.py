from rfhound.config import Config
from rfhound.modules import decode as decode_mod


def test_many_recipes_registered():
    ids = {r.id for r in decode_mod.list_recipes()}
    # A representative spread across the spectrum.
    for rid in ["rtl433", "adsb", "uat978", "vdl2", "ert", "dsd", "hdradio",
                "wspr", "tetra", "noaa_apt", "radiosonde", "satdump", "iridium", "flex"]:
        assert rid in ids, rid
    assert len(ids) >= 18


def test_every_recipe_builds_a_command():
    cfg = Config()
    for r in decode_mod.list_recipes():
        cmd = decode_mod.build_command(r, cfg)
        assert isinstance(cmd, list) and cmd
        assert cmd[0] == r.tool


def test_recipe_categories_are_known():
    cats = {r.category for r in decode_mod.list_recipes()}
    # Should span multiple domains.
    assert {"aviation", "ism", "satellite", "paging"} <= cats


def test_dry_run_uat978():
    cfg = Config()
    r = decode_mod.get_recipe("uat978")
    out = decode_mod.run_decoder(r, cfg, dry_run=True)
    assert "dump978-fa" in out[0]
