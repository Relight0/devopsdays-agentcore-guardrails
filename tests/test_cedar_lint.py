import pytest
from conftest import SCENARIO_DIR
from lint_cedar import lint_paths, lint_text

GOOD = """
permit (
  principal is AgentCore::IamEntity,
  action == AgentCore::Action::"${target}___list_snapshots",
  resource == AgentCore::Gateway::"${gateway_arn}"
)
when { principal.id like "arn:aws:*::${account_id}:*" };
"""


def test_repo_policies_pass():
    files, errors = lint_paths([SCENARIO_DIR / "policies"])
    assert len(files) >= 3
    assert errors == []


def test_good_policy_passes():
    assert lint_text(GOOD) == []


@pytest.mark.parametrize("bad, expected", [
    (GOOD.replace('\nwhen { principal.id like "arn:aws:*::${account_id}:*" }', ""), "when"),
    (GOOD.replace('action == AgentCore::Action::"${target}___list_snapshots"', "action"), "action"),
    (GOOD.replace('resource == AgentCore::Gateway::"${gateway_arn}"', "resource"), "resource"),
    (GOOD.replace("principal is AgentCore::IamEntity", "principal"), "principal"),
    (GOOD.replace("${account_id}", "${otra_cosa}"), "placeholder"),
    (GOOD.replace(";", ""), "permit/forbid"),
    (GOOD.replace("when {", "when ("), "balancear"),
])
def test_bad_policies_are_flagged(bad, expected):
    errors = lint_text(bad)
    assert errors and any(expected in e for e in errors), errors


def test_comments_do_not_confuse_the_linter():
    assert lint_text("// permit (principal, action, resource);\n" + GOOD) == []


def test_forbid_without_when_is_allowed():
    forbid = GOOD.replace("permit", "forbid").replace(
        '\nwhen { principal.id like "arn:aws:*::${account_id}:*" }', "")
    assert lint_text(forbid) == []
