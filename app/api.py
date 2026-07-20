from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import os

from app.schema.pipeline_input import ContractUploadPackage
from app.service.pipeline_service import (
    start_pipeline_run, stream_run_events, get_run_result,
    list_pending_approvals, submit_approval, list_processed_contracts,
    list_contract_overviews, get_decision_cards,
)

app = FastAPI(title="MIS Talent — Agent Pipeline API")

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
    return await list_processed_contracts(limit=limit, offset=offset, latest_only=latest_only)

@app.get("/contracts/overview")                            # JSON gọn: tên, giá trị, ngày, đề xuất
async def contract_overviews(limit: int = 100, offset: int = 0, latest_only: bool = True):
    return await list_contract_overviews(limit=limit, offset=offset, latest_only=latest_only)

@app.post("/runs")
async def create_run(contract: ContractUploadPackage | None = None):
    # Có body -> chạy 1 hợp đồng upload. Bỏ trống -> chạy CẢ LÔ hợp đồng có sẵn
    # trong database thật. Không có fallback mock.
    payload = contract.model_dump(mode="json") if contract is not None else None
    return await start_pipeline_run(contract=payload)

@app.get("/runs/{session_id}/events")                      # SSE cho dashboard
async def run_events(session_id: int):
    async def gen():
        async for ev in stream_run_events(session_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/runs/{session_id}")
async def run_result(session_id: int):
    return await get_run_result(session_id)

@app.get("/runs/{session_id}/decision")                    # Decision Card đầy đủ + reasons
async def run_decision(session_id: int):
    return await get_decision_cards(session_id)

@app.get("/runs/{session_id}/approvals")
async def approvals(session_id: int):
    return await list_pending_approvals(session_id)

@app.post("/runs/{session_id}/approvals/{approval_id}")    # founder duyệt
async def approve(session_id: int, approval_id: str, approved: bool):
    return await submit_approval(session_id, approval_id, approved)
