"""Interceptor generico de REQUEST: reemplaza lo que declara el agente por la verdad del recurso."""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

DELIMITER = "___"


def ec2_resource_facts(key):
    """Hechos reales de un recurso EC2 (volume, snapshot, EIP, SG, ENI)."""
    if not key:
        return {}
    import ec2_inventory  # noqa: PLC0415

    try:
        return ec2_inventory.facts(boto3.client("ec2"), key)
    except ClientError as err:
        LOG.warning("no pude leer %s: %s", key, err)
        return {}


RESOLVERS = {"ec2_resource_facts": ec2_resource_facts}


def _load_rules():
    raw = os.environ.get("RESOLVER_CONFIG", "")
    return (json.loads(raw) if raw else {}).get("rules", [])


def _rule_for(tool_name, rules):
    for rule in rules:
        tools = rule.get("tools") or [rule["tool"]]
        if any(str(tool_name).endswith(DELIMITER + t) for t in tools):
            return rule
    return None


def enrich(body, rules):
    """Devuelve el cuerpo JSON-RPC con los hechos reales; no toca nada que no sea tools/call."""
    if not isinstance(body, dict) or body.get("method") != "tools/call":
        return body
    params = body.get("params") or {}
    rule = _rule_for(params.get("name", ""), rules)
    if rule is None:
        return body

    args = params.setdefault("arguments", {})
    facts = RESOLVERS[rule["resolver"]](args.get(rule["key_arg"]))
    default = rule.get("default", "unknown")

    declared = {arg: args.get(arg) for arg in rule["attributes"]}
    for arg, fact in rule["attributes"].items():
        args[arg] = facts.get(fact, default)

    LOG.info(json.dumps({
        "event": "enriched",
        "tool": params.get("name"),
        "key": args.get(rule["key_arg"]),
        "declared": declared,
        "real": {arg: args[arg] for arg in declared},
        "overridden": any(declared[a] != args[a] for a in declared),
    }))
    return body


def handler(event, context):
    rules = _load_rules()
    request = (event.get("mcp") or {}).get("gatewayRequest") or {}
    body = request.get("body") or {}
    if isinstance(body, str):
        body = json.loads(body)

    body = [enrich(item, rules) for item in body] if isinstance(body, list) else enrich(body, rules)

    return {
        "interceptorOutputVersion": "1.0",
        "mcp": {"transformedGatewayRequest": {"body": body}},
    }
