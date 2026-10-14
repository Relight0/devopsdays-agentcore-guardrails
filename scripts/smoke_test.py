#!/usr/bin/env python3
"""Prueba de plomeria sin LLM. No borra nada que no deba."""

import json
import sys

import _bootstrap  # noqa: F401
import ec2_inventory as inv

from guardrails import config
from guardrails.mcp_client import GatewayClient

OK, FAIL, WARN = "\033[32mOK\033[0m", "\033[31mFALLA\033[0m", "\033[33mAVISO\033[0m"
TARGET = "resources"


def find_tool(tools, name):
    return next((t for t in tools if t.endswith(f"___{name}")), None)


def main():
    try:
        out = config.outputs()
        sc = config.scenario()
    except config.ConfigError as err:
        print(err)
        return 2
    sess = config.session()
    level = config.trust_level()
    print(f"lote activo: {config.active_batch(sess)} | nivel: {level} | modo: {out['governed_mode']}")
    failures = 0
    ids = {}

    for lane in ("ungoverned", "governed"):
        print(f"\n--- carril {lane}")
        gw = GatewayClient(out["gateway_urls"][lane], sess)
        gw.initialize()
        tools = [t["name"] for t in gw.list_tools()]
        print(f"tools/list: {tools}")
        name = find_tool(tools, "list_candidates")
        if not name:
            print(f"{FAIL} no aparece list_candidates")
            failures += 1
            continue
        res = gw.call_tool(name, {})
        if not res.ok:
            print(f"{FAIL} list_candidates: {res.text}")
            failures += 1
            continue
        data = json.loads(res.text)
        kinds = sorted({r["type"] for r in data["resources"]})
        print(f"{OK} list_candidates devolvio {data['count']} recursos de {len(kinds)} tipos: {', '.join(kinds)}")
        if set(kinds) != set(inv.TYPES):
            print(f"{WARN} faltan tipos: {sorted(set(inv.TYPES) - set(kinds))}")
        ids = {r["name"]: r["resource_id"] for r in data["resources"]}

    traps = [t for t in sc["traps"] if t in ids]
    if not traps:
        print(f"\n{FAIL} no hay trampas en el lote activo (ya las borro el Acto 1? cambia de lote o reaplica)")
        return 1

    gw = GatewayClient(out["gateway_urls"]["governed"], sess)
    gw.initialize()

    print("\n--- CloudTrail")
    res = gw.call_tool(f"{TARGET}___find_probable_owner", {"resource_id": ids[traps[0]]})
    data = json.loads(res.text) if res.ok else {}
    if data.get("creator", "unknown") == "unknown":
        print(f"{WARN} CloudTrail aun no muestra la creacion (normal los primeros ~15 min): {res.text[:200]}")
    else:
        print(f"{OK} creador segun CloudTrail: {data['creator']}")

    print("\n--- interceptor: aviso con dueno falso")
    res = gw.call_tool(f"{TARGET}___notify_owner", {
        "resource_id": ids[traps[0]], "owner": "dueno-inventado", "message": "[smoke test] ignorar este aviso"})
    routed = (json.loads(res.text) if res.ok else {}).get("routed_to")
    if routed and routed != "dueno-inventado":
        print(f"{OK} el interceptor enruto al dueno real: {routed}")
    else:
        print(f"{FAIL} no se corrigio el dueno ({res.text[:200]})")
        failures += 1

    print("\n--- Cedar: eliminar cada trampa declarando environment=dev")
    if level < 2:
        print(f"{WARN} en nivel {level} delete_resource no tiene politica: la negacion es por defecto, "
              "no por el dato real. Para probar interceptor + Cedar: make level L=2")
    verdicts = {
        "policy": f"{OK} lo detuvo Cedar",
        "lambda": f"{WARN} lo detuvo la Lambda: Cedar no vio el dato real -> revisar interceptor (plan B activo)",
        "iam": f"{WARN} solo IAM lo detuvo: revisar interceptor y politica",
    }
    for trap in traps:
        res = gw.call_tool(f"{TARGET}___delete_resource", {
            "resource_id": ids[trap], "environment": "dev", "hold": "false", "in_use": "false",
            "quarantine": "expired", "reason": "smoke test"})
        if res.ok:
            print(f"{FAIL} {trap}: SE ELIMINO. Revisa la politica y el rol del carril gobernado")
            failures += 1
        elif res.layer in verdicts:
            print(f"{trap:26} {verdicts[res.layer]}")
        else:
            print(f"{FAIL} {trap}: error no clasificado ({res.text[:200]})")
            failures += 1

    print("\nresultado:", OK if not failures else f"{FAIL} ({failures})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
