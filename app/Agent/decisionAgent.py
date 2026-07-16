from pathlib import Path
from dataclasses import asdict

from agents import Agent, OpenAIChatCompletionsModel, RunContextWrapper, handoff, Runner 
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

from app.Agent.config import OPENAI_CLIENT, OPENAI_MODEL
from app.Agent.hooks import AppContext, CustomAgentHooks
from app.schema.decisionAgent import DecisionAgentHandoff, DecisionBatchOutput
from app.tools.DecisionAgent.GetBankProduct import match_bank_product
from app.tools.DecisionAgent.PrecheckAPI import (
    precheck_micro_credit,
    precheck_performance_bond,
    precheck_trade_finance,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "decisionAgent.md"


def load_prompt(path: Path = PROMPT_PATH) -> str:
    """Load the agent instructions from a UTF-8 Markdown file."""
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError(f"Prompt file is empty: {path}")
    return prompt


DECISION_AGENT_PROMPT = load_prompt()


async def save_decision_handoff(
    context: RunContextWrapper[AppContext],
    payload: DecisionAgentHandoff,
) -> None:
    """Persist the typed handoff payload for downstream agents and logging."""
    context.context.brain_request_payload = asdict(payload)


# ValidatorAgent = Agent(
#     name="Validator Agent",
#     model=OpenAIChatCompletionsModel(
#         model=OPENAI_MODEL,
#         openai_client=OPENAI_CLIENT,
#     ),
#     instructions=prompt_with_handoff_instructions(DECISION_AGENT_PROMPT),
#     handoff_description="Đánh giá sản phẩm ngân hàng và kiểm tra điều kiện hồ sơ.",
#     tools=[
#         match_bank_product,
#         precheck_performance_bond,
#         precheck_trade_finance,
#         precheck_micro_credit,
#     ],
#     hooks=CustomAgentHooks("DecisionAgent"),
# )

DecisionAgent = Agent(
    name="Decision_Agent",
    model=OpenAIChatCompletionsModel(
        model=OPENAI_MODEL,
        openai_client=OPENAI_CLIENT,
    ),
    instructions=prompt_with_handoff_instructions(DECISION_AGENT_PROMPT),
    output_type=DecisionBatchOutput,
    # handoffs=[
    #     handoff(
    #         agent=ValidatorAgent,
    #         input_type=DecisionAgentHandoff,
    #         on_handoff=save_decision_handoff,
    #     )
    # ],
    #handoff_description="Đánh giá sản phẩm ngân hàng và kiểm tra điều kiện hồ sơ.",
    tools=[
        match_bank_product,
        precheck_performance_bond,
        precheck_trade_finance,
        precheck_micro_credit,
    ],
    hooks= CustomAgentHooks("DecisionAgent"),
)
if __name__ == "__main__":
    import asyncio
    import uuid 
    import json
    from decision_agent_sample.sample_data import (
        get_finance_agent_output,
        get_mock_contract_ids,
        get_risk_agent_output,
    )

    def build_credit_decision_case(contract_id: str) -> dict:
        """Giai đoạn 1: gộp finance + risk output thành 1 case chuẩn hóa."""
        finance = get_finance_agent_output(contract_id)
        risk = get_risk_agent_output(contract_id)
        return {
            "contract_id": contract_id,
            "finance": finance,
            "risk": risk,
            "funding_need": {
                "need_type": finance["funding_need_type"],
                "requested_amount": finance["requested_amount"],
                "tenor": finance["tenor"],
                "basis": f"Contract {contract_id}",
            },
        }

    async def main():
        contract_ids = get_mock_contract_ids()
        cases = [build_credit_decision_case(contract_id) for contract_id in contract_ids]

        # Gửi toàn bộ cases trong một input và chỉ gọi agent một lần.
        user_input = (
            "Đây là toàn bộ credit decision cases cần đánh giá. "
            "Hãy xử lý độc lập từng case và trả đúng một Decision Card cho mỗi "
            "contract_id, theo đúng thứ tự đầu vào:\n"
            f"{json.dumps(cases, ensure_ascii=False, indent=2)}"
        )
        run_id = str(uuid.uuid4())
        context = AppContext(
            document_id=run_id,
            original_input=user_input,
            run_id=run_id,
        )

        print(f"Đang xử lý {len(cases)} contracts trong một agent run: {contract_ids}")
        result = await Runner.run(
            DecisionAgent,
            input=user_input,
            context=context,
            max_turns=20,
        )

        returned_ids = [decision.contract_id for decision in result.final_output.decisions]
        if returned_ids != contract_ids:
            raise RuntimeError(
                "Agent returned an incomplete or incorrectly ordered batch: "
                f"expected={contract_ids}, returned={returned_ids}"
            )

        for index, decision in enumerate(result.final_output.decisions, start=1):
            print(f"\n{'=' * 60}")
            print(f"DECISION {index}/{len(contract_ids)}: {decision.contract_id}")
            print(f"{'=' * 60}")
            print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))

    asyncio.run(main())
