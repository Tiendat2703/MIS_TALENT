from types import SimpleNamespace

import pytest

from app.Agent import hooks


def _source_names(tool_name: str) -> set[str]:
    metadata = hooks.get_tool_trace_metadata(tool_name)
    return {source["name"] for source in metadata["data_sources"]}


def test_finance_tool_declares_only_its_business_table_dependencies() -> None:
    assert _source_names("reconcile_bank") == {"invoice", "bank_txn"}


def test_risk_tool_declares_authoritative_tables_and_context_write() -> None:
    metadata = hooks.get_tool_trace_metadata("process_risk_context")
    sources = metadata["data_sources"]

    assert _source_names("process_risk_context") == {
        "context",
        "risk_rule",
        "alert",
        "bank_txn",
        "orders",
        "data_class",
        "masking_example",
    }
    assert {
        source["name"]: (source["kind"], source["access"])
        for source in sources
    }["context"] == ("supabase_table", "read_write")


def test_unknown_tool_keeps_a_stable_empty_source_list() -> None:
    assert hooks.get_tool_trace_metadata("unknown_tool") == {"data_sources": []}


@pytest.mark.asyncio
async def test_tool_start_and_finish_emit_the_same_trace_metadata(monkeypatch) -> None:
    emitted: list[dict] = []

    async def fake_emit(run_id, payload) -> None:
        assert run_id == "42"
        emitted.append(payload)

    monkeypatch.setattr(hooks.event_bus, "emit", fake_emit)
    lifecycle = hooks.CustomAgentHooks()
    context = SimpleNamespace(context=SimpleNamespace(run_id=42))
    agent = SimpleNamespace(name="Decision_Agent")
    tool = SimpleNamespace(name="list_bank_products")

    await lifecycle.on_tool_start(context, agent, tool)
    await lifecycle.on_tool_end(context, agent, tool, {"count": 2})

    assert [event["type"] for event in emitted] == [
        "tool_started",
        "tool_finished",
    ]
    assert emitted[0]["tool_name"] == "list_bank_products"
    assert emitted[0]["data_sources"] == emitted[1]["data_sources"]
    assert emitted[0]["data_sources"] == [
        {
            "label": "11_BANK_PRODUCTS",
            "name": "bank_product",
            "kind": "supabase_table",
            "access": "read",
        }
    ]
