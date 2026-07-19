"""Dump tên bảng + cột thật từ Supabase để cập nhật TABLES trong finance_data.py.

Chạy khi đã có app/.env với thông tin Supabase:
    python -m app.tools.FinanceAgent.dump_schema

In ra mỗi bảng trong schema 'public' kèm danh sách cột và kiểu dữ liệu.
"""

from __future__ import annotations

from app.database.repository import query_db

_QUERY = """
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position
"""


def main() -> None:
    rows = query_db(_QUERY)
    if not rows:
        print("Không có bảng nào trong schema 'public'.")
        return

    tables: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        tables.setdefault(r["table_name"], []).append((r["column_name"], r["data_type"]))

    for table, cols in tables.items():
        print(f"\n=== {table} ===")
        for name, dtype in cols:
            print(f"  {name}: {dtype}")


if __name__ == "__main__":
    main()
