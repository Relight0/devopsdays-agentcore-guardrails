#!/usr/bin/env python3
"""Corre el agente contra un carril del Gateway."""

import argparse
import sys

import _bootstrap  # noqa: F401

from guardrails import agent, config


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instruction", nargs="?", help="Instruccion para el agente.")
    parser.add_argument("--act", help="Usa el carril y la instruccion del acto (definidos en scenario.json).")
    parser.add_argument("--lane", choices=["ungoverned", "governed"], help="Carril (sobrescribe el del acto).")
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--no-record", action="store_true", 
                        help="No escribir en el ledger (los actos 1 y 2 nunca escriben).")
    args = parser.parse_args()

    try:
        acts = config.scenario()["acts"]
        if args.act and args.act not in acts:
            parser.error(f"Acto desconocido: {args.act}. Disponibles: {', '.join(sorted(acts))}")
        act = acts.get(args.act, {})
        lane = args.lane or act.get("lane") or "governed"
        instruction = args.instruction or act.get("instruction")
        if not instruction:
            parser.error("Da una instruccion o usa --act.")
        record = act.get("record", True) and not args.no_record
        return agent.run(lane, instruction, args.max_turns, record=record)
    except config.ConfigError as err:
        agent.say("red", str(err))
        return 2


if __name__ == "__main__":
    sys.exit(main())
