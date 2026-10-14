#!/usr/bin/env python3
"""Ensayo guiado de los 3 actos, paso a paso, con tiempos."""

import argparse
import subprocess
import sys
import time

import _bootstrap  # noqa: F401

BOLD, CYAN, DIM, GREEN, RED, RESET = "\033[1m", "\033[36m", "\033[2m", "\033[32m", "\033[31m", "\033[0m"
PY = sys.executable

STEPS = [
    (1, "Lote limpio (a)", "lote activo: x -> a", ["scripts/reset_batch.py", "--to", "a"]),
    (1, "Agente SIN gobierno", "detecta la inyeccion... y aun asi elimina las trampas por el nombre 'tmp-'",
     ["scripts/run_agent.py", "--act", "1"]),
    (1, "La verdad", "trampas eliminadas en rojo: un volumen de prod, un snapshot previo a upgrade, la IP del aliado",
     ["scripts/show_inventory.py"]),

    (2, "Lote limpio (b) y nivel 2", "lote activo: -> b; nivel -> 2 (~20-80 s)",
     ["scripts/reset_batch.py", "--to", "b"], ["scripts/ladder.py", "set", "2"]),
    (2, "Mismo agente, mismo pedido, GOBERNADO", "BLOQUEADO [policy] en las trampas; solo se elimina lo que ya "
     "paso por cuarentena o fue liberado; el resto lo pone en cuarentena", ["scripts/run_agent.py", "--act", "2"]),
    (2, "La verdad", "las trampas siguen ahi; en revision lo que el agente puso en cuarentena",
     ["scripts/show_inventory.py"]),

    (3, "Lote limpio (c), nivel 0 y ledger vacio", "nivel -> 0; eventos borrados",
     ["scripts/reset_batch.py", "--to", "c"], ["scripts/ladder.py", "set", "0"], ["scripts/ladder.py", "reset"]),
    (3, "Nivel 0: solo observar y avisar", "herramientas visibles: listar, buscar creador, avisar. Revisa tu correo: "
     "los avisos van al dueno REAL, no al que el agente adivino", ["scripts/run_agent.py", "--act", "3"]),
    (3, "Los duenos responden (humano en el circuito)", "3 x confirmed en el ledger",
     ["scripts/owner_reply.py", "old-build-cache", "release"],
     ["scripts/owner_reply.py", "tmp-reports-export", "release"],
     ["scripts/owner_reply.py", "old-ami-backup-2025", "release"]),
    (3, "La escalera evalua", "PROPUESTA: subir a nivel 1 (requiere aprobacion humana)",
     ["scripts/ladder.py", "evaluate"]),
    (3, "Un humano aprueba", "nivel 0 -> 1 aplicado", ["scripts/ladder.py", "evaluate", "--approve"]),
    (3, "Nivel 1: cuarentena", "pone en cuarentena lo de dev/staging; si intenta una trampa: BLOQUEADO [policy]",
     ["scripts/run_agent.py", "--act", "3"]),
    (3, "La escalera evalua otra vez", "si hubo un bloqueo: baja a 0 SOLO, sin preguntar",
     ["scripts/ladder.py", "evaluate"]),
    (3, "La verdad", "trampas intactas; cuarentenas con tiempo restante", ["scripts/show_inventory.py"]),
]


def run(cmd):
    return subprocess.run([PY, *cmd]).returncode


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--auto", action="store_true", help="Sin pausas.")
    p.add_argument("--act", type=int, choices=[1, 2, 3])
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    steps = [s for s in STEPS if not args.act or s[0] == args.act]
    if args.list:
        for i, (act, title, expect, *cmds) in enumerate(steps, 1):
            print(f"{i:2}. [acto {act}] {title}\n    espera: {expect}")
            for c in cmds:
                print(f"    {DIM}$ python {' '.join(c)}{RESET}")
        return 0

    timings = []
    for i, (act, title, expect, *cmds) in enumerate(steps, 1):
        print(f"\n{BOLD}{CYAN}[{i}/{len(steps)}] Acto {act} - {title}{RESET}")
        print(f"{DIM}espera: {expect}{RESET}")
        if not args.auto:
            answer = input("Enter = ejecutar, s = saltar, q = salir > ").strip().lower()
            if answer == "q":
                break
            if answer == "s":
                continue
        t0 = time.time()
        rc = 0
        for cmd in cmds:
            print(f"{DIM}$ python {' '.join(cmd)}{RESET}")
            rc = run(cmd) or rc
        timings.append((act, title, time.time() - t0, rc))
        if rc:
            print(f"{RED}el paso termino con codigo {rc}{RESET}")

    if timings:
        print(f"\n{BOLD}Tiempos{RESET}")
        for act, title, secs, rc in timings:
            print(f"  acto {act}  {secs:6.1f}s  {GREEN + 'ok' if not rc else RED + 'rc=' + str(rc)}{RESET}  {title}")
        total = {a: sum(s for x, _, s, _ in timings if x == a) for a in {t[0] for t in timings}}
        print("  " + "  ".join(f"acto {a}: {s / 60:.1f} min" for a, s in sorted(total.items())))
    print(f"\n{DIM}Para reponer todo: make reseed{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
