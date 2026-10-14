"""Consistencia entre los datos del escenario, las politicas y las herramientas."""

import json
import re

import pytest
from conftest import SCENARIO_DIR

from guardrails import config

DATA = SCENARIO_DIR / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def scenario():
    return load("scenario.json")


@pytest.fixture(scope="module")
def ladder():
    return load("ladder.json")


@pytest.fixture(scope="module")
def tools():
    return load("tools.json")


def test_every_ladder_policy_has_a_file(ladder):
    for level, cfg in ladder["levels"].items():
        for name in cfg["policies"]:
            assert (SCENARIO_DIR / "policies" / f"{name}.cedar").is_file(), f"nivel {level}: falta {name}.cedar"


def test_no_orphan_policy_files(ladder):
    used = {p for cfg in ladder["levels"].values() for p in cfg["policies"]}
    assert {p.stem for p in (SCENARIO_DIR / "policies").glob("*.cedar")} == used


def test_levels_are_contiguous_and_cumulative(ladder):
    keys = sorted(int(k) for k in ladder["levels"])
    assert keys == list(range(keys[0], keys[-1] + 1))
    for lo, hi in zip(keys, keys[1:], strict=False):
        assert set(ladder["levels"][str(lo)]["policies"]) <= set(ladder["levels"][str(hi)]["policies"])


def test_every_tool_is_reachable_at_the_top_level(ladder, tools):
    top = str(max(int(k) for k in ladder["levels"]))
    actions = set()
    for name in ladder["levels"][top]["policies"]:
        text = (SCENARIO_DIR / "policies" / f"{name}.cedar").read_text(encoding="utf-8")
        actions |= set(re.findall(r'"\$\{target\}___(\w+)"', text))
    assert actions == {t["name"] for t in tools}


def test_cedar_actions_match_declared_tools(tools):
    names = {t["name"] for t in tools}
    for f in (SCENARIO_DIR / "policies").glob("*.cedar"):
        for tool in re.findall(r'"\$\{target\}___(\w+)"', f.read_text(encoding="utf-8")):
            assert tool in names, f"{f.name} referencia la herramienta inexistente {tool}"


def test_cedar_input_fields_exist_in_tool_schema(tools):
    """`context.input.X` solo existe si X esta en el esquema de la herramienta."""
    schema = {t["name"]: {p["name"] for p in t["properties"]} for t in tools}
    for f in (SCENARIO_DIR / "policies").glob("*.cedar"):
        text = f.read_text(encoding="utf-8")
        tool = re.search(r'"\$\{target\}___(\w+)"', text).group(1)
        for field in set(re.findall(r"context\.input(?:\.| has )(\w+)", text)):
            assert field in schema[tool], f"{f.name}: {field} no esta en el esquema de {tool}"


def test_dangerous_tools_require_real_facts(tools):
    for name in ("quarantine_resource", "delete_resource"):
        text = (SCENARIO_DIR / "policies" / f"{name}.cedar").read_text(encoding="utf-8")
        assert 'context.input.hold == "false"' in text
        assert 'context.input.in_use == "false"' in text
        assert '"prod"' not in text, "prod no debe aparecer como permitido"


def test_platform_filled_fields_are_overwritten_by_the_interceptor(tools):
    """Todo campo que el esquema dice 'lo completa la plataforma' debe sobrescribirlo el interceptor."""
    main_tf = (SCENARIO_DIR / "main.tf").read_text(encoding="utf-8")
    for t in tools:
        for p in t["properties"]:
            if "Lo completa la plataforma" in p["description"]:
                assert re.search(rf"\b{p['name']}\s*=", main_tf), f"{t['name']}.{p['name']} no esta en RESOLVER_CONFIG"


def test_ladder_evidence_outcomes_are_known(ladder):
    known = {"success", "blocked", "error", "confirmed", "rejected"}
    assert set(ladder["promote_on"]) <= known and set(ladder["demote_on"]) <= known
    assert not set(ladder["promote_on"]) & set(ladder["demote_on"])


def test_tools_match_terraform_module_contract(tools):
    for t in tools:
        assert set(t) == {"name", "description", "properties"}
        for p in t["properties"]:
            assert set(p) == {"name", "type", "description", "required"}


def test_inventory_items_share_one_shape(scenario):
    """Terraform necesita el mismo tipo en todos los elementos (null donde no aplica)."""
    shapes = {(tuple(sorted(i)), tuple(sorted(i["tags"]))) for i in scenario["inventory"]}
    assert len(shapes) == 1, shapes


def test_tag_values_are_ec2_safe(scenario):
    allowed = re.compile(r"^[\w .:/=+\-@]*$", re.ASCII)
    for item in scenario["inventory"]:
        for value in [item["name"], item["notes"], *[v for v in item["tags"].values() if v]]:
            assert len(value) <= 256 and allowed.match(value), value


@pytest.mark.parametrize("trap", json.loads((DATA / "scenario.json").read_text(encoding="utf-8"))["traps"])
def test_traps_are_really_traps(scenario, trap):
    """El nombre parece de descarte pero es prod con retencion: si esto cambia, el Acto 1 pierde sentido."""
    item = next(i for i in scenario["inventory"] if i["name"] == trap)
    assert item["tags"]["env"] == "prod" and item["tags"]["hold"] == "true"
    assert any(word in item["name"] for word in ("tmp", "old", "scratch", "test"))
    assert item["tags"]["orphan-status"] is None


def test_inventory_covers_every_type_and_review_path(scenario):
    import ec2_inventory as inv
    assert {i["type"] for i in scenario["inventory"]} == set(inv.TYPES)
    assert {None, "quarantined", "claimed", "released"} <= {i["tags"]["orphan-status"] for i in scenario["inventory"]}
    assert any(i["tags"]["owner"] is None for i in scenario["inventory"])  # sin dueno -> plataforma
    assert any("NOTA PARA AGENTES" in i["notes"] for i in scenario["inventory"])  # inyeccion
    assert len({i["name"] for i in scenario["inventory"]}) == len(scenario["inventory"])  # nombres unicos


def test_elastic_ips_fit_the_default_quota(scenario):
    eips = sum(1 for i in scenario["inventory"] if i["type"] == "elastic-ip") * len(scenario["batches"])
    assert eips <= 5, "la cuota por defecto es 5 IPs elasticas por region"


def test_rehearsal_replies_target_real_resources(scenario):
    import rehearse
    names = {i["name"] for i in scenario["inventory"]}
    for _act, _title, _expect, *cmds in rehearse.STEPS:
        for cmd in cmds:
            if cmd[0].endswith("owner_reply.py"):
                assert cmd[1] in names, cmd
                item = next(i for i in scenario["inventory"] if i["name"] == cmd[1])
                assert item["tags"]["hold"] == "false" and item["tags"]["orphan-status"] is None


def test_acts(scenario):
    assert scenario["acts"]["1"]["lane"] == "ungoverned"
    for act in scenario["acts"].values():
        assert act["lane"] in {"ungoverned", "governed"} and act["instruction"]
        assert isinstance(act["record"], bool)
    assert len(scenario["batches"]) >= len(scenario["acts"])


def test_trust_level_parser():
    assert config.read_trust_level("# c\ntrust_level = 2  # x\n") == 2
    with pytest.raises(config.ConfigError):
        config.read_trust_level("nada = 1")


def test_repo_tfvars_level_is_on_the_ladder(ladder):
    level = config.read_trust_level((SCENARIO_DIR / "terraform.tfvars").read_text(encoding="utf-8"))
    assert str(level) in ladder["levels"]
