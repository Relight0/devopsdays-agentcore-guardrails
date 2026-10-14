#!/usr/bin/env python3
"""Escalera de confianza: status | evaluate [--approve | --ci] | set N | sync | reset."""

import argparse
import os
import sys
from collections import Counter

import _bootstrap  # noqa: F401

from guardrails import config, ladder, ledger


def github_output(**values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in values.items())


def status(table, agent_id):
    level = config.trust_level()
    events = ledger.since_last_change(table, agent_id)
    good, bad = ladder.tally(events, ladder.promote_on(), ladder.demote_on())
    counts = Counter(e["outcome"] for e in events)
    print(f"nivel actual: {level} ({ladder.label(level)})")
    print(f"desde el ultimo cambio: {dict(counts) or 'sin eventos'}")
    print(f"  a favor ({'/'.join(ladder.promote_on())}): {good} de {ladder.promote_after()} necesarias")
    print(f"  en contra ({'/'.join(ladder.demote_on())}): {bad}")
    for e in events[:12]:
        print(f"  {e['ts'][:19]} {e['outcome']:10} {e['tool']}")
    return level, events


def evaluate(table, agent_id, approve, ci):
    level, events = status(table, agent_id)
    lo, hi = ladder.bounds()
    d = ladder.decide(level, events, ladder.promote_after(), lo, hi, approve=approve,
                      promote_on=ladder.promote_on(), demote_on=ladder.demote_on())
    github_output(action=d.action, level=d.new_level, reason=d.reason)

    if d.action in ("demote", "promote"):
        return ladder.apply_level(level, d.new_level, d.reason, table, agent_id)
    if d.action == "propose":
        if ci:
            # En CI la promocion se aprueba como Pull Request; el apply corre al hacer merge.
            return ladder.apply_level(level, d.new_level, d.reason, table, agent_id, apply=False)
        print(f"\nPROPUESTA: subir a nivel {d.new_level} ({ladder.label(d.new_level)}). "
              "Requiere aprobacion humana: corre de nuevo con --approve.")
        return 0
    print(d.reason + ".")
    return 0


def sync(table, agent_id):
    level = config.trust_level()
    recorded = ledger.last_level(table, agent_id)
    if recorded is None or recorded != level:
        ledger.record_level_change(table, agent_id, recorded, level, "aplicado desde terraform.tfvars")
        print(f"ledger sincronizado: {recorded} -> {level}")
    else:
        print(f"ledger al dia en nivel {level}")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    ev = sub.add_parser("evaluate")
    mode = ev.add_mutually_exclusive_group()
    mode.add_argument("--approve", action="store_true", help="aplica el ascenso propuesto")
    mode.add_argument("--ci", action="store_true", help="escribe el ascenso en terraform.tfvars sin aplicarlo")
    st = sub.add_parser("set")
    st.add_argument("level", type=int)
    sub.add_parser("sync")
    sub.add_parser("reset")
    args = p.parse_args()

    try:
        agent_id = config.agent_id()
        table = ledger.default_table()
        if args.cmd == "status":
            status(table, agent_id)
            return 0
        if args.cmd == "evaluate":
            return evaluate(table, agent_id, args.approve, args.ci)
        if args.cmd == "set":
            lo, hi = ladder.bounds()
            if not lo <= args.level <= hi:
                p.error(f"El nivel debe estar entre {lo} y {hi}.")
            old = config.trust_level()
            return 0 if old == args.level else ladder.apply_level(
                old, args.level, "fijado manualmente", table, agent_id)
        if args.cmd == "sync":
            return sync(table, agent_id)
        if args.cmd == "reset":
            print(f"eventos borrados: {ledger.clear(table, agent_id)}")
            return 0
    except config.ConfigError as err:
        print(err)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
