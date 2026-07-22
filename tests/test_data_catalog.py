"""Read-only data catalog and targeted workflow contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from psycopg2 import sql

from app.api import app
from app.service import data_catalog_service, pipeline_service


client = TestClient(app)


def test_catalog_exposes_exactly_twenty_six_unique_tables() -> None:
    names = [table["name"] for table in data_catalog_service.CATALOG_TABLES]
    labels = [table["label"] for table in data_catalog_service.CATALOG_TABLES]

    assert len(names) == 26
    assert len(names) == len(set(names))
    assert len(labels) == len(set(labels))
    assert "contract" in names


def test_catalog_list_keeps_declared_order_and_hides_missing_tables(
    monkeypatch,
) -> None:
    available = [
        {"table_name": table["name"]}
        for table in data_catalog_service.CATALOG_TABLES
        if table["name"] != "public_test"
    ]
    monkeypatch.setattr(data_catalog_service, "query_db", lambda *_args: available)

    payload = data_catalog_service.list_catalog_tables()

    assert payload["count"] == 25
    assert payload["tables"][0]["name"] == "dataset_guide"
    assert payload["tables"][3]["label"] == "04_CONTRACTS"
    assert "public_test" not in {table["name"] for table in payload["tables"]}


def test_catalog_reads_only_an_allowlisted_table(monkeypatch) -> None:
    calls: list[object] = []

    def fake_query(query, _params=None):
        calls.append(query)
        if isinstance(query, str) and "information_schema.tables" in query:
            return [{"table_name": "contract"}]
        if isinstance(query, sql.Composed):
            return [{"contract_id": "CON-025", "contract_value": 420_000_000}]
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(data_catalog_service, "query_db", fake_query)

    payload = data_catalog_service.read_catalog_table("contract")

    assert payload["table"]["label"] == "04_CONTRACTS"
    assert payload["columns"] == ["contract_id", "contract_value"]
    assert payload["count"] == 1
    assert payload["rows"][0]["contract_id"] == "CON-025"
    assert any(isinstance(query, sql.Composed) for query in calls)


def test_catalog_rejects_a_table_outside_the_allowlist(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Database must not be queried for a hidden table")

    monkeypatch.setattr(data_catalog_service, "query_db", fail_if_called)

    try:
        data_catalog_service.read_catalog_table("LogsAgent")
    except KeyError as exc:
        assert "not available" in str(exc)
    else:
        raise AssertionError("A hidden table was accepted")


def test_contract_options_use_available_customer_name_fields(monkeypatch) -> None:
    def fake_query(query, _params=None):
        if isinstance(query, str) and "information_schema.tables" in query:
            return [{"table_name": "contract"}]
        if "public.contract" in query:
            return [{
                "contract_id": "CON-025",
                "customer_id": "CUS-004",
                "description": "Performance bond",
            }]
        if "public.customer" in query:
            return [{"customer_id": "CUS-004", "legal_name": "Công ty ABC"}]
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(data_catalog_service, "query_db", fake_query)

    payload = data_catalog_service.list_contract_options()

    assert payload == {
        "contracts": [{
            "contract_id": "CON-025",
            "customer_id": "CUS-004",
            "customer_name": "Công ty ABC",
            "description": "Performance bond",
        }],
        "count": 1,
    }


def test_validated_run_endpoint_targets_selected_database_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_start_validated_pipeline_run(**kwargs):
        captured.update(kwargs)
        return {
            "session_id": 208,
            "status": "running",
            "gated": True,
            "contract_id": kwargs["existing_contract_id"],
        }

    monkeypatch.setattr(
        pipeline_service,
        "start_validated_pipeline_run",
        fake_start_validated_pipeline_run,
    )

    response = client.post(
        "/runs/validated",
        params={"contract_id": "CON-025"},
    )

    assert response.status_code == 200
    assert response.json()["contract_id"] == "CON-025"
    assert captured == {"contract": None, "existing_contract_id": "CON-025"}


def test_validated_run_rejects_upload_and_existing_contract_together() -> None:
    response = client.post(
        "/runs/validated",
        params={"contract_id": "CON-025"},
        json={"contract_id": "CON-UPLOAD-001"},
    )

    assert response.status_code == 400
    assert "either" in response.json()["detail"]
