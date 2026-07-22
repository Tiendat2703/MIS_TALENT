from dataclasses import dataclass, field
from typing import Any, Literal

from agents import Agent, RunContextWrapper
from agents.lifecycle import AgentHooks

from app.Agent.bus import event_bus


@dataclass
class AppContext:
    """Local dependency container shared by every agent in one pipeline run.

    ``run_id`` is the bigint ``public.context.session_id``.  SDK handoffs only
    transmit that id; the mutable dictionaries below stay local to the Runner
    and are never used as the inter-agent source of truth.
    """

    document_id: str
    original_input: str
    run_id: int
    contract_id: str | None = None
    contract_ids: list[str] = field(default_factory=list)
    contract_lifecycle: str | None = None
    contract_lifecycles: dict[str, str] = field(default_factory=dict)
    reference_date: str | None = None
    scenario: str | None = None
    finance_store: dict[str, Any] = field(default_factory=dict)
    brain_request_payload: dict[str, Any] | None = None
    continuation_approval_id: str | None = None


TOOL_LABELS = {
    "tool_retrieve_document": "Read strategy document",
    "tool_retrieve_fomularRule": "Read rule package",
    "fetch_futures_ohlcv_field_series": "Fetch OHLCV data",
    "calculate_exponential_moving_average": "Calculate EMA",
    "place_market_order": "Place market order",
    "place_limit_order": "Place limit order",
    "build_risk_pack": "Analyze risks and build Risk Pack",
    "save_risk_pack": "Save Risk Pack to workflow context",
    "prepare_finance_handoff": "Persist Finance Batch Pack",
    "process_risk_context": "Build and persist Risk Batch Pack",
    "load_decision_context": "Load Finance, Risk, and Credit Profiles",
    "list_bank_products": "Read bank product catalog",
    "precheck_performance_bond": "Prepare performance-bond precheck",
    "precheck_trade_finance": "Prepare trade-finance precheck",
    "precheck_micro_credit": "Prepare working-capital precheck",
    "load_service_catalog": "Read service catalog",
    "load_and_validate": "Load and validate Finance data",
    "reconcile_bank": "Reconcile invoices and bank transactions",
    "liquidity_funding": "Analyze liquidity and funding need",
    "classify_invoice": "Classify invoice status",
    "margin_analysis": "Analyze contract and order margins",
    "missing_data": "Identify missing Finance evidence",
    "load_validation_evidence": "Load Validator evidence",
}


DataSourceKind = Literal[
    "supabase_table",
    "runtime_log",
    "runtime_store",
]
DataAccess = Literal["read", "write", "read_write"]


@dataclass(frozen=True)
class ToolDataSource:
    """One declared data dependency shown in realtime agent logs.

    This registry describes the governed source used by a tool. It deliberately
    distinguishes real Supabase tables (including ``public.context``) from
    local runtime stores so the UI never presents a file as a database table.
    """

    label: str
    name: str
    kind: DataSourceKind = "supabase_table"
    access: DataAccess = "read"

    def as_event_payload(self) -> dict[str, str]:
        return {
            "label": self.label,
            "name": self.name,
            "kind": self.kind,
            "access": self.access,
        }


def _table(label: str, name: str, access: DataAccess = "read") -> ToolDataSource:
    return ToolDataSource(label=label, name=name, access=access)


FINANCE_INPUT_SOURCES = (
    _table("04_CONTRACTS", "contract"),
    _table("06_ORDERS", "orders"),
    _table("07_INVOICES", "invoice"),
    _table("08_BANK_TXN", "bank_txn"),
    _table("09_CASHFLOW", "cashflow"),
    _table("02_OPC_PROFILE", "company"),
    _table("03_CUSTOMERS", "customer"),
    _table("05_PRODUCTS", "service"),
)

WORKFLOW_CONTEXT_READ = _table("CONTEXT", "context")
WORKFLOW_CONTEXT_WRITE = _table("CONTEXT", "context", "write")
WORKFLOW_CONTEXT_READ_WRITE = _table("CONTEXT", "context", "read_write")
RUNTIME_LOG_SOURCE = ToolDataSource(
    label="AGENT_RUNTIME_LOG",
    name="logs/agent_runs/{run_id}.json",
    kind="runtime_log",
    access="read",
)
APPROVAL_STATE_SOURCE = ToolDataSource(
    label="HITL_APPROVAL_STATE",
    name="data/pending_states/{run_id}.json",
    kind="runtime_store",
    access="read_write",
)


TOOL_DATA_SOURCES: dict[str, tuple[ToolDataSource, ...]] = {
    # Finance tools consume the immutable run snapshot preloaded from Supabase.
    "load_service_catalog": (_table("05_PRODUCTS", "service"),),
    "load_and_validate": FINANCE_INPUT_SOURCES,
    "reconcile_bank": (
        _table("07_INVOICES", "invoice"),
        _table("08_BANK_TXN", "bank_txn"),
    ),
    "liquidity_funding": (
        _table("09_CASHFLOW", "cashflow"),
        _table("02_OPC_PROFILE", "company"),
    ),
    "classify_invoice": (_table("07_INVOICES", "invoice"),),
    "margin_analysis": (
        _table("06_ORDERS", "orders"),
        _table("04_CONTRACTS", "contract"),
        _table("02_OPC_PROFILE", "company"),
        _table("05_PRODUCTS", "service"),
    ),
    "missing_data": (
        _table("06_ORDERS", "orders"),
        _table("07_INVOICES", "invoice"),
        _table("08_BANK_TXN", "bank_txn"),
    ),
    "prepare_finance_handoff": (WORKFLOW_CONTEXT_WRITE,),
    # Risk reads authoritative rule/evidence tables and persists its pack.
    "process_risk_context": (
        WORKFLOW_CONTEXT_READ_WRITE,
        _table("13_RISK_RULES", "risk_rule"),
        _table("14_ALERTS", "alert"),
        _table("08_BANK_TXN", "bank_txn"),
        _table("06_ORDERS", "orders"),
        _table("15_DATA_CLASS", "data_class"),
        _table("16_MASKING_EXAMPLES", "masking_example"),
    ),
    "build_risk_pack": (
        _table("13_RISK_RULES", "risk_rule"),
        _table("14_ALERTS", "alert"),
        _table("08_BANK_TXN", "bank_txn"),
        _table("06_ORDERS", "orders"),
        _table("15_DATA_CLASS", "data_class"),
        _table("16_MASKING_EXAMPLES", "masking_example"),
    ),
    "get_risk_rules": (_table("13_RISK_RULES", "risk_rule"),),
    "get_alerts": (_table("14_ALERTS", "alert"),),
    "get_data_classes": (_table("15_DATA_CLASS", "data_class"),),
    "get_masking_examples": (
        _table("16_MASKING_EXAMPLES", "masking_example"),
    ),
    "save_risk_pack": (WORKFLOW_CONTEXT_WRITE,),
    # Decision uses persisted packs plus authoritative credit/product catalogs.
    "load_decision_context": (
        WORKFLOW_CONTEXT_READ,
        _table("10_CREDIT_PROFILE", "credit_profile"),
    ),
    "list_bank_products": (_table("11_BANK_PRODUCTS", "bank_product"),),
    # These tools use the local human-approval state and deterministic demo
    # adapter; they do not read a Supabase table.
    "precheck_performance_bond": (APPROVAL_STATE_SOURCE,),
    "precheck_trade_finance": (APPROVAL_STATE_SOURCE,),
    "precheck_micro_credit": (APPROVAL_STATE_SOURCE,),
    # Validator reads the persisted pack plus the event-bus snapshot.
    "load_validation_evidence": (
        WORKFLOW_CONTEXT_READ,
        RUNTIME_LOG_SOURCE,
    ),
}


def get_tool_trace_metadata(tool_name: str) -> dict[str, list[dict[str, str]]]:
    """Return a fresh JSON-safe source list for one tool event."""
    return {
        "data_sources": [
            source.as_event_payload()
            for source in TOOL_DATA_SOURCES.get(tool_name, ())
        ]
    }


class CustomAgentHooks(AgentHooks):
    def __init__(self, display_name: str | None = None):
        self.display_name = display_name

    async def _emit(self, context: RunContextWrapper, payload: dict[str, Any]) -> None:
        run_id = str(context.context.run_id)
        print(
            f"[RUN {run_id}] "
            f"type={payload.get('type')} | "
            f"agent={payload.get('agent')} | "
            f"task={payload.get('task')} | "
            f"status={payload.get('status')}"
        )
        await event_bus.emit(run_id, payload)

    async def on_start(self, context: RunContextWrapper, agent: Agent) -> None:
        await self._emit(context, {
            "type": "agent_started",
            "agent": agent.name,
            "task": f"{agent.name} started",
            "status": "running",
        })

    async def on_end(self, context: RunContextWrapper, agent: Agent, output: Any) -> None:
        await self._emit(context, {
            "type": "agent_finished",
            "agent": agent.name,
            "task": f"{agent.name} completed",
            "status": "done",
            "summary": str(output)[:500],
        })

    async def on_handoff(self, context: RunContextWrapper, agent: Agent, source: Agent) -> None:
        await self._emit(context, {
            "type": "agent_handoff",
            "agent": source.name,
            "target_agent": agent.name,
            "task": f"Handoff from {source.name} to {agent.name}",
            "status": "done",
        })

    async def on_tool_start(self, context: RunContextWrapper, agent: Agent, tool) -> None:
        tool_name = tool.name
        await self._emit(context, {
            "type": "tool_started",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Run tool {tool_name}"),
            "status": "running",
            **get_tool_trace_metadata(tool_name),
        })

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool,
        result: object,
    ) -> None:
        tool_name = tool.name

        # ✅ Print đầu ra tool trực tiếp ra terminal
        print(f"\n{'='*60}")
        print(f"[TOOL OUTPUT] {tool_name}")
        print(f"[AGENT] {agent.name}")
        print(f"[RESULT]\n{result}")
        print(f"{'='*60}\n")

        await self._emit(context, {
            "type": "tool_finished",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Tool {tool_name} completed"),
            "status": "done",
            "summary": str(result)[:500],
            **get_tool_trace_metadata(tool_name),
        })
