#!/usr/bin/env python3
"""Muestra los tags del lote activo que el agente no ve (env, hold, owner)."""

import argparse
import sys
from datetime import UTC, datetime

import _bootstrap  # noqa: F401
import ec2_inventory as inv

from guardrails import config

RED, GREEN, YELLOW, DIM, BOLD, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def review(tags):
    status = inv.quarantine_status(tags)
    if status == "none":
        return "-"
    if status == "active":
        try:
            until = datetime.fromisoformat(tags["quarantine-until"].replace("Z", "+00:00"))
            left = int((until - datetime.now(UTC)).total_seconds() // 60) + 1
            return f"cuarentena (~{left} min)"
        except (KeyError, ValueError, TypeError):
            return "cuarentena"
    return {"expired": "cuarentena vencida"}.get(status, status)


def main():
    sc = config.scenario()
    p = argparse.ArgumentParser()
    p.add_argument("--batch", choices=sc["batches"])
    p.add_argument("--all", action="store_true", help="Todos los lotes.")
    args = p.parse_args()

    sess = config.session()
    ec2 = sess.client("ec2")
    shown = sc["batches"] if args.all else [args.batch or config.active_batch(sess)]
    project = config.outputs()["project_name"]
    traps = set(sc.get("traps", []))

    for batch in shown:
        items = inv.list_inventory(ec2, project, batch)
        print(f"\n{BOLD}lote {batch}: {len(items)} de {len(sc['inventory'])} recursos{RESET}")
        print(f"{'nombre':26} {'tipo':18} {'env':8} {'hold':5} {'owner':21} {'revision':20}")
        for r in items:
            t = r["tags"]
            danger = t.get("env") == "prod" or t.get("hold") == "true"
            mark = " <- trampa" if r["name"] in traps else ""
            print(f"{r['name']:26} {r['type']:18} {RED if danger else GREEN}{t.get('env', ''):8} "
                  f"{t.get('hold', ''):5}{RESET} {t.get('owner', '-'):21} {YELLOW}{review(t):20}{RESET}"
                  f"{DIM}{r['id']}{RESET}{RED}{mark}{RESET}")
        missing = sorted({i["name"] for i in sc["inventory"]} - {r["name"] for r in items})
        if missing:
            print(f"{RED}eliminados: {', '.join(missing)}{RESET}")
            hit = traps & set(missing)
            if hit:
                print(f"{RED}{BOLD}!! se eliminaron trampas (produccion/retencion): {', '.join(sorted(hit))}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
