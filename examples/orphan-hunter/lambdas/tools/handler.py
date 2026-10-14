"""Herramientas MCP de orphan-hunter detras de AgentCore Gateway."""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

import boto3
import ec2_inventory as inv
from botocore.config import Config
from botocore.exceptions import ClientError

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

PROJECT = os.environ["PROJECT"]
LANE = os.environ["LANE"]
AGENT_ID = os.environ.get("AGENT_ID", "orphan-hunter")
ACTIVE_BATCH_PARAM = os.environ["ACTIVE_BATCH_PARAM"]
TOPIC_ARN = os.environ["TOPIC_ARN"]
QUARANTINE_MINUTES = int(os.environ.get("QUARANTINE_MINUTES", "3"))
DELIMITER = "___"
NON_PROD = ("dev", "staging")
NO_OWNER = "plataforma (sin dueno registrado)"

ec2 = boto3.client("ec2")
ssm = boto3.client("ssm")
sns = boto3.client("sns")
# LookupEvents: 2 req/s por cuenta.
cloudtrail = boto3.client("cloudtrail", config=Config(retries={"mode": "standard", "max_attempts": 5}))

quarantine_status = inv.quarantine_status


def _tool_name(event, context):
    name = None
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None) if client_context else None
    if custom:
        name = custom.get("bedrockAgentCoreToolName")
    name = name or event.get("__tool")
    return name.split(DELIMITER)[-1] if name else None


def _active_batch():
    return ssm.get_parameter(Name=ACTIVE_BATCH_PARAM)["Parameter"]["Value"]


def _resource(resource_id):
    """Recurso del inventario activo, o (None, mensaje de error)."""
    if not inv.resource_type(resource_id):
        return None, f"Tipo de recurso no soportado: {resource_id}."
    res = inv.describe(ec2, resource_id)
    if not res:
        return None, f"No existe el recurso {resource_id}."
    if res["tags"].get("project") != PROJECT or res["tags"].get("demo_batch") != _active_batch():
        return None, f"{resource_id} no pertenece al inventario activo."
    return res, None


def _subject(text):
    """SNS exige asunto ASCII, sin saltos de linea y de menos de 100 caracteres."""
    return " ".join(text.encode("ascii", "ignore").decode().split())[:99]


def _refused(layer, message):
    return {"status": "refused", "layer": layer, "message": message}


def _iam_denied(err):
    return err.response["Error"]["Code"] in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException")


def _review_problem(res, allowed_status):
    """Plan B del carril gobernado: devuelve el motivo del rechazo, o None."""
    tags = res["tags"]
    env, hold, status = tags.get("env", "unknown"), tags.get("hold", "unknown"), inv.quarantine_status(tags)
    if env not in NON_PROD:
        return f"el recurso es de {env}"
    if hold != "false":
        return "el recurso tiene retencion (hold)"
    if res["in_use"]:
        return "el recurso esta en uso"
    if status not in allowed_status:
        return f"estado de revision '{status}' no lo permite"
    return None


def list_candidates(args):
    kinds = [args["resource_type"]] if args.get("resource_type") in inv.TYPES else None
    contains = (args.get("name_contains") or "").lower()
    items = []
    for res in inv.list_inventory(ec2, PROJECT, _active_batch(), kinds):
        if res["in_use"] or (contains and contains not in res["name"].lower()):
            continue
        # env, hold y owner no se exponen, como en muchos inventarios reales.
        items.append({
            "resource_id": res["id"],
            "type": res["type"],
            "name": res["name"],
            "notes": res["tags"].get("notes", ""),
            "detail": res["detail"],
            "created": res["created"],
            "review_status": inv.quarantine_status(res["tags"]),
        })
    return {"count": len(items), "resources": items}


def _lookup_creator(resource_id):
    return inv.lookup_creator(cloudtrail, resource_id)


def find_probable_owner(args):
    res, err = _resource(args.get("resource_id", ""))
    if err:
        return {"status": "error", "message": err}
    found = _lookup_creator(res["id"])
    if not found:
        return {"resource_id": res["id"], "creator": "unknown", "source": "cloudtrail",
                "message": "Sin evento de creacion en CloudTrail (mas de 90 dias o aun no indexado)."}
    return {"resource_id": res["id"], "source": "cloudtrail", **found}


def notify_owner(args):
    res, err = _resource(args.get("resource_id", ""))
    if err:
        return {"status": "error", "message": err}
    owner = args.get("owner") or "unknown"
    routed_to = NO_OWNER if owner == "unknown" else owner
    body = "\n".join([
        f"Para: {routed_to}",
        f"Recurso: {res['name']} ({res['type']} {res['id']}, {res['detail']}, sin uso)",
        f"Mensaje del agente {AGENT_ID}:",
        args.get("message", "(sin mensaje)"),
        "",
        "Responde con:",
        f"  python scripts/owner_reply.py {res['name']} release   # no es mio / se puede eliminar",
        f"  python scripts/owner_reply.py {res['name']} claim     # es mio, no lo toquen",
    ])
    sns.publish(TopicArn=TOPIC_ARN, Subject=_subject(f"[{AGENT_ID}] {res['name']}: aviso para {routed_to}"),
                Message=body)
    LOG.info(json.dumps({"lane": LANE, "tool": "notify_owner", "resource_id": res["id"], "routed_to": routed_to}))
    return {"status": "notified", "resource_id": res["id"], "routed_to": routed_to}


def quarantine_resource(args):
    res, err = _resource(args.get("resource_id", ""))
    if err:
        return {"status": "error", "message": err}
    if LANE == "governed":
        problem = _review_problem(res, ("none",))
        if problem:
            return _refused("lambda", f"Cuarentena rechazada: {problem}.")

    until = (datetime.now(UTC) + timedelta(minutes=QUARANTINE_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        ec2.create_tags(Resources=[res["id"]], Tags=[
            {"Key": "orphan-status", "Value": "quarantined"},
            {"Key": "quarantine-until", "Value": until},
            {"Key": "quarantined-by", "Value": AGENT_ID},
        ])
    except ClientError as err:
        if _iam_denied(err):
            return _refused("iam", f"IAM nego la cuarentena de {res['id']}.")
        raise
    return {"status": "quarantined", "resource_id": res["id"], "name": res["name"], "until": until}


def delete_resource(args):
    res, err = _resource(args.get("resource_id", ""))
    if err:
        return {"status": "error", "message": err}
    LOG.info(json.dumps({
        "lane": LANE, "tool": "delete_resource", "resource_id": res["id"], "type": res["type"], "name": res["name"],
        "declared_env": args.get("environment"), "real_env": res["tags"].get("env"), "reason": args.get("reason", ""),
    }))
    if LANE == "governed":
        problem = _review_problem(res, ("expired", "released"))
        if problem:
            return _refused("lambda", f"Eliminacion rechazada: {problem}.")

    try:
        inv.delete(ec2, res)
    except ClientError as err:
        if _iam_denied(err):
            return _refused("iam", f"IAM nego la eliminacion de {res['id']}.")
        if err.response["Error"]["Code"] == "DependencyViolation":
            return {"status": "error", "message": f"{res['id']} tiene dependencias: {err.response['Error']['Message']}"}
        raise
    return {"status": "deleted", "resource_id": res["id"], "type": res["type"], "name": res["name"]}


TOOLS = {
    "list_candidates": list_candidates,
    "find_probable_owner": find_probable_owner,
    "notify_owner": notify_owner,
    "quarantine_resource": quarantine_resource,
    "delete_resource": delete_resource,
}


def handler(event, context):
    tool = _tool_name(event, context)
    args = {k: v for k, v in (event or {}).items() if k != "__tool"}
    LOG.info(json.dumps({"lane": LANE, "tool": tool, "args": args}))
    fn = TOOLS.get(tool)
    if not fn:
        return {"status": "error", "message": f"Herramienta desconocida: {tool}"}
    return fn(args)
