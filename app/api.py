from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import logging
import os

from app.schema.pipeline_input import ContractUploadPackage
from app.service.approval import ApprovalExecutionError
from app.service.pipeline_service import (
    start_pipeline_run, stream_run_events, get_run_result,
    list_pending_approvals, submit_approval, list_processed_contracts,
    list_contract_overviews, get_decision_cards,
)

app = FastAPI(title="MIS Talent — Agent Pipeline API")
logger = logging.getLogger("uvicorn.error")


def _pipeline_service():
    """Load agent dependencies only for endpoints that actually use them."""
    from app.service import pipeline_service

    return pipeline_service

# Cho phép FE (React) gọi API + SSE từ origin khác. Dev: mặc định cho tất cả;
# production đặt CORS_ORIGINS="https://your-fe.com,https://..." trong .env.
_origins = os.getenv("CORS_ORIGINS", "*").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_credentials=_origins != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/contracts")                                     # dashboard: hợp đồng đã xử lí (đầy đủ)
async def processed_contracts(limit: int = 100, offset: int = 0, latest_only: bool = True):
    return await _pipeline_service().list_processed_contracts(
        limit=limit,
        offset=offset,
        latest_only=latest_only,
    )

@app.get("/contracts/overview")                            # JSON gọn: tên, giá trị, ngày, đề xuất
async def contract_overviews(limit: int = 100, offset: int = 0, latest_only: bool = True):
    return await _pipeline_service().list_contract_overviews(
        limit=limit,
        offset=offset,
        latest_only=latest_only,
    )

@app.get("/dashboard")
async def dashboard_data(limit: int = 100, offset: int = 0, latest_only: bool = True):
    """Bootstrap contracts, metrics and approvals with one browser request."""
    return await _pipeline_service().get_dashboard_data(
        limit=limit,
        offset=offset,
        latest_only=latest_only,
    )

@app.post("/contracts/validate")
async def validate_contract(contract: ContractUploadPackage):
    """Validate and echo a form payload without starting or persisting a run."""
    payload = contract.model_dump(mode="json")
    logger.info("Received contract form payload: contract_id=%s", contract.contract_id)
    return {
        "received": True,
        "message": "Contract payload received and validated",
        "contract": payload,
    }

@app.post("/runs")
async def create_run(contract: ContractUploadPackage | None = None):
    # Có body -> chạy 1 hợp đồng upload. Bỏ trống -> chạy CẢ LÔ hợp đồng có sẵn
    # trong database thật. Không có fallback mock.
    payload = contract.model_dump(mode="json") if contract is not None else None
    return await _pipeline_service().start_pipeline_run(contract=payload)

@app.post("/runs/validated")                               # chạy pipeline CÓ CỔNG QC
async def create_validated_run(contract: ContractUploadPackage | None = None):
    # Finance → Validate → Risk → Validate → Decision → Validate. Dừng tại cổng đầu
    # tiên không PASS. Validation event phát trên cùng session_id (xem qua SSE).
    payload = contract.model_dump(mode="json") if contract is not None else None
    return await _pipeline_service().start_validated_pipeline_run(contract=payload)

@app.get("/runs/{session_id}/events")                      # SSE cho dashboard
async def run_events(session_id: int):
    async def gen():
        async for ev in _pipeline_service().stream_run_events(session_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/dashboard/events")
async def dashboard_events():
    """Notify the dashboard after a pipeline result is persisted."""
    async def gen():
        async for ev in _pipeline_service().stream_dashboard_events():
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/runs/{session_id}")
async def run_result(session_id: int):
    return await _pipeline_service().get_run_result(session_id)

@app.get("/runs/{session_id}/decision")                    # Decision Card đầy đủ + reasons
async def run_decision(session_id: int):
    return await _pipeline_service().get_decision_cards(session_id)

@app.get("/runs/{session_id}/detail")
async def run_detail(session_id: int):
    return await _pipeline_service().get_run_detail(session_id)

@app.get("/runs/{session_id}/validations")                 # ValidationReport của validator
async def run_validations(session_id: int):
    return await _pipeline_service().get_validation_reports(session_id)

@app.get("/runs/{session_id}/approvals")
async def approvals(session_id: int):
    return await _pipeline_service().list_pending_approvals(session_id)

@app.post("/runs/{session_id}/approvals/{approval_id}")    # founder duyệt
async def approve(session_id: int, approval_id: str, approved: bool):
    try:
        return await submit_approval(session_id, approval_id, approved)
    except ApprovalExecutionError as exc:
        status_code = (
            422 if exc.execution_error.startswith("ValueError:") else 502
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": "BANK_PRECHECK_EXECUTION_FAILED",
                "contract_id": exc.contract_id,
                "approval_id": exc.approval_id,
                "message": exc.execution_error,
            },
        ) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVAL_DECISION_REJECTED",
                "message": str(exc),
            },
        ) from exc
