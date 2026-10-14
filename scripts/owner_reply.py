#!/usr/bin/env python3
"""Simula la respuesta del dueno a un aviso del agente (el humano en el circuito)."""

import argparse
import sys

import _bootstrap  # noqa: F401
import ec2_inventory as inv

from guardrails import config, ledger

ANSWERS = {
    "release": ("released", "confirmed", "el dueno confirmo que se puede eliminar"),
    "claim": ("claimed", "rejected", "el dueno reclamo el recurso"),
}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help="Nombre del recurso (etiqueta Name) en el lote activo.")
    p.add_argument("answer", choices=sorted(ANSWERS))
    p.add_argument("--no-record", action="store_true", help="Solo etiquetar, sin escribir en el ledger.")
    args = p.parse_args()

    status, outcome, detail = ANSWERS[args.answer]
    sess = config.session()
    ec2 = sess.client("ec2")
    batch = config.active_batch(sess)
    found = [r for r in inv.list_inventory(ec2, config.outputs()["project_name"], batch) if r["name"] == args.name]
    if not found:
        print(f"No encontre '{args.name}' en el lote {batch} (ya lo elimino el agente?).")
        return 1
    res = found[0]

    ec2.create_tags(Resources=[res["id"]], Tags=[{"Key": "orphan-status", "Value": status}])
    print(f"{args.name} ({res['type']} {res['id']}): orphan-status={status}")

    if not args.no_record:
        ledger.record_outcome(ledger.default_table(sess), config.agent_id(), f"owner_reply:{args.name}",
                              outcome, config.trust_level(), detail)
        print(f"ledger: {outcome} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
