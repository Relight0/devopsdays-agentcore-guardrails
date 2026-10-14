import json

import pytest

from guardrails.mcp_client import GatewayClient, GatewayError, _parse_sse

DENIED = {"code": -32002, "message": "Tool Execution Denied: Tool call not allowed due to policy enforcement "
                                     "[No policy applies to the request (denied by default).]"}


class FakeSession:
    region_name = "us-east-1"


def client(monkeypatch, response=None, error=None):
    gw = GatewayClient("https://example.invalid/mcp", FakeSession())

    def fake_rpc(method, params=None):
        if error:
            raise error
        return response

    monkeypatch.setattr(gw, "_rpc", fake_rpc)
    return gw


def text_result(payload, is_error=False):
    return {"result": {"isError": is_error, "content": [{"type": "text", "text": json.dumps(payload)}]}}


def test_success(monkeypatch):
    res = client(monkeypatch, text_result({"status": "deleted"})).call_tool("t", {})
    assert res.ok and not res.blocked


def test_policy_denial_is_blocked_by_policy(monkeypatch):
    res = client(monkeypatch, {"error": DENIED}).call_tool("t", {})
    assert not res.ok and res.layer == "policy"


def test_http_403_without_policy_denial_is_not_a_block(monkeypatch):
    """Un 403 de SigV4 es un problema de credenciales, no una decision de Cedar."""
    res = client(monkeypatch, error=GatewayError(403, "forbidden")).call_tool("t", {})
    assert not res.ok and not res.blocked


def test_aws_access_denied_inside_tool_is_not_a_block(monkeypatch):
    res = client(monkeypatch, text_result("AccessDenied: not authorized to perform sns:Publish",
                                          is_error=True)).call_tool("t", {})
    assert not res.ok and not res.blocked


def test_lambda_refusal_keeps_its_layer(monkeypatch):
    res = client(monkeypatch, text_result({"status": "refused", "layer": "iam"})).call_tool("t", {})
    assert not res.ok and res.layer == "iam"


def test_lambda_refusal_defaults_to_lambda_layer(monkeypatch):
    res = client(monkeypatch, text_result({"status": "refused"})).call_tool("t", {})
    assert res.layer == "lambda"


def test_tool_error_is_not_a_block(monkeypatch):
    res = client(monkeypatch, text_result({"status": "error", "message": "no existe"})).call_tool("t", {})
    assert not res.ok and not res.blocked


def test_iserror_with_gateway_denial_is_policy(monkeypatch):
    res = client(monkeypatch, text_result("Tool Execution Denied: Tool call not allowed due to policy enforcement",
                                          is_error=True)).call_tool("t", {})
    assert res.layer == "policy"


def test_unclassified_http_error_is_not_a_block(monkeypatch):
    res = client(monkeypatch, error=GatewayError(500, "boom")).call_tool("t", {})
    assert not res.ok and not res.blocked


def test_parse_sse_picks_matching_id():
    sse = 'data: {"id": 1, "result": {"a": 1}}\n\ndata: {"id": 2, "result": {"b": 2}}\n'
    assert _parse_sse(sse, 2)["result"] == {"b": 2}


def test_parse_sse_without_data_raises():
    with pytest.raises(GatewayError):
        _parse_sse("event: ping\n", 1)
