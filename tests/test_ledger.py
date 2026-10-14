import time

import boto3
import pytest
from moto import mock_aws

from guardrails import ledger


@pytest.fixture
def table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        yield ddb.create_table(
            TableName="ledger",
            KeySchema=[{"AttributeName": "agent_id", "KeyType": "HASH"}, {"AttributeName": "ts", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "agent_id", "AttributeType": "S"},
                                  {"AttributeName": "ts", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


def tick():
    time.sleep(0.002)  # ts con microsegundos distintos


def test_events_since_last_change(table):
    ledger.record_outcome(table, "a1", "t", "blocked", 1)
    tick()
    ledger.record_level_change(table, "a1", 1, 0, "demotion")
    tick()
    ledger.record_outcome(table, "a1", "t", "success", 0)
    tick()
    ledger.record_outcome(table, "a1", "t", "success", 0)
    events = ledger.since_last_change(table, "a1")
    assert [e["outcome"] for e in events] == ["success", "success"]


def test_agents_are_isolated(table):
    ledger.record_outcome(table, "a1", "t", "success", 0)
    tick()
    ledger.record_outcome(table, "a2", "t", "blocked", 0)
    assert [e["outcome"] for e in ledger.since_last_change(table, "a1")] == ["success"]


def test_clear(table):
    for _ in range(3):
        ledger.record_outcome(table, "a1", "t", "success", 0)
        tick()
    assert ledger.clear(table, "a1") == 3
    assert ledger.since_last_change(table, "a1") == []


def test_detail_is_truncated(table):
    ledger.record_outcome(table, "a1", "t", "error", 0, detail="x" * 2000)
    assert len(ledger.since_last_change(table, "a1")[0]["detail"]) == 500


def test_last_level(table):
    assert ledger.last_level(table, "a1") is None
    ledger.record_level_change(table, "a1", 0, 1, "promotion")
    tick()
    ledger.record_outcome(table, "a1", "t", "success", 1)
    assert ledger.last_level(table, "a1") == 1
