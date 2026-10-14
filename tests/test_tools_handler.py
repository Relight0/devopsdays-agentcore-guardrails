import json
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from conftest import ROOT, SCENARIO, SCENARIO_DIR, load_module

HANDLER = SCENARIO_DIR / "lambdas" / "tools" / "handler.py"
TOTAL = len(SCENARIO["inventory"])
TRAPS = SCENARIO["traps"]


def make_tools(monkeypatch, lane):
    ssm = boto3.client("ssm", region_name="us-east-1")
    ssm.put_parameter(Name="/demo/active-batch", Value="a", Type="String")
    topic = boto3.client("sns", region_name="us-east-1").create_topic(Name="notify")["TopicArn"]
    for k, v in {"PROJECT": "demo", "LANE": lane, "ACTIVE_BATCH_PARAM": "/demo/active-batch",
                 "TOPIC_ARN": topic, "QUARANTINE_MINUTES": "3", "AGENT_ID": "orphan-hunter"}.items():
        monkeypatch.setenv(k, v)
    mod = load_module(f"tools_{lane}", HANDLER)
    mod.published = []
    real_publish = mod.sns.publish

    def publish(**kw):
        mod.published.append(kw)
        return real_publish(**kw)

    monkeypatch.setattr(mod.sns, "publish", publish)
    monkeypatch.setattr(mod, "_lookup_creator", lambda rid: {"creator": "arn:aws:iam::1:user/terraform",
                                                            "created_at": "2026-10-05T00:00:00Z"})
    return mod


def invoke(mod, tool, **args):
    return mod.handler({"__tool": f"resources___{tool}", **args}, None)


def ec2():
    return boto3.client("ec2", region_name="us-east-1")


def tag(rid, **tags):
    ec2().create_tags(Resources=[rid], Tags=[{"Key": k.replace("_", "-"), "Value": v} for k, v in tags.items()])


def tags_of(rid):
    import ec2_inventory as inv
    return inv.describe(ec2(), rid)["tags"]


@pytest.fixture
def governed(monkeypatch, seeded):
    return make_tools(monkeypatch, "governed"), seeded


@pytest.fixture
def ungoverned(monkeypatch, seeded):
    return make_tools(monkeypatch, "ungoverned"), seeded


def test_list_hides_governance_tags_and_other_batches(governed):
    mod, _ = governed
    out = invoke(mod, "list_candidates")
    assert out["count"] == TOTAL  # solo el lote activo
    for res in out["resources"]:
        assert set(res) == {"resource_id", "type", "name", "notes", "detail", "created", "review_status"}
    status = {r["name"]: r["review_status"] for r in out["resources"]}
    assert status["test-load-results-0812"] == "expired"
    assert status["old-jenkins-workspace"] == "claimed"
    assert status["test-snapshot-loadgen"] == "released"


def test_list_filters(governed):
    mod, _ = governed
    assert [r["name"] for r in invoke(mod, "list_candidates", resource_type="elastic-ip")["resources"]] == [
        "tmp-partner-vpn-ip"]
    assert [r["name"] for r in invoke(mod, "list_candidates", name_contains="JENKINS")["resources"]] == [
        "old-jenkins-workspace"]


def test_list_skips_resources_in_use(governed):
    mod, ids = governed
    subnet = ec2().describe_subnets()["Subnets"][0]["SubnetId"]
    ec2().create_network_interface(SubnetId=subnet, Groups=[ids["old-test-sg"]])
    names = {r["name"] for r in invoke(mod, "list_candidates")["resources"]}
    assert "old-test-sg" not in names


def test_find_probable_owner_returns_creator_not_owner(governed):
    mod, ids = governed
    assert invoke(mod, "find_probable_owner", resource_id=ids["scratch-ml-features"])["creator"].endswith(
        "user/terraform")


def test_find_probable_owner_unknown(governed, monkeypatch):
    mod, ids = governed
    monkeypatch.setattr(mod, "_lookup_creator", lambda rid: None)
    assert invoke(mod, "find_probable_owner", resource_id=ids["old-build-cache"])["creator"] == "unknown"


def test_notify_publishes_and_routes(governed):
    mod, ids = governed
    out = invoke(mod, "notify_owner", resource_id=ids["tmp-partner-vpn-ip"], owner="equipo-integraciones",
                 message="es tuya?")
    assert out == {"status": "notified", "resource_id": ids["tmp-partner-vpn-ip"], "routed_to": "equipo-integraciones"}
    msg = mod.published[0]
    assert "equipo-integraciones" in msg["Subject"] and "owner_reply.py tmp-partner-vpn-ip" in msg["Message"]


def test_notify_unknown_owner_goes_to_platform(governed):
    mod, ids = governed
    assert invoke(mod, "notify_owner", resource_id=ids["tmp-debug-eni"], owner="unknown",
                  message="x")["routed_to"].startswith("plataforma")


def test_notify_subject_is_sns_safe(ungoverned):
    mod, ids = ungoverned
    invoke(mod, "notify_owner", resource_id=ids["old-build-cache"], owner="dueño\nde " + "x" * 200, message="x")
    subject = mod.published[0]["Subject"]
    assert subject.isascii() and "\n" not in subject and len(subject) < 100


@pytest.mark.parametrize("name", ["old-build-cache", "old-ami-backup-2025", "old-test-sg", "tmp-debug-eni"])
def test_quarantine_tags_only_review_keys(governed, name):
    mod, ids = governed
    rid = ids[name]
    before = tags_of(rid)
    out = invoke(mod, "quarantine_resource", resource_id=rid, environment="dev", reason="x")
    assert out["status"] == "quarantined", out
    after = tags_of(rid)
    assert after["orphan-status"] == "quarantined" and after["quarantined-by"] == "orphan-hunter"
    until = datetime.fromisoformat(after["quarantine-until"].replace("Z", "+00:00"))
    assert timedelta(minutes=2) < until - datetime.now(UTC) <= timedelta(minutes=3)
    assert {k for k in after if after[k] != before.get(k)} == {"orphan-status", "quarantine-until", "quarantined-by"}


@pytest.mark.parametrize("name", [*TRAPS, "orders-db-data", "old-jenkins-workspace", "test-load-results-0812",
                                  "test-snapshot-loadgen"])
def test_governed_quarantine_refuses_prod_hold_or_in_review(governed, name):
    mod, ids = governed
    out = invoke(mod, "quarantine_resource", resource_id=ids[name], environment="dev", reason="x")
    assert out["status"] == "refused" and out["layer"] == "lambda", out


def test_released_is_not_quarantined_again(governed):
    """La respuesta del dueno (released) no la pisa el agente."""
    mod, ids = governed
    tag(ids["old-build-cache"], orphan_status="released")
    assert invoke(mod, "quarantine_resource", resource_id=ids["old-build-cache"], environment="dev",
                  reason="x")["status"] == "refused"
    assert tags_of(ids["old-build-cache"])["orphan-status"] == "released"


def test_in_use_resource_is_refused(governed):
    mod, ids = governed
    subnet = ec2().describe_subnets()["Subnets"][0]["SubnetId"]
    ec2().create_network_interface(SubnetId=subnet, Groups=[ids["old-test-sg"]])
    out = invoke(mod, "quarantine_resource", resource_id=ids["old-test-sg"], environment="dev", reason="x")
    assert out["status"] == "refused" and "en uso" in out["message"]


@pytest.mark.parametrize("name", ["test-load-results-0812", "test-snapshot-loadgen"])
def test_governed_deletes_what_went_through_the_process(governed, name):
    mod, ids = governed
    out = invoke(mod, "delete_resource", resource_id=ids[name], environment="staging", reason="x")
    assert out["status"] == "deleted", out
    assert invoke(mod, "list_candidates")["count"] == TOTAL - 1


@pytest.mark.parametrize("name", ["old-ami-backup-2025", "old-test-sg", "tmp-debug-eni", "tmp-reports-export"])
def test_released_resources_of_every_type_can_be_deleted(governed, name):
    mod, ids = governed
    tag(ids[name], orphan_status="released")
    assert invoke(mod, "delete_resource", resource_id=ids[name], environment="dev", reason="x")["status"] == "deleted"


@pytest.mark.parametrize("name", [*TRAPS, "old-build-cache", "old-jenkins-workspace"])
def test_governed_refuses_delete_without_process(governed, name):
    """Las trampas (prod+hold), un huerfano sin cuarentena y uno reclamado: ninguno se borra."""
    mod, ids = governed
    out = invoke(mod, "delete_resource", resource_id=ids[name], environment="dev", reason="x")
    assert out["status"] == "refused" and out["layer"] == "lambda"
    assert invoke(mod, "list_candidates")["count"] == TOTAL


def test_active_quarantine_cannot_be_deleted_yet(governed):
    mod, ids = governed
    invoke(mod, "quarantine_resource", resource_id=ids["old-build-cache"], environment="dev", reason="x")
    out = invoke(mod, "delete_resource", resource_id=ids["old-build-cache"], environment="dev", reason="x")
    assert out["status"] == "refused" and "active" in out["message"]


@pytest.mark.parametrize("trap", TRAPS)
def test_ungoverned_deletes_the_traps(ungoverned, trap):
    """Acto 1: sin gobierno manda el nombre y se borra prod (incluida la IP del aliado: no se recupera)."""
    mod, ids = ungoverned
    assert invoke(mod, "delete_resource", resource_id=ids[trap], environment="dev", reason="x")["status"] == "deleted"


def test_other_batch_is_out_of_reach(governed):
    mod, _ = governed
    other = ec2().describe_volumes(Filters=[{"Name": "tag:demo_batch", "Values": ["b"]}])["Volumes"][0]["VolumeId"]
    assert invoke(mod, "delete_resource", resource_id=other, environment="dev")["status"] == "error"


def test_unknown_unsupported_and_tool(governed):
    mod, _ = governed
    assert invoke(mod, "delete_resource", resource_id="vol-0000000000000000f", environment="dev")["status"] == "error"
    assert "no soportado" in invoke(mod, "delete_resource", resource_id="i-0123", environment="dev")["message"]
    assert invoke(mod, "nope")["status"] == "error"


def test_tool_name_from_client_context(governed):
    mod, _ = governed

    class Ctx:
        class client_context:  # noqa: N801
            custom = {"bedrockAgentCoreToolName": "resources___list_candidates"}

    out = mod.handler({}, Ctx())
    assert out["count"] == TOTAL
    json.dumps(out)  # serializable


@pytest.mark.parametrize(("tags", "expected"), [
    ({}, "none"),
    ({"orphan-status": "claimed"}, "claimed"),
    ({"orphan-status": "released"}, "released"),
    ({"orphan-status": "quarantined", "quarantine-until": "2026-01-01T00:00:00Z"}, "expired"),
    ({"orphan-status": "quarantined", "quarantine-until": "2999-01-01T00:00:00Z"}, "active"),
    ({"orphan-status": "quarantined", "quarantine-until": "no-es-fecha"}, "active"),
    ({"orphan-status": "quarantined", "quarantine-until": "2026-01-01"}, "expired"),  # sin zona: UTC
    ({"orphan-status": "quarantined"}, "active"),
    ({"orphan-status": "raro"}, "unknown"),
])
def test_tool_and_interceptor_share_the_quarantine_rule(monkeypatch, tags, expected):
    for k in ("PROJECT", "LANE", "ACTIVE_BATCH_PARAM", "TOPIC_ARN"):
        monkeypatch.setenv(k, "x")
    tool = load_module("tools_rule", HANDLER)
    resolver = load_module("resolver_rule", ROOT / "lambdas" / "attribute_resolver" / "handler.py")
    import ec2_inventory as inv
    assert tool.quarantine_status is inv.quarantine_status
    assert "ec2_resource_facts" in resolver.RESOLVERS
    assert inv.quarantine_status(tags) == expected
