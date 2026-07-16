import os

import requests
from agents import function_tool


def _response(score: int, note: str) -> dict:
    return {
        "eli": score >= 70,
        "score": score,
        "note": note,
    }


def _call_api(
    base_url: str | None,
    endpoint: str,
    payload: dict,
    mock_response: dict,
) -> dict:
    try:
        if not base_url:
            raise ValueError("API base URL is not configured")

        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}",
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return mock_response


@function_tool
def precheck_performance_bond(
    contract_id: str,
    amount: float,
    company_profile: str,
) -> dict:
    """Gọi API kiểm tra bảo lãnh; trả mock nếu API chưa khả dụng."""
    endpoint = "/openapi/v1/guarantee/precheck"
    payload = {
        "contract_id": contract_id,
        "amount": amount,
        "company_profile": company_profile,
    }

    if not contract_id or not company_profile or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu thông tin hợp đồng hoặc doanh nghiệp.",
        )
    elif amount > 1_000_000_000:
        mock_response = _response(
            60,
            "Hồ sơ cần thẩm định thêm vì số tiền bảo lãnh cao.",
        )
    else:
        mock_response = _response(85, "Hồ sơ đầy đủ và đủ điều kiện sơ bộ.")

    return _call_api(
        os.getenv("VIETINBANK_API_BASE_URL"),
        endpoint,
        payload,
        mock_response,
    )


@function_tool
def precheck_trade_finance(
    contract_id: str,
    supplier_docs: list[str],
    amount: float,
) -> dict:
    """Gọi API kiểm tra LC; trả mock nếu API chưa khả dụng."""
    endpoint = "/openapi/v1/trade-finance/precheck"
    payload = {
        "contract_id": contract_id,
        "supplier_docs": supplier_docs,
        "amount": amount,
    }

    if not contract_id or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu thông tin hợp đồng hoặc số tiền đề nghị.",
        )
    elif len(supplier_docs) < 2:
        mock_response = _response(55, "Hồ sơ chưa đủ chứng từ nhà cung cấp.")
    else:
        mock_response = _response(
            88,
            "Hồ sơ đầy đủ và có thể chuyển sang bước thẩm định.",
        )

    return _call_api(
        os.getenv("VIETINBANK_API_BASE_URL"),
        endpoint,
        payload,
        mock_response,
    )


@function_tool
def precheck_micro_credit(
    customer_type: str,
    amount: float,
    receivable_list: list[str],
) -> dict:
    """Gọi API kiểm tra vay vốn nhỏ; trả mock nếu API chưa khả dụng."""
    endpoint = "/sandbox/v1/micro-credit/precheck"
    payload = {
        "customer_type": customer_type,
        "amount": amount,
        "receivable_list": receivable_list,
    }

    if not customer_type or amount <= 0:
        mock_response = _response(
            40,
            "Hồ sơ thiếu loại khách hàng hoặc số tiền vay.",
        )
    elif not receivable_list:
        mock_response = _response(50, "Hồ sơ chưa có danh sách khoản phải thu.")
    elif amount > 300_000_000:
        mock_response = _response(
            65,
            "Hồ sơ cần thẩm định thêm vì số tiền vay cao.",
        )
    else:
        mock_response = _response(
            82,
            "Hồ sơ đạt điều kiện sơ bộ cho khoản vay vốn lưu động.",
        )

    return _call_api(
        os.getenv("COOPBANK_API_BASE_URL"),
        endpoint,
        payload,
        mock_response,
    )


PRECHECK_TOOLS = [
    precheck_performance_bond,
    precheck_trade_finance,
    precheck_micro_credit,
]
