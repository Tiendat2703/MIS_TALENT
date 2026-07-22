"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { API_REQUEST_HEADERS, apiUrl } from "@/lib/api";
import { ACTIVE_RUN_STORAGE_KEY } from "@/lib/run-session";

type CatalogTable = {
  name: string;
  label: string;
  description: string;
};

type ContractOption = {
  contract_id: string;
  customer_id: string | null;
  customer_name: string | null;
  description: string | null;
};

type TableData = {
  table: CatalogTable;
  columns: string[];
  rows: Record<string, unknown>[];
  count: number;
  loaded_at: string;
};

type TableListResponse = {
  tables: CatalogTable[];
  count: number;
};

type ContractListResponse = {
  contracts: ContractOption[];
  count: number;
};

type ApiError = {
  detail?: string;
};

const CONTRACT_TABLE_NAME = "contract";

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Trống";
  if (typeof value === "boolean") return value ? "Có" : "Không";
  if (typeof value === "number") return new Intl.NumberFormat("vi-VN").format(value);
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function formatSyncTime(value?: string): string {
  if (!value) return "chưa đồng bộ";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "không xác định";

  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function contractLabel(contract: ContractOption): string {
  const party = contract.customer_name || contract.customer_id || contract.description;
  return party ? `${contract.contract_id} · ${party}` : contract.contract_id;
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({})) as T & ApiError;
  if (!response.ok) {
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : `Không thể tải dữ liệu (HTTP ${response.status}).`,
    );
  }
  return payload;
}

export function TeamPackWorkspace() {
  const router = useRouter();
  const [tables, setTables] = useState<CatalogTable[]>([]);
  const [contracts, setContracts] = useState<ContractOption[]>([]);
  const [selectedTable, setSelectedTable] = useState(CONTRACT_TABLE_NAME);
  const [selectedContractId, setSelectedContractId] = useState("");
  const [tableData, setTableData] = useState<TableData | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(true);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [catalogError, setCatalogError] = useState("");
  const [tableError, setTableError] = useState("");
  const [startError, setStartError] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const selectedRowRef = useRef<HTMLTableRowElement | null>(null);

  const selectedContract = useMemo(
    () => contracts.find((contract) => contract.contract_id === selectedContractId) ?? null,
    [contracts, selectedContractId],
  );

  const loadCatalog = useCallback(async (signal?: AbortSignal) => {
    try {
      const [tableResponse, contractResponse] = await Promise.all([
        fetch(apiUrl("/data-catalog/tables"), {
          cache: "no-store",
          headers: { Accept: "application/json", ...API_REQUEST_HEADERS },
          signal,
        }),
        fetch(apiUrl("/data-catalog/contracts"), {
          cache: "no-store",
          headers: { Accept: "application/json", ...API_REQUEST_HEADERS },
          signal,
        }),
      ]);
      const [tablePayload, contractPayload] = await Promise.all([
        readJson<TableListResponse>(tableResponse),
        readJson<ContractListResponse>(contractResponse),
      ]);
      setTables(tablePayload.tables);
      setContracts(contractPayload.contracts);
    } catch (error) {
      if (signal?.aborted) return;
      setCatalogError(error instanceof Error ? error.message : "Không thể tải danh mục Supabase.");
    } finally {
      if (!signal?.aborted) setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const requestId = window.setTimeout(() => {
      void loadCatalog(controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(requestId);
      controller.abort();
    };
  }, [loadCatalog]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadTable() {
      setTableLoading(true);
      setTableError("");
      try {
        const response = await fetch(
          apiUrl(`/data-catalog/tables/${encodeURIComponent(selectedTable)}`),
          {
            cache: "no-store",
            headers: { Accept: "application/json", ...API_REQUEST_HEADERS },
            signal: controller.signal,
          },
        );
        const payload = await readJson<TableData>(response);
        if (!controller.signal.aborted) setTableData(payload);
      } catch (error) {
        if (controller.signal.aborted) return;
        setTableData(null);
        setTableError(error instanceof Error ? error.message : "Không thể tải bảng dữ liệu.");
      } finally {
        if (!controller.signal.aborted) setTableLoading(false);
      }
    }

    void loadTable();
    return () => controller.abort();
  }, [refreshVersion, selectedTable]);

  useEffect(() => {
    if (
      selectedTable !== CONTRACT_TABLE_NAME
      || !selectedContractId
      || tableLoading
      || !selectedRowRef.current
    ) return;

    selectedRowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedContractId, selectedTable, tableData, tableLoading]);

  const handleContractChange = (contractId: string) => {
    setSelectedContractId(contractId);
    setStartError("");
    if (contractId) setSelectedTable(CONTRACT_TABLE_NAME);
  };

  const handleRefresh = () => {
    setRefreshVersion((version) => version + 1);
    if (selectedTable === CONTRACT_TABLE_NAME) {
      setCatalogLoading(true);
      setCatalogError("");
      const controller = new AbortController();
      void loadCatalog(controller.signal);
    }
  };

  const startEvaluation = async () => {
    if (!selectedContractId || isStarting) return;
    setIsStarting(true);
    setStartError("");

    try {
      const response = await fetch(
        apiUrl(`/runs/validated?contract_id=${encodeURIComponent(selectedContractId)}`),
        {
          method: "POST",
          headers: { Accept: "application/json", ...API_REQUEST_HEADERS },
        },
      );
      const payload = await readJson<{ session_id?: number }>(response);
      if (typeof payload.session_id !== "number") {
        throw new Error("API không trả về session_id hợp lệ.");
      }

      window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(payload.session_id));
      router.push("/agent");
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "Không thể bắt đầu đánh giá.");
      setIsStarting(false);
    }
  };

  const tableTitle = tableData?.table.label
    || tables.find((table) => table.name === selectedTable)?.label
    || (selectedTable === CONTRACT_TABLE_NAME ? "04_CONTRACTS" : selectedTable);
  const catalogStatus = catalogLoading
    ? "Đang kết nối Supabase"
    : catalogError
      ? "Mất kết nối Supabase"
      : `${tables.length} bảng Supabase`;

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      <header className="mb-6 border-b border-[var(--fin-soft-border)] pb-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-500">Team Pack</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">Kho dữ liệu hợp đồng</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--fin-muted)]">
          Kiểm tra dữ liệu đã nạp từ Supabase và chọn một hợp đồng để chạy quy trình đánh giá AI Agent.
        </p>
      </header>

      <section className="grid min-h-[680px] overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] lg:grid-cols-[310px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--fin-soft-border)] p-5 lg:border-b-0 lg:border-r lg:p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--fin-muted)]">Kho dữ liệu</p>
              <p className="mt-1 text-sm font-medium">{catalogStatus}</p>
            </div>
            <span
              className={`size-2 rounded-full ${catalogLoading ? "bg-amber-400" : catalogError ? "bg-rose-400" : "bg-emerald-400"}`}
              aria-label={catalogStatus}
            />
          </div>

          <div className="mt-8">
            <label htmlFor="catalog-table" className="text-sm font-medium">Chọn bảng dữ liệu</label>
            <select
              id="catalog-table"
              value={selectedTable}
              onChange={(event) => setSelectedTable(event.target.value)}
              disabled={catalogLoading || tables.length === 0}
              className="mt-2 min-h-11 w-full rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-bg)] px-3 text-sm text-[var(--fin-text)] outline-none transition focus:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {tables.length === 0 && <option value={CONTRACT_TABLE_NAME}>04_CONTRACTS · Hợp đồng</option>}
              {tables.map((table) => (
                <option key={table.name} value={table.name}>{table.label} · {table.description}</option>
              ))}
            </select>
          </div>

          <div className="mt-6">
            <label htmlFor="catalog-contract" className="text-sm font-medium">Chọn hợp đồng cần xử lý</label>
            <select
              id="catalog-contract"
              value={selectedContractId}
              onChange={(event) => handleContractChange(event.target.value)}
              disabled={catalogLoading}
              className="mt-2 min-h-11 w-full rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-bg)] px-3 text-sm text-[var(--fin-text)] outline-none transition focus:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <option value="">Chỉ xem dữ liệu</option>
              {contracts.map((contract) => (
                <option key={contract.contract_id} value={contract.contract_id}>{contractLabel(contract)}</option>
              ))}
            </select>
            <p className="mt-2 text-xs leading-5 text-[var(--fin-muted)]">
              Chọn hợp đồng sẽ mở lại 04_CONTRACTS và làm nổi bật bản ghi tương ứng.
            </p>
          </div>

          {catalogError && (
            <div role="alert" className="mt-5 rounded-lg border border-rose-400/25 bg-rose-400/[0.06] p-3 text-sm leading-5 text-rose-300">
              {catalogError}
            </div>
          )}

          {selectedContract && (
            <div className="mt-8 border-t border-[var(--fin-soft-border)] pt-5">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-[var(--fin-muted)]">Hợp đồng đang chọn</p>
              <p className="mt-2 font-mono text-base font-semibold text-emerald-400">{selectedContract.contract_id}</p>
              <p className="mt-1 text-sm leading-5 text-[var(--fin-muted)]">
                {selectedContract.customer_name || selectedContract.customer_id || selectedContract.description || "Không có mô tả"}
              </p>

              <button
                type="button"
                onClick={startEvaluation}
                disabled={isStarting}
                className="mt-5 min-h-11 w-full rounded-lg bg-emerald-400 px-4 text-sm font-semibold text-emerald-950 transition hover:bg-emerald-300 active:translate-y-px disabled:cursor-wait disabled:bg-emerald-900 disabled:text-emerald-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--fin-surface)]"
              >
                {isStarting ? "Đang khởi tạo đánh giá..." : "Bắt đầu đánh giá"}
              </button>

              {startError && <p role="alert" className="mt-3 text-sm leading-5 text-rose-300">{startError}</p>}
            </div>
          )}
        </aside>

        <div className="flex min-w-0 flex-col p-4 sm:p-6">
          <div className="flex flex-col gap-4 border-b border-[var(--fin-soft-border)] pb-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-lg font-semibold tracking-[-0.02em]">{tableTitle}</p>
              <p className="mt-1 text-sm text-[var(--fin-muted)]">Dữ liệu được tải từ Supabase</p>
            </div>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={tableLoading}
              className="min-h-10 rounded-lg border border-[var(--fin-soft-border)] px-4 text-sm font-medium transition hover:border-emerald-500 hover:text-emerald-400 disabled:cursor-wait disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              {tableLoading ? "Đang đồng bộ..." : "Làm mới dữ liệu"}
            </button>
          </div>

          <div className="mt-5 flex min-h-0 flex-1 flex-col">
            {tableLoading && (
              <div aria-label="Đang tải bảng dữ liệu" className="grid gap-2">
                {[0, 1, 2, 3, 4, 5].map((row) => (
                  <div key={row} className={`h-11 rounded-md bg-[var(--fin-surface-raised)] ${row === 0 ? "opacity-100" : "opacity-60"}`} />
                ))}
              </div>
            )}

            {!tableLoading && tableError && (
              <div role="alert" className="flex min-h-72 flex-col items-center justify-center rounded-lg border border-rose-400/25 bg-rose-400/[0.04] p-6 text-center">
                <p className="font-medium text-rose-300">Không thể hiển thị bảng dữ liệu</p>
                <p className="mt-2 max-w-lg text-sm leading-6 text-[var(--fin-muted)]">{tableError}</p>
                <button type="button" onClick={handleRefresh} className="mt-5 rounded-lg border border-[var(--fin-soft-border)] px-4 py-2 text-sm hover:border-emerald-500">
                  Thử lại
                </button>
              </div>
            )}

            {!tableLoading && !tableError && tableData && tableData.rows.length === 0 && (
              <div className="flex min-h-72 items-center justify-center rounded-lg border border-dashed border-[var(--fin-soft-border)] p-6 text-center text-sm text-[var(--fin-muted)]">
                Bảng này chưa có bản ghi nào.
              </div>
            )}

            {!tableLoading && !tableError && tableData && tableData.rows.length > 0 && (
              <div className="max-h-[560px] min-h-[420px] overflow-auto rounded-lg border border-[var(--fin-soft-border)]">
                <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
                  <thead className="sticky top-0 z-10 bg-[var(--fin-surface-raised)]">
                    <tr>
                      {tableData.columns.map((column) => (
                        <th key={column} scope="col" className="whitespace-nowrap border-b border-r border-[var(--fin-soft-border)] px-4 py-3 font-mono text-xs font-semibold text-[var(--fin-muted)] last:border-r-0">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableData.rows.map((row, rowIndex) => {
                      const isSelected = selectedTable === CONTRACT_TABLE_NAME
                        && row.contract_id === selectedContractId;
                      return (
                        <tr
                          key={`${String(row[tableData.columns[0]] ?? "row")}-${rowIndex}`}
                          ref={(element) => {
                            if (isSelected) selectedRowRef.current = element;
                          }}
                          className={isSelected ? "bg-emerald-400/[0.12] text-[var(--fin-text)]" : "hover:bg-[var(--fin-surface-raised)]"}
                          aria-selected={isSelected}
                        >
                          {tableData.columns.map((column) => {
                            const value = formatValue(row[column]);
                            return (
                              <td key={column} className={`max-w-80 border-b border-r border-[var(--fin-soft-border)] px-4 py-3 align-top leading-5 last:border-r-0 ${isSelected ? "border-b-emerald-400/20" : ""}`}>
                                <span className={`block whitespace-pre-wrap break-words ${row[column] === null || row[column] === undefined || row[column] === "" ? "italic text-[var(--fin-muted)]" : ""}`} title={value}>
                                  {value}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <footer className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--fin-muted)]">
            <p>{tableData?.count ?? 0} bản ghi</p>
            <p>Đồng bộ lúc {formatSyncTime(tableData?.loaded_at)}</p>
          </footer>
        </div>
      </section>
    </div>
  );
}
