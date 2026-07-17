import json
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agents import function_tool
from psycopg2 import sql
from psycopg2.extras import Json

from app.Agent.bus import event_bus
from app.database.repository import query_db


DEFAULT_LOG_TABLE = "LogsAgent"
DB_LOG_COLUMNS = {
    "financelogs": "FinanceLogs",
    "risklogs": "RiskLogs",
    "decisionlog": "DecisionLogs",
    "validatorlogs": "ValidatorLogs",
}


def _normalize_log_value(value: Any) -> Any:
    """Store JSON strings as JSON values and ordinary strings as JSON strings."""
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _json_safe(value: Any) -> Any:
    return json.loads(
        json.dumps(value, ensure_ascii=False, default=_json_default)
    )


def build_decision_log_payload(run_id: str, response: Any) -> dict[str, Any]:
    """Combine the Decision response with hook events captured before this write."""
    snapshot = event_bus.get_snapshot(run_id)
    if snapshot is None:
        raise ValueError(f"No hook log snapshot found for run_id={run_id}")

    normalized_response = _normalize_log_value(response)
    if (
        isinstance(normalized_response, dict)
        and "response" in normalized_response
        and "decisions" not in normalized_response
    ):
        normalized_response = normalized_response["response"]

    return {
        "run_id": run_id,
        "capture_stage": "write_logs_started",
        "agent_log": _json_safe(snapshot),
        "response": _json_safe(normalized_response),
    }


def _to_db_value(value: Any) -> Any:
    if value is None:
        return None
    return Json(_normalize_log_value(value))


def _get_table_name() -> str:
    table_name = os.getenv("AGENT_LOG_TABLE", DEFAULT_LOG_TABLE).strip()
    if not table_name:
        raise ValueError("AGENT_LOG_TABLE must not be empty")
    return table_name


def _normalize_id(id: str) -> str:
    normalized_id = id.strip()
    if not normalized_id:
        raise ValueError("id must not be empty")
    return normalized_id


def upsert_agent_logs(
    id: str,
    financelogs: Any,
    risklogs: Any,
    decisionlog: Any,
    validatorlogs: Any,
) -> dict[str, Any]:
    """Upsert all four agent log columns for one shared run id."""
    normalized_id = _normalize_id(id)
    table_name = _get_table_name()
    column_identifiers = {
        key: sql.Identifier(value)
        for key, value in DB_LOG_COLUMNS.items()
    }

    statement = sql.SQL(
        """
        INSERT INTO {table} (
            id,
            {financelogs},
            {risklogs},
            {decisionlog},
            {validatorlogs}
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            {financelogs} = EXCLUDED.{financelogs},
            {risklogs} = EXCLUDED.{risklogs},
            {decisionlog} = EXCLUDED.{decisionlog},
            {validatorlogs} = EXCLUDED.{validatorlogs}
        RETURNING id
        """
    ).format(
        table=sql.Identifier(table_name),
        **column_identifiers,
    )

    rows = query_db(
        statement,
        (
            normalized_id,
            _to_db_value(financelogs),
            _to_db_value(risklogs),
            _to_db_value(decisionlog),
            _to_db_value(validatorlogs),
        ),
    )
    if not rows:
        raise RuntimeError("Agent log upsert completed without a returned row")

    return {
        "status": "upserted",
        "id": str(rows[0]["id"]),
        "table": table_name,
    }


def upsert_agent_logs_partial(
    id: str,
    *,
    financelogs: Any = None,
    risklogs: Any = None,
    decisionlog: Any = None,
    validatorlogs: Any = None,
) -> dict[str, Any]:
    """Upsert supplied logs while preserving existing logs owned by other agents."""
    normalized_id = _normalize_id(id)
    table_name = _get_table_name()
    values = {
        "financelogs": financelogs,
        "risklogs": risklogs,
        "decisionlog": decisionlog,
        "validatorlogs": validatorlogs,
    }
    supplied_columns = [
        key
        for key, value in values.items()
        if value is not None
    ]
    if not supplied_columns:
        raise ValueError("At least one agent log must be supplied")

    column_identifiers = {
        key: sql.Identifier(value)
        for key, value in DB_LOG_COLUMNS.items()
    }
    assignments = sql.SQL(", ").join(
        sql.SQL("{column} = EXCLUDED.{column}").format(
            column=column_identifiers[key]
        )
        for key in supplied_columns
    )
    statement = sql.SQL(
        """
        INSERT INTO {table} (
            id,
            {financelogs},
            {risklogs},
            {decisionlog},
            {validatorlogs}
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET {assignments}
        RETURNING id
        """
    ).format(
        table=sql.Identifier(table_name),
        assignments=assignments,
        **column_identifiers,
    )
    rows = query_db(
        statement,
        (
            normalized_id,
            *(_to_db_value(values[key]) for key in DB_LOG_COLUMNS),
        ),
    )
    if not rows:
        raise RuntimeError("Agent log upsert completed without a returned row")

    return {
        "status": "upserted",
        "id": str(rows[0]["id"]),
        "columns": [DB_LOG_COLUMNS[key] for key in supplied_columns],
        "table": table_name,
    }


@function_tool
def write_logs(
    id: str,
    financelogs: str | None,
    risklogs: str | None,
    decisionlog: str | None,
    validatorlogs: str | None,
) -> dict:
    """Upsert hook events and supplied agent responses by shared run id.

    Fields set to null are preserved when the id already exists. Each supplied
    field accepts a JSON-encoded string or ordinary text. DecisionLogs includes
    both the current event-bus snapshot and the supplied Decision response.
    """
    if decisionlog is not None:
        decisionlog = build_decision_log_payload(id, decisionlog)

    return upsert_agent_logs_partial(
        id=id,
        financelogs=financelogs,
        risklogs=risklogs,
        decisionlog=decisionlog,
        validatorlogs=validatorlogs,
    )


__all__ = [
    "build_decision_log_payload",
    "upsert_agent_logs",
    "upsert_agent_logs_partial",
    "write_logs",
]
