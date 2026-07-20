"""Entry point chạy API bằng uvicorn.

    python -m app.main
    # hoặc trực tiếp:
    uvicorn app.api:app --reload --host 0.0.0.0 --port 8080

Cấu hình qua env (tùy chọn): API_HOST, API_PORT, API_RELOAD.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.api:app",  # dạng chuỗi để bật được reload khi dev
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8080")),
        reload=os.getenv("API_RELOAD", "true").strip().lower() == "true",
    )


if __name__ == "__main__":
    main()
