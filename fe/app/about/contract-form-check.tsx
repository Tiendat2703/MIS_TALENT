"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import ContractForm, {
  type ContractFormData,
  type FinancePreflightResponse,
} from "@/components/inputform/form";
import { API_REQUEST_HEADERS, apiUrl } from "@/lib/api";
import { ACTIVE_RUN_STORAGE_KEY } from "@/lib/run-session";

type ErrorResponse = { detail?: string };
type NextContractIdResponse = { contract_id?: string };

export function ContractFormCheck() {
  const router = useRouter();
  const [contractIdPreview, setContractIdPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewAttempt, setPreviewAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const loadPreview = async () => {
      try {
        setPreviewError("");
        const response = await fetch(apiUrl("/contracts/next-id"), {
          headers: {
            Accept: "application/json",
            ...API_REQUEST_HEADERS,
          },
        });
        const result = (await response.json()) as NextContractIdResponse & ErrorResponse;
        if (!response.ok || typeof result.contract_id !== "string") {
          throw new Error(
            typeof result.detail === "string"
              ? result.detail
              : "Backend không trả về mã hợp đồng dự kiến.",
          );
        }
        if (!cancelled) setContractIdPreview(result.contract_id);
      } catch (error) {
        if (!cancelled) {
          setPreviewError(
            error instanceof Error
              ? error.message
              : "Không thể tải mã hợp đồng dự kiến.",
          );
        }
      }
    };

    void loadPreview();
    return () => {
      cancelled = true;
    };
  }, [previewAttempt]);

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

    if (
      result.status === "AWAITING_INPUT"
      || result.status === "AWAITING_CONFIRMATION"
    ) {
      return result;
    }

    if (
      result.status !== "RUNNING"
      || typeof result.session_id !== "number"
      || typeof result.contract_id !== "string"
    ) {
      throw new Error("BE không trả về session_id hoặc contract_id hợp lệ.");
    }

    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(result.session_id));
    router.push("/agent");
    return result;
  };

  return (
    <ContractForm
      initialValues={{ contract_id: contractIdPreview }}
      contractIdPreviewStatus={
        previewError ? "error" : contractIdPreview ? "ready" : "loading"
      }
      contractIdPreviewError={previewError}
      onRetryContractIdPreview={() => {
        setContractIdPreview(null);
        setPreviewAttempt((current) => current + 1);
      }}
      onSubmit={sendContract}
    />
  );
}
