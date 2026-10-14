"""Ledger en DynamoDB."""

from datetime import UTC, datetime

from boto3.dynamodb.conditions import Key

from . import config


def default_table(sess=None):
    sess = sess or config.session()
    return sess.resource("dynamodb").Table(config.outputs()["trust_ledger_table"])


def _now():
    return datetime.now(UTC).isoformat(timespec="microseconds")


def record_outcome(table, agent_id, tool, outcome, level, detail=""):
    """outcome: success | blocked | error"""
    table.put_item(Item={
        "agent_id": agent_id,
        "ts": _now(),
        "kind": "outcome",
        "tool": tool,
        "outcome": outcome,
        "detail": detail[:500],
        "level": level,
    })


def record_level_change(table, agent_id, old, new, why):
    table.put_item(Item={
        "agent_id": agent_id, "ts": _now(), "kind": "level_change",
        "from_level": old, "to_level": new, "detail": why,
    })


def since_last_change(table, agent_id):
    """Eventos de resultado desde el ultimo cambio de nivel (mas reciente primero)."""
    items, kwargs = [], {
        "KeyConditionExpression": Key("agent_id").eq(agent_id),
        "ScanIndexForward": False,
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    events = []
    for item in items:
        if item["kind"] == "level_change":
            break
        events.append(item)
    return events


def last_level(table, agent_id):
    """Ultimo nivel registrado en el ledger, o None."""
    kwargs = {"KeyConditionExpression": Key("agent_id").eq(agent_id), "ScanIndexForward": False}
    while True:
        resp = table.query(**kwargs)
        for item in resp.get("Items", []):
            if item["kind"] == "level_change":
                return int(item["to_level"])
        if "LastEvaluatedKey" not in resp:
            return None
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def clear(table, agent_id):
    kwargs, deleted = {"KeyConditionExpression": Key("agent_id").eq(agent_id)}, 0
    with table.batch_writer() as batch:
        while True:
            resp = table.query(**kwargs)
            for item in resp.get("Items", []):
                batch.delete_item(Key={"agent_id": item["agent_id"], "ts": item["ts"]})
                deleted += 1
            if "LastEvaluatedKey" not in resp:
                return deleted
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
