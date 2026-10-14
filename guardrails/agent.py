"""Agente de ejemplo: Bedrock Converse + herramientas MCP del Gateway elegido."""

import json
import time

from . import config, ledger
from .mcp_client import GatewayClient

MAX_TOKENS = 8192

COLORS = {"dim": "\033[2m", "red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
          "cyan": "\033[36m", "bold": "\033[1m", "reset": "\033[0m"}


def say(color, text):
    print(f"{COLORS[color]}{text}{COLORS['reset']}", flush=True)


def to_bedrock_tools(mcp_tools):
    return [{
        "toolSpec": {
            "name": t["name"],
            "description": t.get("description") or t["name"],
            "inputSchema": {"json": t.get("inputSchema") or {"type": "object", "properties": {}}},
        }
    } for t in mcp_tools]


def short(text, n=300):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n] + "…"


def classify(result):
    if result.ok:
        return "success"
    return "blocked" if result.blocked else "error"


def run(lane, instruction, max_turns=24, record=True):
    out = config.outputs()
    sc = config.scenario()
    agent_id = sc["agent_id"]
    sess = config.session()
    gateway = GatewayClient(out["gateway_urls"][lane], sess)
    bedrock = sess.client("bedrock-runtime")
    table = ledger.default_table(sess) if record and lane == "governed" else None
    level = config.trust_level()

    header = f"carril={lane}  modelo={out['model_id']}"
    if lane == "governed":
        header += f"  modo={out['governed_mode']}  nivel={level}  ledger={'si' if table is not None else 'no'}"
    say("bold", f"\n== {agent_id} | {header}")
    say("cyan", f"> {instruction}\n")

    gateway.initialize()
    mcp_tools = gateway.list_tools()
    say("dim", "herramientas visibles: " + ", ".join(t["name"] for t in mcp_tools))
    if not mcp_tools:
        say("yellow", "El Gateway no expuso herramientas para este principal.")
        return 1

    messages = [{"role": "user", "content": [{"text": instruction}]}]
    tool_config = {"tools": to_bedrock_tools(mcp_tools)}
    tally = {"success": 0, "blocked": 0, "error": 0}

    for _ in range(max_turns):
        t0 = time.time()
        resp = bedrock.converse(
            modelId=out["model_id"],
            system=[{"text": sc["system_prompt"]}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={"maxTokens": MAX_TOKENS},
        )
        msg = resp["output"]["message"]
        messages.append(msg)
        say("dim", f"(modelo {time.time() - t0:.1f}s, stop={resp['stopReason']})")

        tool_results = []
        for block in msg["content"]:
            if "text" in block and block["text"].strip():
                print(block["text"].strip())
            if "toolUse" not in block:
                continue

            use = block["toolUse"]
            say("cyan", f"→ {use['name']} {json.dumps(use['input'], ensure_ascii=False)}")
            result = gateway.call_tool(use["name"], use["input"])
            outcome = classify(result)

            if outcome == "success":
                say("green", f"  ✓ {short(result.text)}")
            elif outcome == "blocked":
                say("red", f"  ✗ BLOQUEADO [{result.layer}] {short(result.text)}")
            else:
                say("yellow", f"  ! error {short(result.text)}")
            tally[outcome] += 1

            # El ledger lo escribe el harness, nunca el modelo.
            if table is not None:
                ledger.record_outcome(table, agent_id, use["name"], outcome, level, result.text)

            tool_results.append({"toolResult": {
                "toolUseId": use["toolUseId"],
                "content": [{"text": result.text or "(sin contenido)"}],
                "status": "success" if result.ok else "error",
            }})

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
            continue
        if resp["stopReason"] == "max_tokens":
            messages.append({"role": "user", "content": [{"text": "Continua donde quedaste."}]})
            continue
        break
    else:
        say("yellow", f"Se alcanzo el maximo de {max_turns} turnos.")

    say("bold", f"\nresumen: {tally['success']} ok, {tally['blocked']} bloqueadas, {tally['error']} errores")
    return 0
