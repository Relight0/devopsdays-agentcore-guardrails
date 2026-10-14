"""Cliente MCP mínimo (JSON-RPC sobre HTTP) firmado con SigV4 para un Gateway AWS_IAM."""

import itertools
import json

import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

PROTOCOL_VERSION = "2025-06-18"
# Solo una negacion del Policy Engine cuenta como "policy"; un AccessDenied o un 403 de SigV4 no.
DENY_MARKERS = ("-32002", "tool execution denied", "policy enforcement")


class GatewayError(RuntimeError):
    def __init__(self, status, text):
        super().__init__(f"HTTP {status}: {text[:500]}")
        self.status = status
        self.text = text


class ToolResult:
    """Resultado normalizado de tools/call."""

    def __init__(self, ok, text, layer=None, raw=None):
        self.ok = ok
        self.text = text
        self.layer = layer  # policy | lambda | iam | None
        self.raw = raw

    @property
    def blocked(self):
        return self.layer is not None


class GatewayClient:
    def __init__(self, url, session):
        self.url = url
        self.session = session
        self.region = session.region_name
        self._ids = itertools.count(1)
        self.mcp_session_id = None

    def _post(self, payload):
        body = json.dumps(payload)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.mcp_session_id:
            headers["Mcp-Session-Id"] = self.mcp_session_id

        creds = self.session.get_credentials().get_frozen_credentials()
        req = AWSRequest(method="POST", url=self.url, data=body, headers=headers)
        SigV4Auth(creds, "bedrock-agentcore", self.region).add_auth(req)

        resp = requests.post(self.url, data=body, headers=dict(req.headers), timeout=90)
        self.mcp_session_id = resp.headers.get("Mcp-Session-Id", self.mcp_session_id)

        if "id" not in payload:  # notificación: no hay respuesta
            return None
        if resp.status_code >= 400:
            raise GatewayError(resp.status_code, resp.text)
        if "text/event-stream" in resp.headers.get("Content-Type", ""):
            return _parse_sse(resp.text, payload["id"])
        return resp.json()

    def _rpc(self, method, params=None):
        return self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or {}})

    def initialize(self):
        resp = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agentcore-guardrails", "version": "1.0.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return resp

    def list_tools(self):
        tools, cursor = [], None
        while True:
            resp = self._rpc("tools/list", {"cursor": cursor} if cursor else {})
            if "error" in resp:
                raise GatewayError(200, json.dumps(resp["error"]))
            result = resp.get("result", {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name, arguments):
        try:
            resp = self._rpc("tools/call", {"name": name, "arguments": arguments})
        except GatewayError as err:
            layer = "policy" if _looks_denied(err.text) else None
            return ToolResult(False, str(err), layer=layer, raw=err.text)

        if "error" in resp:
            text = json.dumps(resp["error"], ensure_ascii=False)
            return ToolResult(False, text, layer="policy" if _looks_denied(text) else None, raw=resp)

        result = resp.get("result", {})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            return ToolResult(False, text, layer="policy" if _looks_denied(text) else None, raw=resp)

        payload = _try_json(text)
        if isinstance(payload, dict) and payload.get("status") == "refused":
            return ToolResult(False, text, layer=payload.get("layer", "lambda"), raw=resp)
        if isinstance(payload, dict) and payload.get("status") == "error":
            return ToolResult(False, text, raw=resp)
        return ToolResult(True, text, raw=resp)


def _looks_denied(text):
    low = (text or "").lower()
    return any(m in low for m in DENY_MARKERS)


def _try_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _parse_sse(text, request_id):
    last = None
    for line in text.splitlines():
        if line.startswith("data:"):
            data = _try_json(line[5:].strip())
            if isinstance(data, dict):
                last = data
                if data.get("id") == request_id:
                    return data
    if last is None:
        raise GatewayError(200, f"Respuesta SSE sin datos: {text[:300]}")
    return last