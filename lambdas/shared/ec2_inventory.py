"""Inventario de recursos EC2 "huerfanizables": una sola fuente de verdad para las Lambdas."""

import json
from datetime import UTC, datetime

from botocore.exceptions import ClientError

TYPES = {
    "volume": {"prefix": "vol-", "event": "CreateVolume", "id_path": ("volumeId",)},
    "snapshot": {"prefix": "snap-", "event": "CreateSnapshot", "id_path": ("snapshotId",)},
    "elastic-ip": {"prefix": "eipalloc-", "event": "AllocateAddress", "id_path": ("allocationId",)},
    "security-group": {"prefix": "sg-", "event": "CreateSecurityGroup", "id_path": ("groupId",)},
    "network-interface": {"prefix": "eni-", "event": "CreateNetworkInterface",
                          "id_path": ("networkInterface", "networkInterfaceId")},
}
NOT_FOUND = {
    "InvalidVolume.NotFound", "InvalidVolumeID.Malformed", "InvalidSnapshot.NotFound", "InvalidSnapshotID.Malformed",
    "InvalidAllocationID.NotFound", "InvalidAllocationID.Malformed",
    "InvalidGroup.NotFound", "InvalidGroupId.Malformed",
    "InvalidNetworkInterfaceID.NotFound", "InvalidNetworkInterfaceID.Malformed", "InvalidParameterValue",
}


def resource_type(resource_id):
    for name, spec in TYPES.items():
        if str(resource_id or "").startswith(spec["prefix"]):
            return name
    return None


def quarantine_status(tags, now=None):
    """none | active | expired | claimed | released | unknown."""
    now = now or datetime.now(UTC)
    status = tags.get("orphan-status")
    if not status:
        return "none"
    if status in ("claimed", "released"):
        return status
    if status == "quarantined":
        try:
            until = datetime.fromisoformat(tags.get("quarantine-until", "").replace("Z", "+00:00"))
        except ValueError:
            return "active"  # fecha ilegible: nunca se trata como vencida
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        return "expired" if now >= until else "active"
    return "unknown"


def tags_of(raw):
    return {t["Key"]: t["Value"] for t in (raw.get("Tags") or raw.get("TagSet") or [])}


def _created(value):
    return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else None


def _sg_in_use(ec2, group_id):
    enis = ec2.describe_network_interfaces(Filters=[{"Name": "group-id", "Values": [group_id]}])
    return bool(enis.get("NetworkInterfaces"))


def _normalize(ec2, kind, raw):
    tags = tags_of(raw)
    if kind == "volume":
        rid, in_use, detail, created = raw["VolumeId"], raw.get("State") != "available", f"{raw['Size']} GiB", \
            _created(raw.get("CreateTime"))
    elif kind == "snapshot":
        rid, in_use, detail, created = raw["SnapshotId"], False, f"{raw.get('VolumeSize', '?')} GiB", \
            _created(raw.get("StartTime"))
    elif kind == "elastic-ip":
        rid, in_use, detail, created = raw["AllocationId"], bool(raw.get("AssociationId")), \
            raw.get("PublicIp", ""), None
    elif kind == "security-group":
        rid, detail, created = raw["GroupId"], f"{len(raw.get('IpPermissions', []))} reglas de entrada", None
        in_use = _sg_in_use(ec2, rid)
    else:  # network-interface
        rid, in_use, detail, created = raw["NetworkInterfaceId"], raw.get("Status") != "available", \
            raw.get("PrivateIpAddress", ""), None
    return {"id": rid, "type": kind, "name": tags.get("Name", rid), "tags": tags,
            "in_use": in_use, "detail": detail, "created": created}


def _describe_calls(ec2, kind, ids=None, filters=None):
    kw = {"Filters": filters} if filters else {}
    if kind == "volume":
        return ec2.describe_volumes(**({"VolumeIds": ids} if ids else {}), **kw)["Volumes"]
    if kind == "snapshot":
        return ec2.describe_snapshots(OwnerIds=["self"], **({"SnapshotIds": ids} if ids else {}), **kw)["Snapshots"]
    if kind == "elastic-ip":
        return ec2.describe_addresses(**({"AllocationIds": ids} if ids else {}), **kw)["Addresses"]
    if kind == "security-group":
        return ec2.describe_security_groups(**({"GroupIds": ids} if ids else {}), **kw)["SecurityGroups"]
    return ec2.describe_network_interfaces(**({"NetworkInterfaceIds": ids} if ids else {}), **kw)["NetworkInterfaces"]


def describe(ec2, resource_id):
    """Recurso normalizado, o None si no existe o el ID no es de un tipo soportado."""
    kind = resource_type(resource_id)
    if not kind:
        return None
    try:
        raws = _describe_calls(ec2, kind, ids=[resource_id])
    except ClientError as err:
        if err.response["Error"]["Code"] in NOT_FOUND:
            return None
        raise
    return _normalize(ec2, kind, raws[0]) if raws else None


def list_inventory(ec2, project, batch, kinds=None):
    """Todos los recursos del lote, de todos los tipos (o de `kinds`)."""
    filters = [{"Name": "tag:project", "Values": [project]}, {"Name": "tag:demo_batch", "Values": [batch]}]
    items = []
    for kind in kinds or TYPES:
        items.extend(_normalize(ec2, kind, raw) for raw in _describe_calls(ec2, kind, filters=filters))
    return sorted(items, key=lambda i: (i["type"], i["name"]))


def facts(ec2, resource_id):
    """Hechos reales para el interceptor: etiquetas + tipo + en uso + cuarentena derivada. {} si no existe."""
    res = describe(ec2, resource_id)
    if not res:
        return {}
    return {**res["tags"], "type": res["type"], "in_use": "true" if res["in_use"] else "false",
            "quarantine": quarantine_status(res["tags"])}


def delete(ec2, res):
    rid = res["id"]
    if res["type"] == "volume":
        ec2.delete_volume(VolumeId=rid)
    elif res["type"] == "snapshot":
        ec2.delete_snapshot(SnapshotId=rid)
    elif res["type"] == "elastic-ip":
        ec2.release_address(AllocationId=rid)
    elif res["type"] == "security-group":
        ec2.delete_security_group(GroupId=rid)
    else:
        ec2.delete_network_interface(NetworkInterfaceId=rid)


def creator_from_event(event, resource_id):
    """{"creator", "created_at"} si el evento de CloudTrail creo este recurso, si no None."""
    detail = json.loads(event.get("CloudTrailEvent", "{}"))
    kind = resource_type(resource_id)
    if not kind or detail.get("eventName") != TYPES[kind]["event"]:
        return None
    value = detail.get("responseElements") or {}
    for key in TYPES[kind]["id_path"]:
        value = value.get(key) if isinstance(value, dict) else None
    if value != resource_id:
        return None
    return {"creator": (detail.get("userIdentity") or {}).get("arn", "unknown"), "created_at": detail.get("eventTime")}


def lookup_creator(cloudtrail, resource_id, max_items=100):
    kind = resource_type(resource_id)
    if not kind:
        return None
    lookups = [
        [{"AttributeKey": "ResourceName", "AttributeValue": resource_id}],
        [{"AttributeKey": "EventName", "AttributeValue": TYPES[kind]["event"]}],
    ]
    for attrs in lookups:
        pages = cloudtrail.get_paginator("lookup_events").paginate(
            LookupAttributes=attrs, PaginationConfig={"MaxItems": max_items})
        for page in pages:
            for event in page.get("Events", []):
                found = creator_from_event(event, resource_id)
                if found:
                    return found
    return None
