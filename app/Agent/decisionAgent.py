import asyncio
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from agents import Agent, OpenAIChatCompletionsModel, RunContextWrapper, handoff, Runner 
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions
from app.tools.writeLogs import write_logs
from app.Agent.config import OPENAI_CLIENT, OPENAI_MODEL
from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext, CustomAgentHooks
from app.Agent.state_store import (
    commit_initial_result,
    initialize_approval_state,
)
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

DecisionAgent = Agent(
    name="Decision_Agent",
    model=OpenAIChatCompletionsModel(
        model=OPENAI_MODEL,
        openai_client=OPENAI_CLIENT,
    ),
    instructions=prompt_with_handoff_instructions(DECISION_AGENT_PROMPT),
    output_type=DecisionBatchOutput,
    tools=[
        match_bank_product,
        precheck_performance_bond,
        precheck_trade_finance,
        precheck_micro_credit,
        write_logs
    ],
    hooks= CustomAgentHooks("DecisionAgent"),
)

async def run_decision_agent(
    user_input: str,
    *,
    context: AppContext | None = None,
    expected_contract_ids: list[str] | None = None,
    run_metadata: dict[str, object] | None = None,
    max_turns: int = 20,
):
    """Run Decision Agent with complete JSON logging for every caller."""
    if context is None:
        run_id = str(uuid.uuid4())
        context = AppContext(
            document_id=run_id,
            original_input=user_input,
            run_id=run_id,
        )
    else:
        run_id = context.run_id
        context.original_input = user_input

    try:
        await initialize_approval_state(
            run_id,
            context,
            user_input,
            metadata=run_metadata,
        )

        agent_input = (
            "Execution context for mandatory logging:\n"
            f'{{"run_id": "{run_id}"}}\n\n'
            f"{user_input}"
        )
        result = await Runner.run(
            DecisionAgent,
            input=agent_input,
            context=context,
            max_turns=max_turns,
        )

        if result.interruptions:
            raise RuntimeError(
                "Unexpected SDK interruption: precheck tools must use StateStore gating"
            )

        if expected_contract_ids is not None:
            returned_ids = [
                decision.contract_id
                for decision in result.final_output.decisions
            ]
            if returned_ids != expected_contract_ids:
                raise RuntimeError(
                    "Agent returned an incomplete or incorrectly ordered batch: "
                    f"expected={expected_contract_ids}, returned={returned_ids}"
                )

        decision_result = asdict(result.final_output)
        state = await commit_initial_result(
            run_id,
            decision_result,
            result.to_input_list(mode="normalized"),
        )
        pending = [
            request
            for request in state["approval_requests"]
            if request["status"] == "pending"
        ]

        if pending:
            await event_bus.emit(run_id, {
                "type": "run_review",
                "agent": DecisionAgent.name,
                "task": "Đã hoàn tất Decision Card và đang chờ duyệt precheck",
                "status": "review",
                "data": {
                    "decision_result": decision_result,
                    "pending_approvals": pending,
                },
            })
        else:
            await event_bus.emit(run_id, {
                "type": "run_finished",
                "agent": DecisionAgent.name,
                "task": "Hoàn tất batch credit decision cases",
                "status": "done",
                "data": decision_result,
            })
        return result

    except asyncio.CancelledError:
        await asyncio.shield(event_bus.emit(run_id, {
            "type": "run_cancelled",
            "agent": DecisionAgent.name,
            "task": "Decision Agent bị dừng",
            "status": "cancelled",
            "data": {"message": "Run was cancelled before completion"},
        }))
        raise
    except Exception as exc:
        await event_bus.emit(run_id, {
            "type": "run_error",
            "agent": DecisionAgent.name,
            "task": "Decision Agent gặp lỗi",
            "status": "error",
            "data": {
                "error_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
        })
        raise
    finally:
        if event_bus.get_snapshot(run_id) is not None:
            log_path = event_bus.persist_snapshot(run_id)
            print(f"Agent log saved to: {log_path}")

if __name__ == "__main__":
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

        print(f"Đang xử lý {len(cases)} contracts trong một agent run: {contract_ids}")
        result = await run_decision_agent(
            user_input,
            expected_contract_ids=contract_ids,
            run_metadata={
                "contract_ids": contract_ids,
                "input_cases": cases,
            },
        )

        for index, decision in enumerate(result.final_output.decisions, start=1):
            print(f"\n{'=' * 60}")
            print(f"DECISION {index}/{len(contract_ids)}: {decision.contract_id}")
            print(f"{'=' * 60}")
            print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))

    asyncio.run(main())