"""Strict structured output for the Validate (QC) Agent.

Validator không sửa số liệu thay agent chính. Nó chỉ đọc run log + output pack của
một stage (finance / risk / decision) và trả về một verdict kèm challenge ticket khi
phát hiện sai/thiếu/vượt quyền. Verdict là cổng (gate) quyết định pipeline có được
đi tiếp sang stage sau hay không.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.schema.handoff_packs import Severity, StrictModel


# Stage đang được kiểm tra. Một run có tối đa ba lần validate, mỗi lần một stage.
Stage = Literal["finance", "risk", "decision"]

# Bốn nhóm nhiệm vụ QC của validator (mục 2 trong thiết kế):
#   PROCESS            — A. đi đủ/đúng các bước quy trình.
#   TOOL_DATA_SOURCE   — B. đúng tool / đúng bảng dữ liệu, không gọi nguồn cấm.
#   OUTPUT_SCHEMA      — C. output đúng loại pack, không lẫn output của stage khác.
#   AUTHORITY_BOUNDARY — D. không vượt quyền (accept/reject, chọn sản phẩm, precheck…).
CheckCategory = Literal[
    "PROCESS",
    "TOOL_DATA_SOURCE",
    "OUTPUT_SCHEMA",
    "AUTHORITY_BOUNDARY",
]


# Kết luận validator được phép trả (mục 2, phần cuối). Chỉ năm giá trị này hợp lệ;
# validator không có quyền nào khác ngoài phán xử. ``BLOCK_FINAL_DECISION`` chỉ dùng
# cho stage decision.
VERDICT_VALUES = Literal[
    "PASS",
    "NEED_CLARIFICATION",
    "REWORK_REQUIRED",
    "BLOCK_NEXT_STAGE",
    "BLOCK_FINAL_DECISION",
]

# Chỉ verdict này cho phép pipeline đi tiếp. Mọi verdict khác là một cổng chặn.
PASSING_VERDICTS = {"PASS"}


class ChecklistItemResult(StrictModel):
    """Một mục trong checklist của stage, cùng bằng chứng lấy từ run log/pack."""

    item_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: CheckCategory
    passed: bool
    evidence: str = Field(
        min_length=1,
        description="Trích dẫn cụ thể từ run log/output pack chứng minh kết luận.",
    )
    note: str = ""


class ChallengeTicket(StrictModel):
    """Phiếu phản biện gửi lại agent trước khi validator không PASS.

    Agent trước phải giải trình hoặc chạy lại đúng phần sai, rồi validator kiểm lại.
    """

    ticket_id: str = Field(min_length=1)
    stage: Stage
    target_agent: str = Field(min_length=1)
    category: CheckCategory
    checklist_item: str = Field(min_length=1)
    severity: Severity
    verdict: VERDICT_VALUES
    finding: str = Field(min_length=1, description="Sai/thiếu/vượt quyền cụ thể.")
    evidence: str = Field(min_length=1, description="Dẫn chứng từ log/pack.")
    required_action: str = Field(
        min_length=1,
        description="Việc agent trước phải làm để được PASS.",
    )


class ValidationReport(StrictModel):
    """Kết quả QC của validator cho đúng một stage."""

    session_id: int = Field(gt=0)
    stage: Stage
    validated_agent: str = Field(min_length=1)
    verdict: VERDICT_VALUES
    checklist_results: list[ChecklistItemResult] = Field(min_length=1)
    challenge_tickets: list[ChallengeTicket] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    validated_at: datetime | None = None

    @property
    def passed(self) -> bool:
        return self.verdict in PASSING_VERDICTS

    @model_validator(mode="after")
    def _consistency(self) -> "ValidationReport":
        # PASS phải sạch: không kèm phiếu phản biện.
        if self.verdict in PASSING_VERDICTS and self.challenge_tickets:
            raise ValueError("PASS verdict must not carry challenge tickets")
        # Mọi verdict chặn phải kèm ít nhất một phiếu phản biện có dẫn chứng.
        if self.verdict not in PASSING_VERDICTS and not self.challenge_tickets:
            raise ValueError(
                f"Verdict {self.verdict} requires at least one challenge ticket"
            )
        # BLOCK_FINAL_DECISION là cổng cuối, chỉ thuộc stage decision.
        blocking_final = "BLOCK_FINAL_DECISION"
        if self.stage != "decision" and self.verdict == blocking_final:
            raise ValueError("BLOCK_FINAL_DECISION is only valid for the decision stage")
        if any(
            ticket.verdict == blocking_final and self.stage != "decision"
            for ticket in self.challenge_tickets
        ):
            raise ValueError(
                "BLOCK_FINAL_DECISION tickets are only valid for the decision stage"
            )
        # Phiếu phản biện phải thuộc đúng stage đang kiểm.
        for ticket in self.challenge_tickets:
            if ticket.stage != self.stage:
                raise ValueError(
                    f"Challenge ticket stage {ticket.stage} does not match "
                    f"report stage {self.stage}"
                )
        return self


__all__ = [
    "ChallengeTicket",
    "CheckCategory",
    "ChecklistItemResult",
    "PASSING_VERDICTS",
    "Stage",
    "ValidationReport",
    "VERDICT_VALUES",
]
