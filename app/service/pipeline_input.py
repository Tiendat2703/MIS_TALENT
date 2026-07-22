"""Load and merge an external contract package into a run-local portfolio."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.schema.pipeline_input import ContractUploadPackage


def load_contract_package(
    source: ContractUploadPackage | dict[str, Any] | str | Path,
) -> ContractUploadPackage:
    if isinstance(source, ContractUploadPackage):
        return source
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Contract upload package not found: {path}")
        return ContractUploadPackage.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    return ContractUploadPackage.model_validate(source)


def _upsert_run_local(rows: list[dict[str, Any]], key: str, row: dict[str, Any]) -> None:
    value = row[key]
    existing = next((item for item in rows if item.get(key) == value), None)
    if existing is None:
        rows.append(row)
    else:
        existing.clear()
        existing.update(row)


def merge_contract_package(
    base_data: dict[str, Any],
    package: ContractUploadPackage,
) -> dict[str, Any]:
    """Return a copy; never mutate or persist the normal database source rows."""
    data = deepcopy(base_data)
    _upsert_run_local(
        data["contracts"],
        "contract_id",
        package.model_dump(mode="json"),
    )
    # Lưu nguyên gói upload để Finance tính what-if dòng tiền (điều khoản thanh
    # toán, giá trị, mốc thời gian) cho hợp đồng mới này.
    data["upload"] = package.model_dump(mode="json")
    data["source"] = f"{base_data.get('source', 'unknown')}+upload"
    return data


def select_pipeline_scope(
    base_data: dict[str, Any],
    uploaded_contract: ContractUploadPackage | None = None,
    existing_contract_id: str | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    """Resolve batch, upload, or one existing-contract mode deterministically."""
    if uploaded_contract is not None and existing_contract_id is not None:
        raise ValueError("Choose either an uploaded contract or an existing contract_id")
    if uploaded_contract is not None:
        return (
            merge_contract_package(base_data, uploaded_contract),
            [uploaded_contract.contract_id],
            "upload",
        )

    contract_ids = [
        str(item["contract_id"])
        for item in base_data.get("contracts", [])
        if item.get("contract_id")
    ]
    if not contract_ids:
        raise ValueError("The normal data source contains no contracts")
    if len(contract_ids) != len(set(contract_ids)):
        raise ValueError("The normal data source contains duplicate contract_id values")
    if existing_contract_id is not None:
        normalized_id = existing_contract_id.strip()
        if normalized_id not in contract_ids:
            raise LookupError(
                f"Existing contract was not found in the database: {normalized_id}"
            )
        return base_data, [normalized_id], "existing_contract"
    return base_data, contract_ids, "automatic_batch"


__all__ = [
    "load_contract_package",
    "merge_contract_package",
    "select_pipeline_scope",
]
