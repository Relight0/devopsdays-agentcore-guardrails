"""Contrato estatico de Terraform (sin terraform, sin AWS)."""

import re
from pathlib import Path

import hcl2
import pytest
from conftest import ROOT

META = {"source", "depends_on", "count", "for_each", "providers", "version", "__comments__", "__is_block__"}


def unq(value):
    """python-hcl2 devuelve algunas cadenas con comillas incluidas segun la version."""
    return value.strip('"') if isinstance(value, str) else value


def parse(path):
    with open(path, encoding="utf-8") as fh:
        return hcl2.load(fh)


def blocks(directory, kind):
    out = []
    for tf in sorted(Path(directory).glob("*.tf")):
        out.extend(parse(tf).get(kind, []))
    return out


def module_interface(directory):
    variables = {unq(name): cfg for block in blocks(directory, "variable") for name, cfg in block.items()}
    outputs = {unq(name) for block in blocks(directory, "output") for name in block}
    required = {n for n, c in variables.items() if "default" not in c}
    return set(variables), required, outputs


def module_calls():
    calls = []
    for example in sorted((ROOT / "examples").iterdir()):
        for block in blocks(example, "module"):
            for name, cfg in block.items():
                calls.append((example, unq(name), cfg))
    return calls


CALLS = module_calls()
IDS = [f"{ex.name}.{name}" for ex, name, _ in CALLS]


def test_there_are_module_calls():
    assert len(CALLS) >= 6


@pytest.mark.parametrize(("example", "name", "cfg"), CALLS, ids=IDS)
def test_module_call_matches_interface(example, name, cfg):
    source = (example / unq(cfg["source"])).resolve()
    assert source.is_dir(), f"source no existe: {cfg['source']}"
    declared, required, _ = module_interface(source)
    passed = {unq(k) for k in cfg} - META
    assert not passed - declared, f"argumentos que el modulo no declara: {sorted(passed - declared)}"
    assert not required - passed, f"variables obligatorias sin pasar: {sorted(required - passed)}"


@pytest.mark.parametrize("example", sorted((ROOT / "examples").iterdir()), ids=lambda p: p.name)
def test_module_output_references_exist(example):
    calls = {name: (example / unq(cfg["source"])).resolve() for _, name, cfg in module_calls() if _ == example}
    text = "\n".join(p.read_text(encoding="utf-8") for p in example.glob("*.tf"))
    for mod, out in set(re.findall(r"\bmodule\.(\w+)\.(\w+)", text)):
        if mod not in calls:
            continue  # p. ej. el destino de un -target en comentarios
        assert out in module_interface(calls[mod])[2], f"module.{mod}.{out} no existe"


def test_templates_use_only_known_placeholders():
    """Las plantillas Cedar solo pueden usar variables que el modulo trust-ladder inyecta."""
    injected = {"gateway_arn", "target", "account_id"}
    for f in (ROOT / "examples").glob("*/policies/*.cedar"):
        assert set(re.findall(r"\$\{(\w+)\}", f.read_text(encoding="utf-8"))) <= injected, f.name


def test_provider_versions_are_pinned_consistently():
    versions = set()
    for tf in ROOT.glob("**/*.tf"):
        if ".terraform" in tf.parts:
            continue
        for block in parse(tf).get("terraform", []):
            for providers in block.get("required_providers", []):
                for name, cfg in providers.items():
                    if unq(name) == "aws":
                        versions.add(unq(cfg["version"]))
    assert versions == {"~> 6.67"}, versions


def test_python_only_reads_outputs_that_terraform_declares():
    """Contrato outputs.tf <-> paquete Python: renombrar un output rompe la prueba, no el escenario en vivo."""
    declared = module_interface(ROOT / "examples" / "orphan-hunter")[2]
    used = set()
    for py in [*(ROOT / "guardrails").glob("*.py"), *(ROOT / "scripts").glob("*.py")]:
        used |= set(re.findall(r"\bout(?:puts\(\))?\[\"(\w+)\"\]", py.read_text(encoding="utf-8")))
        used |= set(re.findall(r"config\.outputs\(\)\[\"(\w+)\"\]", py.read_text(encoding="utf-8")))
    assert used, "no encontre usos de outputs (la expresion regular quedo vieja)"
    assert used <= declared, f"Python lee outputs que no existen: {sorted(used - declared)}"


ROOT_STACKS = [ROOT / "examples" / "orphan-hunter", ROOT / "bootstrap"]


@pytest.mark.parametrize("stack", ROOT_STACKS, ids=lambda p: p.name)
def test_root_variables_are_all_set_in_tfvars(stack):
    """En los root modules todo valor vive en terraform.tfvars: sin defaults escondidos."""
    variables = {unq(n): c for block in blocks(stack, "variable") for n, c in block.items()}
    with_default = sorted(n for n, c in variables.items() if "default" in c)
    assert not with_default, f"variables con default en {stack.name}: {with_default}"
    tfvars = {unq(k) for k in parse(stack / "terraform.tfvars") if not k.startswith("__")}
    assert tfvars == set(variables), {"faltan": sorted(set(variables) - tfvars),
                                      "sobran": sorted(tfvars - set(variables))}


def test_bootstrap_matches_stack():
    stack = parse(ROOT / "examples" / "orphan-hunter" / "terraform.tfvars")
    boot = parse(ROOT / "bootstrap" / "terraform.tfvars")
    for key in ("region", "project_name"):
        assert unq(boot[key]) == unq(stack[key]), key
    assert unq(stack["repository"]) == f"{unq(boot['github_owner'])}/{unq(boot['github_repo'])}"
