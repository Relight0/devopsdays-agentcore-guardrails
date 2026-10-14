#!/usr/bin/env python3
"""Cambia el lote de recursos visible para el agente (reinicio entre actos en 1 s)."""

import argparse
import subprocess
import sys

import _bootstrap  # noqa: F401

from guardrails import config


def main():
    batches = config.scenario()["batches"]
    p = argparse.ArgumentParser()
    p.add_argument("--to", choices=batches)
    p.add_argument("--reseed", action="store_true")
    args = p.parse_args()

    if args.reseed:
        return subprocess.run(
            ["terraform", f"-chdir={config.scenario_dir()}", "apply", "-auto-approve"]).returncode

    sess = config.session()
    current = config.active_batch(sess)
    target = args.to or batches[(batches.index(current) + 1) % len(batches)]
    sess.client("ssm").put_parameter(Name=config.outputs()["active_batch_param"], Value=target, Overwrite=True)
    print(f"lote activo: {current} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
