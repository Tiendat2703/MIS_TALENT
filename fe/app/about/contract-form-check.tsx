"use client";

import { useRouter } from "next/navigation";

import ContractForm, {
  type ContractFormData,
  type FinancePreflightResponse,
} from "@/components/inputform/form";
import { API_REQUEST_HEADERS, apiUrl } from "@/lib/api";
import { ACTIVE_RUN_STORAGE_KEY } from "@/lib/run-session";

type ErrorResponse = { detail?: string };

export function ContractFormCheck() {
  const router = useRouter();

  const sendContract = async (payload: ContractFormData) => {
    const response = await fetch(apiUrl("/finance/preflight"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...API_REQUEST_HEADERS,
      },
      body: JSON.stringify(payload),
    });
    const result = (await response.json()) as FinancePreflightResponse & ErrorResponse;

    if (!response.ok) {
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : `Không thể khởi tạo pipeline (HTTP ${response.status}).`,
      );
    }

    if (result.status === "AWAITING_INPUT") {
      return result;
    }

    if (result.status !== "RUNNING" || typeof result.session_id !== "number") {
      throw new Error("BE không trả về session_id hợp lệ.");
    }

    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(result.session_id));
    router.push("/agent");
    return result;
  };

  return <ContractForm onSubmit={sendContract} />;
}
