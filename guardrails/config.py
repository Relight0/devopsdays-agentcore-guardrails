"""Configuracion: el escenario son datos (JSON) y la infraestructura es la fuente de verdad (outputs)."""

import functools
import json
import os
import shutil
import subprocess
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIO_DIR = REPO_ROOT / "examples" / "orphan-hunter"


class ConfigError(RuntimeError):
    pass


def scenario_dir():
    return Path(os.environ.get("GUARDRAILS_DIR", DEFAULT_SCENARIO_DIR)).resolve()


def _read_json(name):
    path = scenario_dir() / "data" / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise ConfigError(f"No encuentro {path}") from err


def scenario():
    return _read_json("scenario.json")


def ladder_config():
    return _read_json("ladder.json")


def agent_id():
    return scenario()["agent_id"]


@functools.lru_cache(maxsize=4)
def _outputs(tf_dir):
    terraform = shutil.which("terraform")
    if not terraform:
        raise ConfigError("No encuentro terraform en el PATH.")
    proc = subprocess.run(
        [terraform, f"-chdir={tf_dir}", "output", "-json"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise ConfigError(f"terraform output fallo:\n{proc.stderr}")
    raw = json.loads(proc.stdout or "{}")
    if not raw:
        raise ConfigError(f"No hay outputs. Corre primero: terraform -chdir={tf_dir} apply")
    return {k: v["value"] for k, v in raw.items()}


def outputs():
    return _outputs(str(scenario_dir()))


def read_trust_level(text):
    """Extrae trust_level de un .tfvars. Pura: se prueba sin Terraform."""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("trust_level") and "=" in line:
            return int(line.split("=", 1)[1].strip())
    raise ConfigError("No encuentro trust_level en terraform.tfvars")


def tfvars_path():
    return scenario_dir() / "terraform.tfvars"


def trust_level():
    """Nivel actual, leido de terraform.tfvars (los outputs quedan viejos tras un apply con -target)."""
    return read_trust_level(tfvars_path().read_text(encoding="utf-8"))


def session():
    """Sesion de boto3 con la misma cadena de credenciales que usa Terraform."""
    return boto3.Session(region_name=outputs()["region"])


def active_batch(sess=None):
    sess = sess or session()
    return sess.client("ssm").get_parameter(Name=outputs()["active_batch_param"])["Parameter"]["Value"]
