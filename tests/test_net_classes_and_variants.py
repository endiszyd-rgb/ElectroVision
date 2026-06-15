"""Tests for Net Classes Manager and Design Variants."""
import json
import pytest

from src.ui.dialogs.net_classes_dialog import NetClass, BUILTIN_CLASSES
from src.ui.dialogs.variants_dialog import DesignVariant, ComponentOverride


# ── Net Classes ────────────────────────────────────────────────────────────────

class TestNetClass:
    def test_default_values(self):
        nc = NetClass(name="Test")
        assert nc.min_width_mm == pytest.approx(0.2)
        assert nc.min_clearance_mm == pytest.approx(0.2)
        assert nc.nets == []

    def test_to_dict_roundtrip(self):
        nc = NetClass(name="HighSpeed", min_width_mm=0.1, min_clearance_mm=0.15)
        nc.nets = ["CLK", "DATA"]
        d = nc.to_dict()
        nc2 = NetClass.from_dict(d)
        assert nc2.name == "HighSpeed"
        assert nc2.min_width_mm == pytest.approx(0.1)
        assert nc2.min_clearance_mm == pytest.approx(0.15)
        assert nc2.nets == ["CLK", "DATA"]

    def test_from_dict_missing_keys_uses_defaults(self):
        nc = NetClass.from_dict({"name": "X"})
        assert nc.min_width_mm == pytest.approx(0.2)
        assert nc.color == "#4080c0"
        assert nc.nets == []

    def test_color_field(self):
        nc = NetClass(name="RF", color="#c08020")
        assert nc.color == "#c08020"

    def test_diff_pair_fields(self):
        nc = NetClass(name="DP", diff_pair_gap_mm=0.15, diff_pair_skew_mm=0.025)
        d = nc.to_dict()
        nc2 = NetClass.from_dict(d)
        assert nc2.diff_pair_gap_mm == pytest.approx(0.15)
        assert nc2.diff_pair_skew_mm == pytest.approx(0.025)

    def test_json_serialisation(self):
        classes = list(BUILTIN_CLASSES)
        data = [nc.to_dict() for nc in classes]
        text = json.dumps(data)
        loaded = [NetClass.from_dict(d) for d in json.loads(text)]
        assert len(loaded) == len(classes)
        assert loaded[0].name == classes[0].name


class TestBuiltinClasses:
    def test_six_presets(self):
        assert len(BUILTIN_CLASSES) == 6

    def test_default_class_exists(self):
        names = [nc.name for nc in BUILTIN_CLASSES]
        assert "Default" in names

    def test_power_class_wider_than_default(self):
        default = next(nc for nc in BUILTIN_CLASSES if nc.name == "Default")
        power   = next(nc for nc in BUILTIN_CLASSES if nc.name == "Power")
        assert power.min_width_mm > default.min_width_mm

    def test_highspeed_narrower_than_default(self):
        default = next(nc for nc in BUILTIN_CLASSES if nc.name == "Default")
        hs      = next(nc for nc in BUILTIN_CLASSES if nc.name == "HighSpeed")
        assert hs.min_width_mm < default.min_width_mm

    def test_power_has_gnd_and_vcc(self):
        power = next(nc for nc in BUILTIN_CLASSES if nc.name == "Power")
        assert "GND" in power.nets
        assert "VCC" in power.nets


# ── Design Variants ────────────────────────────────────────────────────────────

def _make_comp(ref, value="10k"):
    from src.core.models.component import Component
    return Component(ref, value, "R_0402", 0, 0)


class TestComponentOverride:
    def test_default_not_dnp(self):
        ov = ComponentOverride(reference="R1")
        assert ov.dnp is False
        assert ov.alt_value == ""
        assert ov.notes == ""

    def test_roundtrip(self):
        ov = ComponentOverride(reference="R1", dnp=True, alt_value="4k7", notes="proto only")
        d = ov.to_dict()
        ov2 = ComponentOverride.from_dict(d)
        assert ov2.reference == "R1"
        assert ov2.dnp is True
        assert ov2.alt_value == "4k7"
        assert ov2.notes == "proto only"

    def test_from_dict_defaults(self):
        ov = ComponentOverride.from_dict({"reference": "C1"})
        assert ov.dnp is False
        assert ov.alt_footprint == ""


class TestDesignVariant:
    def test_empty_dnp_set(self):
        v = DesignVariant(name="Prod")
        assert v.dnp_set() == set()

    def test_dnp_set_after_adding_override(self):
        v = DesignVariant(name="Lite")
        v.overrides.append(ComponentOverride(reference="R5", dnp=True))
        assert "R5" in v.dnp_set()

    def test_non_dnp_override_not_in_dnp_set(self):
        v = DesignVariant(name="Prod")
        v.overrides.append(ComponentOverride(reference="R3", dnp=False, alt_value="22k"))
        assert "R3" not in v.dnp_set()

    def test_override_for_existing(self):
        v = DesignVariant(name="Prod")
        ov = ComponentOverride(reference="U1", dnp=True)
        v.overrides.append(ov)
        assert v.override_for("U1") is ov

    def test_override_for_missing(self):
        v = DesignVariant(name="Prod")
        assert v.override_for("X99") is None

    def test_effective_bom_excludes_dnp(self):
        v = DesignVariant(name="Lite")
        v.overrides.append(ComponentOverride(reference="U2", dnp=True))
        comps = [_make_comp("R1"), _make_comp("U2"), _make_comp("C1")]
        bom = v.effective_bom(comps)
        refs = [c.reference for c, _ in bom]
        assert "U2" not in refs
        assert "R1" in refs
        assert "C1" in refs

    def test_effective_bom_includes_substituted(self):
        v = DesignVariant(name="Alt")
        v.overrides.append(ComponentOverride(reference="R1", alt_value="22k"))
        comps = [_make_comp("R1"), _make_comp("R2")]
        bom = v.effective_bom(comps)
        assert len(bom) == 2
        r1_ov = next(ov for comp, ov in bom if comp.reference == "R1")
        assert r1_ov is not None
        assert r1_ov.alt_value == "22k"

    def test_roundtrip_json(self):
        v = DesignVariant(name="Proto", description="development board")
        v.overrides.append(ComponentOverride(reference="R1", dnp=True))
        v.overrides.append(ComponentOverride(reference="C3", alt_value="47pF"))
        d = v.to_dict()
        v2 = DesignVariant.from_dict(d)
        assert v2.name == "Proto"
        assert v2.description == "development board"
        assert len(v2.overrides) == 2
        assert v2.override_for("R1").dnp is True
        assert v2.override_for("C3").alt_value == "47pF"

    def test_empty_variant_roundtrip(self):
        v = DesignVariant(name="Empty")
        d = v.to_dict()
        v2 = DesignVariant.from_dict(d)
        assert v2.name == "Empty"
        assert v2.overrides == []

    def test_multiple_variants_json(self):
        variants = [
            DesignVariant(name="Prod"),
            DesignVariant(name="Proto"),
        ]
        variants[1].overrides.append(ComponentOverride(reference="U3", dnp=True))
        data = [v.to_dict() for v in variants]
        loaded = [DesignVariant.from_dict(d) for d in data]
        assert loaded[0].name == "Prod"
        assert loaded[1].name == "Proto"
        assert loaded[1].override_for("U3").dnp is True
