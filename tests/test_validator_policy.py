from app.tools.ValidatorAgent.evidence import STAGE_POLICY


def test_risk_validator_treats_rr_005_as_active_rule() -> None:
    risk_policy = STAGE_POLICY["risk"]

    rr_005_policy = risk_policy["rule_status_policy"]["RR-005"]
    assert "ACTIVE rule" in rr_005_policy
    assert "NOT_APPLICABLE" in rr_005_policy
    assert "RULE_INACTIVE is valid only" in rr_005_policy


def test_risk_validator_prompt_does_not_force_rr_005_inactive() -> None:
    evaluation_note = STAGE_POLICY["risk"]["evaluation_note"]

    assert "RR-005 là rule hoạt động" in evaluation_note
    assert "không được ép thành RULE_INACTIVE" in evaluation_note
