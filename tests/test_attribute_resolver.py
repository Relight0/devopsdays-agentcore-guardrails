import copy
import json
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from conftest import ROOT, load_module

RESOLVER = ROOT / "lambdas" / "attribute_resolver" / "handler.py"
RULES = {"rules": [
    {"tools": ["notify_owner"], "resolver": "ec2_resource_facts", "key_arg": "resource_id",
     "attributes": {"owner": "owner"}, "default": "unknown"},
    {"tools": ["quarantine_resource", "delete_resource"], "resolver": "ec2_resource_facts", "key_arg": "resource_id",
     "attributes": {"environment": "env", "hold": "hold", "in_use": "in_use", "quarantine": "quarantine"},
     "default": "unknown"},
]}


@pytest.fixture
def resolver(monkeypatch):
    monkeypatch.setenv("RESOLVER_CONFIG", json.dumps(RULES))
    return load_module("attribute_resolver", RESOLVER)


def call(resolver, tool, args):
    params = {"name": f"resources___{tool}", "arguments": args}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
    out = resolver.handler({"mcp": {"gatewayRequest": {"body": body}}}, None)
    assert out["interceptorOutputVersion"] == "1.0"
    return out["mcp"]["transformedGatewayRequest"]["body"]["params"]["arguments"]


@pytest.mark.parametrize("trap", ["tmp-migration-copy-0917", "tmp-pre-upgrade-db", "tmp-partner-vpn-ip"])
def test_traps_declared_dev_become_real_prod_with_hold(resolver, seeded, trap):
    """Las trampas: nombre 'tmp-', etiquetas prod + hold. El agente declara dev; mandan las etiquetas."""
    args = call(resolver, "delete_resource", {
        "resource_id": seeded[trap], "environment": "dev", "hold": "false", "in_use": "false",
        "quarantine": "expired", "reason": "limpieza"})
    assert (args["environment"], args["hold"], args["in_use"], args["quarantine"]) == ("prod", "true", "false", "none")
    assert args["reason"] == "limpieza"  # lo demas no se toca


@pytest.mark.parametrize(("name", "expected"), [
    ("test-load-results-0812", "expired"), ("old-jenkins-workspace", "claimed"), ("test-snapshot-loadgen", "released"),
])
def test_quarantine_status_is_derived(resolver, seeded, name, expected):
    assert call(resolver, "delete_resource", {"resource_id": seeded[name]})["quarantine"] == expected


def test_active_quarantine_is_not_expired(resolver, seeded):
    until = (datetime.now(UTC) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = seeded["old-test-sg"]
    boto3.client("ec2", region_name="us-east-1").create_tags(Resources=[rid], Tags=[
        {"Key": "orphan-status", "Value": "quarantined"}, {"Key": "quarantine-until", "Value": until}])
    assert call(resolver, "delete_resource", {"resource_id": rid})["quarantine"] == "active"


def test_in_use_is_real(resolver, seeded):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    subnet = ec2.describe_subnets()["Subnets"][0]["SubnetId"]
    ec2.create_network_interface(SubnetId=subnet, Groups=[seeded["scratch-db-access"]])
    args = call(resolver, "quarantine_resource", {"resource_id": seeded["scratch-db-access"], "in_use": "false"})
    assert args["in_use"] == "true"


def test_notify_is_routed_to_real_owner(resolver, seeded):
    args = call(resolver, "notify_owner", {
        "resource_id": seeded["tmp-partner-vpn-ip"], "owner": "arn:aws:iam::1:user/terraform", "message": "x"})
    assert args["owner"] == "equipo-integraciones"
    assert args["message"] == "x"


def test_missing_owner_tag_becomes_unknown(resolver, seeded):
    assert call(resolver, "notify_owner", {"resource_id": seeded["tmp-debug-eni"], "owner": "alguien"})[
        "owner"] == "unknown"


def test_unknown_unsupported_or_missing_resource_becomes_unknown(resolver, seeded):
    for rid in ("vol-0000000000000000f", "i-0123456789", None):
        args = call(resolver, "delete_resource", {"resource_id": rid, "environment": "dev"})
        assert (args["environment"], args["hold"], args["in_use"], args["quarantine"]) == ("unknown",) * 4


def test_read_only_tools_are_untouched(resolver, seeded):
    assert call(resolver, "list_candidates", {"name_contains": "x"}) == {"name_contains": "x"}


def test_non_tool_calls_are_untouched(resolver):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    out = resolver.handler({"mcp": {"gatewayRequest": {"body": copy.deepcopy(body)}}}, None)
    assert out["mcp"]["transformedGatewayRequest"]["body"] == body


def test_batch_and_string_bodies(resolver, seeded):
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "resources___quarantine_resource",
        "arguments": {"resource_id": seeded["orders-db-data"], "environment": "dev"}}}
    out = resolver.handler({"mcp": {"gatewayRequest": {"body": json.dumps([req])}}}, None)
    args = out["mcp"]["transformedGatewayRequest"]["body"][0]["params"]["arguments"]
    assert (args["environment"], args["hold"]) == ("prod", "true")


def test_legacy_single_tool_rule(monkeypatch, seeded):
    monkeypatch.setenv("RESOLVER_CONFIG", json.dumps({"rules": [{
        "tool": "delete_resource", "resolver": "ec2_resource_facts", "key_arg": "resource_id",
        "attributes": {"environment": "env"}}]}))
    mod = load_module("attribute_resolver_legacy", RESOLVER)
    assert call(mod, "delete_resource", {"resource_id": seeded["orders-db-data"]})["environment"] == "prod"


def test_no_config_is_passthrough(monkeypatch):
    monkeypatch.delenv("RESOLVER_CONFIG", raising=False)
    mod = load_module("attribute_resolver_empty", RESOLVER)
    assert call(mod, "delete_resource", {"resource_id": "vol-1", "environment": "dev"})["environment"] == "dev"
