"""Escalera de confianza: sube lento y con humano; baja rapido y sola."""

import os
import re
import subprocess
import time
from dataclasses import dataclass

from . import config, ledger

LADDER_TARGET = "module.ladder.aws_bedrockagentcore_policy.this"
DEFAULT_PROMOTE_ON = ("success",)
DEFAULT_DEMOTE_ON = ("blocked",)


@dataclass(frozen=True)
class Decision:
    action: str  # demote | promote | propose | hold | floor
    new_level: int
    reason: str


def tally(events, promote_on=DEFAULT_PROMOTE_ON, demote_on=DEFAULT_DEMOTE_ON):
    good = sum(1 for e in events if e["outcome"] in promote_on)
    bad = sum(1 for e in events if e["outcome"] in demote_on)
    return good, bad


def decide(level, events, promote_after, min_level, max_level, approve=False,
           promote_on=DEFAULT_PROMOTE_ON, demote_on=DEFAULT_DEMOTE_ON):
    good, bad = tally(events, promote_on, demote_on)
    if bad:
        if level > min_level:
            why = f"{bad} evento(s) en contra ({'/'.join(demote_on)}): degradacion automatica"
            return Decision("demote", level - 1, why)
        return Decision("floor", level, "ya esta en el nivel minimo; se mantiene")
    if good >= promote_after and level < max_level:
        if approve:
            return Decision("promote", level + 1, f"{good} evidencias ({'/'.join(promote_on)}); aprobado por humano")
        return Decision("propose", level + 1, f"{good} evidencias ({'/'.join(promote_on)}): requiere aprobacion humana")
    return Decision("hold", level, "sin cambios")


def bounds():
    levels = sorted(int(k) for k in config.ladder_config()["levels"])
    return levels[0], levels[-1]


def promote_after():
    env = os.environ.get("LADDER_PROMOTE_AFTER")
    return int(env) if env else int(config.ladder_config()["promote_after"])


def promote_on():
    return tuple(config.ladder_config().get("promote_on", DEFAULT_PROMOTE_ON))


def demote_on():
    return tuple(config.ladder_config().get("demote_on", DEFAULT_DEMOTE_ON))


def label(level):
    return config.ladder_config()["levels"][str(level)]["label"]


def write_level(level):
    path = config.tfvars_path()
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(r"^trust_level\s*=.*$", f"trust_level = {level}", text, count=1, flags=re.M)
    if not count:
        raise config.ConfigError(f"No encuentro trust_level en {path}")
    path.write_text(new, encoding="utf-8")


def terraform_apply():
    return subprocess.run([
        "terraform", f"-chdir={config.scenario_dir()}", "apply", "-auto-approve",
        "-compact-warnings", "-lock-timeout=5m", "-refresh=false", f"-target={LADDER_TARGET}",
    ]).returncode


def apply_level(old, new, why, table, agent_id, apply=True):
    write_level(new)
    print(f"nivel {old} -> {new} ({label(new)}): {why}")
    if not apply:
        return 0
    t0 = time.time()
    rc = terraform_apply()
    if rc != 0:
        print("terraform apply fallo; terraform.tfvars quedo en el nivel nuevo, revisa antes de seguir.")
        return rc
    ledger.record_level_change(table, agent_id, old, new, why)
    print(f"aplicado en {time.time() - t0:.0f}s; el Gateway puede tardar unos segundos mas en reflejarlo.")
    return 0
