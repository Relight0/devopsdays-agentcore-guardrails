#!/usr/bin/env python3
"""Revisa credenciales, herramientas y acceso al modelo ANTES del primer apply."""

import argparse
import shutil
import subprocess
import sys

import _bootstrap  # noqa: F401
import boto3
import botocore

from guardrails import config

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def check(label, fn):
    try:
        detail = fn()
        print(f"{GREEN}✓{RESET} {label}{': ' + detail if detail else ''}")
        return True
    except Exception as err:  # noqa: BLE001
        print(f"{RED}✗{RESET} {label}: {err}")
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--model", default="us.anthropic.claude-sonnet-4-6")
    args = p.parse_args()
    sess = boto3.Session(region_name=args.region)

    def terraform():
        tf = shutil.which("terraform")
        if not tf:
            raise RuntimeError("no está en el PATH")
        return subprocess.run([tf, "version"], capture_output=True, text=True).stdout.splitlines()[0]

    def identity():
        ident = sess.client("sts").get_caller_identity()
        return f"{ident['Arn']} (cuenta {ident['Account']})"

    def sdk():
        if "bedrock-agentcore-control" not in sess.get_available_services():
            raise RuntimeError(f"boto3 {boto3.__version__} no trae AgentCore: pip install -U boto3")
        return f"boto3 {boto3.__version__} / botocore {botocore.__version__}"

    def agentcore():
        sess.client("bedrock-agentcore-control").list_gateways(maxResults=1)
        return "list_gateways responde"

    def cloudtrail():
        sess.client("cloudtrail").lookup_events(MaxResults=1)
        return "historial de eventos disponible (orphan-hunter lo usa para buscar al creador)"

    def quota(service, code, default):
        try:
            return int(sess.client("service-quotas").get_service_quota(
                ServiceCode=service, QuotaCode=code)["Quota"]["Value"])
        except Exception:  # noqa: BLE001
            return default

    def demand(kind):
        sc = config.scenario()
        return sum(1 for r in sc["inventory"] if r["type"] == kind) * len(sc["batches"])

    def eips():
        need = demand("elastic-ip")
        addresses = sess.client("ec2").describe_addresses()["Addresses"]
        demo = [a for a in addresses if any(t["Key"] == "demo_batch" for t in a.get("Tags", []))]
        used = len(addresses) - len(demo)
        limit = quota("ec2", "L-0263D0A3", 5)
        if used + need > limit:
            raise RuntimeError(f"el demo necesita {need} IPs elasticas, ya usas {used} y la cuota es {limit}: "
                               "pide aumento en Service Quotas o baja el numero de lotes")
        return f"{used} en uso + {need} del demo <= cuota {limit}"

    def vpcs():
        vpcs_now = sess.client("ec2").describe_vpcs()["Vpcs"]
        demo = any(t["Key"] == "Name" and t["Value"].endswith("-vpc") and "orphan" in t["Value"]
                   for v in vpcs_now for t in v.get("Tags", []))
        used = len(vpcs_now) - (1 if demo else 0)
        limit = quota("vpc", "L-F678F1CE", 5)
        if used + 1 > limit:
            raise RuntimeError(f"ya tienes {used} VPCs y la cuota es {limit}; el demo crea 1")
        return f"{used} en uso + 1 del demo <= cuota {limit}"

    def model():
        resp = sess.client("bedrock-runtime").converse(
            modelId=args.model,
            messages=[{"role": "user", "content": [{"text": "Responde solo: OK"}]}],
            inferenceConfig={"maxTokens": 10},
        )
        text = resp["output"]["message"]["content"][0]["text"].strip()
        return f"{args.model} respondió '{text}' en {resp['metrics']['latencyMs']} ms"

    results = [
        check("terraform", terraform),
        check("credenciales", identity),
        check("SDK", sdk),
        check("AgentCore control plane", agentcore),
        check("CloudTrail", cloudtrail),
        check("cuota de IPs elasticas", eips),
        check("cuota de VPCs", vpcs),
        check("modelo en Bedrock", model),
    ]
    print(f"\n{YELLOW}Revisa también a mano:{RESET} Service Quotas > Amazon Bedrock > cuotas del perfil "
          f"de inferencia en {args.region} (tokens y solicitudes por minuto).")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())