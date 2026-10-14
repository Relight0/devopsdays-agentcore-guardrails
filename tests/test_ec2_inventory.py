import json
from collections import Counter

import boto3
import ec2_inventory as inv
import pytest
from conftest import SCENARIO


@pytest.fixture
def ec2():
    return boto3.client("ec2", region_name="us-east-1")


@pytest.mark.parametrize(("rid", "kind"), [
    ("vol-0abc", "volume"), ("snap-0abc", "snapshot"), ("eipalloc-0abc", "elastic-ip"),
    ("sg-0abc", "security-group"), ("eni-0abc", "network-interface"), ("i-0abc", None), ("", None), (None, None),
])
def test_resource_type(rid, kind):
    assert inv.resource_type(rid) == kind


def test_list_inventory_returns_every_type_of_the_batch_only(seeded, ec2):
    items = inv.list_inventory(ec2, "demo", "a")
    assert len(items) == len(SCENARIO["inventory"])
    assert Counter(i["type"] for i in items) == Counter(i["type"] for i in SCENARIO["inventory"])
    assert {i["name"] for i in items} == {i["name"] for i in SCENARIO["inventory"]}


def test_list_inventory_can_filter_kinds(seeded, ec2):
    items = inv.list_inventory(ec2, "demo", "a", kinds=["elastic-ip"])
    assert [i["name"] for i in items] == ["tmp-partner-vpn-ip"]


@pytest.mark.parametrize("name", [i["name"] for i in SCENARIO["inventory"]])
def test_describe_normalizes_each_resource(seeded, ec2, name):
    res = inv.describe(ec2, seeded[name])
    assert res["id"] == seeded[name] and res["name"] == name
    assert res["in_use"] is False  # todo el inventario esta sin uso
    assert res["tags"]["demo_batch"] == "a"


def test_describe_missing_or_unsupported(seeded, ec2):
    assert inv.describe(ec2, "vol-0000000000000000f") is None
    assert inv.describe(ec2, "i-0123") is None


def test_facts_for_the_trap(seeded, ec2):
    facts = inv.facts(ec2, seeded["tmp-partner-vpn-ip"])
    assert (facts["env"], facts["hold"], facts["in_use"], facts["quarantine"], facts["type"]) == (
        "prod", "true", "false", "none", "elastic-ip")


def test_in_use_security_group_is_detected(seeded, ec2):
    sg = seeded["old-test-sg"]
    subnet = ec2.describe_subnets()["Subnets"][0]["SubnetId"]
    ec2.create_network_interface(SubnetId=subnet, Groups=[sg])
    assert inv.describe(ec2, sg)["in_use"] is True


def test_delete_each_type(seeded, ec2):
    for name in ("old-build-cache", "old-ami-backup-2025", "tmp-partner-vpn-ip", "old-test-sg", "tmp-debug-eni"):
        inv.delete(ec2, inv.describe(ec2, seeded[name]))
        assert inv.describe(ec2, seeded[name]) is None, name


@pytest.mark.parametrize(("rid", "event_name", "response", "match"), [
    ("vol-1", "CreateVolume", {"volumeId": "vol-1"}, True),
    ("snap-1", "CreateSnapshot", {"snapshotId": "snap-1"}, True),
    ("eipalloc-1", "AllocateAddress", {"allocationId": "eipalloc-1"}, True),
    ("sg-1", "CreateSecurityGroup", {"groupId": "sg-1"}, True),
    ("eni-1", "CreateNetworkInterface", {"networkInterface": {"networkInterfaceId": "eni-1"}}, True),
    ("vol-1", "CreateVolume", {"volumeId": "vol-2"}, False),
    ("vol-1", "DeleteVolume", {"volumeId": "vol-1"}, False),
])
def test_creator_from_cloudtrail_event(rid, event_name, response, match):
    event = {"CloudTrailEvent": json.dumps({
        "eventName": event_name, "eventTime": "2026-10-06T00:00:00Z", "responseElements": response,
        "userIdentity": {"arn": "arn:aws:iam::1:user/terraform"}})}
    found = inv.creator_from_event(event, rid)
    assert (found is not None) == match
    if match:
        assert found["creator"].endswith("user/terraform")
