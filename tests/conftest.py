import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "lambdas" / "shared"))  # ec2_inventory, como dentro del zip de las Lambdas

SCENARIO_DIR = ROOT / "examples" / "orphan-hunter"
SCENARIO = json.loads((SCENARIO_DIR / "data" / "scenario.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Credenciales falsas: ninguna prueba puede tocar AWS de verdad."""
    for key in ("AWS_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


def load_module(name, path):
    """Importa un handler de Lambda por ruta (cada prueba obtiene una copia nueva, con sus clientes boto3)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_tags(item, batch):
    tags = {k: v for k, v in item["tags"].items() if v is not None}
    tags.update({"Name": item["name"], "notes": item["notes"], "project": "demo", "demo_batch": batch})
    return [{"Key": k, "Value": v} for k, v in tags.items()]


def create(ec2, item, batch, vpc_id, subnet_id):
    """Crea un recurso del inventario, como lo hace inventory.tf. Devuelve su ID."""
    tags = seed_tags(item, batch)
    kind = item["type"]
    if kind == "volume":
        return ec2.create_volume(AvailabilityZone="us-east-1a", Size=1, VolumeType="gp3")["VolumeId"], tags
    if kind == "snapshot":
        vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"]
        return ec2.create_snapshot(VolumeId=vol, Description=item["notes"])["SnapshotId"], tags
    if kind == "elastic-ip":
        return ec2.allocate_address(Domain="vpc")["AllocationId"], tags
    if kind == "security-group":
        return ec2.create_security_group(GroupName=f"{batch}-{item['name']}", Description=item["notes"],
                                         VpcId=vpc_id)["GroupId"], tags
    return ec2.create_network_interface(SubnetId=subnet_id, Description=item["notes"])[
        "NetworkInterface"]["NetworkInterfaceId"], tags


@pytest.fixture
def seeded():
    """Siembra el inventario del escenario (lote a, y una copia en lote b) en un EC2 simulado."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        ec2 = boto3.client("ec2", region_name="us-east-1")
        vpc = ec2.create_vpc(CidrBlock="10.42.0.0/16")["Vpc"]["VpcId"]
        subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.42.1.0/24", AvailabilityZone="us-east-1a")[
            "Subnet"]["SubnetId"]
        ids = {}
        for batch in ("a", "b"):
            for item in SCENARIO["inventory"]:
                rid, tags = create(ec2, item, batch, vpc, subnet)
                ec2.create_tags(Resources=[rid], Tags=tags)
                if batch == "a":
                    ids[item["name"]] = rid
        yield ids
