"use client";

import ContractForm, { type ContractFormData } from "@/components/inputform/form";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8080"
).replace(/\/+$/, "");

type ContractValidationResponse = {
  received?: boolean;
  detail?: string;
};

export function ContractFormCheck() {
  const sendContract = async (payload: ContractFormData) => {
    const response = await fetch(`${API_BASE_URL}/contracts/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = (await response.json()) as ContractValidationResponse;

    if (!response.ok) {
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : `BE từ chối payload (HTTP ${response.status}).`,
      );
    }

    if (!result.received) {
      throw new Error("BE không trả về xác nhận payload hợp lệ.");
    }
  };

  return <ContractForm onSubmit={sendContract} />;
}
