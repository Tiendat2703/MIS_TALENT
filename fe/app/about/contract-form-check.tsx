"use client";

import { useRouter } from "next/navigation";

import ContractForm, { type ContractFormData } from "@/components/inputform/form";
import { API_REQUEST_HEADERS, apiUrl } from "@/lib/api";
import { ACTIVE_RUN_STORAGE_KEY } from "@/lib/run-session";

type StartRunResponse = {
  session_id?: number;
  status?: string;
  detail?: string;
};

export function ContractFormCheck() {
  const router = useRouter();

  const sendContract = async (payload: ContractFormData) => {
    const response = await fetch(apiUrl("/runs"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...API_REQUEST_HEADERS,
      },
      body: JSON.stringify(payload),
    });
    const result = (await response.json()) as StartRunResponse;

    if (!response.ok) {
      throw new Error(
        typeof result.detail === "string"
          ? result.detail
          : `Không thể khởi tạo pipeline (HTTP ${response.status}).`,
      );
    }

    if (typeof result.session_id !== "number") {
      throw new Error("BE không trả về session_id hợp lệ.");
    }

    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(result.session_id));
    router.push("/agent");
  };

  return <ContractForm onSubmit={sendContract} />;
}
