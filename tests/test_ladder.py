import pytest

from guardrails import ladder
from guardrails.ladder import decide, tally

OK = {"outcome": "success"}
BLOCK = {"outcome": "blocked"}
ERR = {"outcome": "error"}
CONFIRMED = {"outcome": "confirmed"}
REJECTED = {"outcome": "rejected"}


HUMAN = {"promote_on": ("confirmed",), "demote_on": ("blocked", "rejected")}


def d(level, events, approve=False, promote_after=3, **kw):
    return decide(level, events, promote_after, 0, 2, approve=approve, **kw)


def test_blocked_demotes_one_level_without_asking():
    out = d(2, [BLOCK, OK, OK, OK])
    assert (out.action, out.new_level) == ("demote", 1)


def test_demotion_wins_over_promotion_threshold():
    assert d(1, [OK] * 10 + [BLOCK]).action == "demote"


def test_floor_holds_at_minimum():
    assert (d(0, [BLOCK]).action, d(0, [BLOCK]).new_level) == ("floor", 0)


def test_promotion_is_only_proposed_without_approval():
    out = d(0, [OK, OK, OK])
    assert (out.action, out.new_level) == ("propose", 1)


def test_promotion_applies_with_approval():
    out = d(1, [OK, OK, OK], approve=True)
    assert (out.action, out.new_level) == ("promote", 2)


def test_not_enough_evidence_holds():
    assert d(0, [OK, OK]).action == "hold"


def test_ceiling_never_promotes():
    assert d(2, [OK] * 9, approve=True).action == "hold"


def test_errors_count_neither_way():
    assert d(1, [ERR, ERR, ERR]).action == "hold"


@pytest.mark.parametrize("n", [1, 2, 5])
def test_threshold_is_configurable(n):
    assert d(0, [OK] * n, promote_after=n).action == "propose"
    assert d(0, [OK] * (n - 1), promote_after=n).action == "hold"


def test_tool_success_alone_does_not_promote_when_humans_decide():
    """El agente no se asciende por hacer cosas: se asciende porque humanos confirman que acerto."""
    assert d(0, [OK] * 10, **HUMAN).action == "hold"


def test_human_confirmations_propose_promotion():
    assert d(0, [CONFIRMED] * 3 + [OK] * 5, **HUMAN).action == "propose"


def test_owner_claim_demotes():
    out = d(1, [CONFIRMED] * 5 + [REJECTED], **HUMAN)
    assert (out.action, out.new_level) == ("demote", 0)


def test_policy_block_still_demotes_with_human_rules():
    assert d(2, [CONFIRMED] * 5 + [BLOCK], **HUMAN).action == "demote"


def test_tally():
    assert tally([OK, OK, BLOCK, ERR]) == (2, 1)
    assert tally([CONFIRMED, OK, REJECTED, BLOCK], **HUMAN) == (1, 2)


def test_write_level_only_touches_trust_level(tmp_path, monkeypatch):
    tfvars = tmp_path / "terraform.tfvars"
    tfvars.write_text('region      = "us-east-1"\ntrust_level = 0\nnotify_email = null\n', encoding="utf-8")
    monkeypatch.setattr(ladder.config, "tfvars_path", lambda: tfvars)
    ladder.write_level(2)
    assert tfvars.read_text(encoding="utf-8") == 'region      = "us-east-1"\ntrust_level = 2\nnotify_email = null\n'
