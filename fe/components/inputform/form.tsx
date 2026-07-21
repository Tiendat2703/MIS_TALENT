"use client";

import { useMemo, useState, type FormEvent } from "react";
import {
  BadgeDollarSign,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  FileCheck2,
  FileText,
  Landmark,
  Percent,
  RotateCcw,
  Send,
  Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";
export type ContractFormData = {
  contract_id: string | null;
  customer_id: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  contract_value: number | null;
  gross_margin: number | null;
  payment_terms: string | null;
  requested_amount: number | null;
  funding_need_type: string | null;
  tenor: string | null;
};

export type FinancePreflightMissingField = {
  field: string;
  label: string;
  reason: string;
  data_type: "text" | "number" | "date";
};

export type FinancePreflightDataIssue = {
  table: string;
  record: string;
  reason: string;
  severity: string;
  kind: string;
};

export type FinanceServiceMatch = {
  service_id: string;
  service_name: string;
  target_margin: number;
};

export type GrossMarginRecommendation = {
  primary_service: FinanceServiceMatch;
  alternative_services: FinanceServiceMatch[];
  recommended_gross_margin: number;
  confidence: number | null;
  reasoning: string;
};

export type FinancePreflightResponse = {
  status: "RUNNING" | "AWAITING_INPUT" | "AWAITING_CONFIRMATION";
  can_start_pipeline: boolean;
  session_id: number | null;
  contract_id: string | null;
  missing_fields: FinancePreflightMissingField[];
  data_issues: FinancePreflightDataIssue[];
  gross_margin_recommendation: GrossMarginRecommendation | null;
  summary: string;
};

type ContractFormState = {
  contract_id: string;
  customer_id: string;
  start_date: string;
  end_date: string;
  description: string;
  contract_value: string;
  gross_margin: string;
  payment_terms: string;
};

type FieldErrors = Partial<Record<keyof ContractFormState, string>>;

export type ContractFormProps = {
  initialValues?: Partial<ContractFormData>;
  contractIdPreviewStatus?: "loading" | "ready" | "error";
  contractIdPreviewError?: string;
  onRetryContractIdPreview?: () => void;
  onSubmit?: (
    values: ContractFormData,
  ) => void | FinancePreflightResponse | Promise<void | FinancePreflightResponse>;
  className?: string;
  submitLabel?: string;
  disabled?: boolean;
};

const paymentTermOptions = [
  "Monthly payment",
  "Milestone payment",
  "Performance bond required",
  "Possible LC/trade finance",
  "Working capital",
] as const;

const inputClassName =
  "mt-2 h-12 w-full rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-surface-raised)] px-4 text-base text-[var(--fin-text)] outline-none transition placeholder:text-[var(--fin-muted)]/60 hover:border-emerald-400/30 focus:border-emerald-400/70 focus:ring-3 focus:ring-emerald-400/10 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-red-400/70 aria-invalid:ring-3 aria-invalid:ring-red-400/10";

const textareaClassName = cn(inputClassName, "h-auto min-h-24 resize-y py-3 leading-6");

function toFormState(values?: Partial<ContractFormData>): ContractFormState {
  return {
    contract_id: values?.contract_id ?? "",
    customer_id: values?.customer_id ?? "",
    start_date: values?.start_date ?? "",
    end_date: values?.end_date ?? "",
    description: values?.description ?? "",
    contract_value:
      values?.contract_value == null ? "" : String(values.contract_value),
    gross_margin:
      values?.gross_margin == null ? "" : String(values.gross_margin * 100),
    payment_terms: values?.payment_terms ?? "",
  };
}

function formatCurrency(value: string) {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) return "0 ₫";

  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(amount);
}

function validate(values: ContractFormState): FieldErrors {
  const errors: FieldErrors = {};
  const contractValue = Number(values.contract_value);
  const grossMargin = Number(values.gross_margin);

  if (values.start_date && values.end_date && values.end_date < values.start_date) {
    errors.end_date = "Ngày kết thúc phải sau ngày bắt đầu.";
  }
  if (values.contract_value && (!Number.isFinite(contractValue) || contractValue <= 0)) {
    errors.contract_value = "Giá trị hợp đồng phải lớn hơn 0.";
  }
  if (
    values.gross_margin
    && (!Number.isFinite(grossMargin) || grossMargin < 0 || grossMargin > 100)
  ) {
    errors.gross_margin = "Biên lợi nhuận phải nằm trong khoảng 0–100%.";
  }
  return errors;
}

function optionalText(value: string): string | null {
  return value.trim() || null;
}

function optionalNumber(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

function buildContractPayload(
  values: ContractFormState,
  contractIdPreview?: string | null,
): ContractFormData {
  return {
    contract_id: contractIdPreview ?? optionalText(values.contract_id),
    customer_id: optionalText(values.customer_id),
    start_date: optionalText(values.start_date),
    end_date: optionalText(values.end_date),
    description: optionalText(values.description),
    contract_value: optionalNumber(values.contract_value),
    gross_margin: values.gross_margin.trim() ? Number(values.gross_margin) / 100 : null,
    payment_terms: optionalText(values.payment_terms),
    requested_amount: null,
    funding_need_type: null,
    tenor: null,
  };
}

function RequiredMark() {
  return <span className="ml-1 text-emerald-400" aria-hidden="true">*</span>;
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;

  return (
    <p id={id} className="mt-1.5 flex items-center gap-1.5 text-sm text-red-400">
      <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof FileText;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-5 flex items-start gap-3 border-b border-[var(--fin-soft-border)] pb-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-emerald-400/20 bg-emerald-400/10 text-emerald-400">
        <Icon className="size-4.5" aria-hidden="true" />
      </span>
      <div>
        <h2 className="text-base font-semibold text-[var(--fin-text)]">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-[var(--fin-muted)]">{description}</p>
      </div>
    </div>
  );
}

export function ContractForm({
  initialValues,
  contractIdPreviewStatus = "ready",
  contractIdPreviewError = "",
  onRetryContractIdPreview,
  onSubmit,
  className,
  submitLabel = "Kiểm tra và gửi thẩm định",
  disabled = false,
}: ContractFormProps) {
  const initialState = useMemo(() => toFormState(initialValues), [initialValues]);
  const [values, setValues] = useState<ContractFormState>(initialState);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitState, setSubmitState] = useState<
    "idle" | "submitting" | "success" | "error" | "confirmation"
  >("idle");
  const [submitMessage, setSubmitMessage] = useState("");
  const [dataIssues, setDataIssues] = useState<FinancePreflightDataIssue[]>([]);
  const [marginRecommendation, setMarginRecommendation] =
    useState<GrossMarginRecommendation | null>(null);

  const updateField = (field: keyof ContractFormState, value: string) => {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setDataIssues([]);
    setMarginRecommendation(null);
    if (submitState !== "idle") {
      setSubmitState("idle");
      setSubmitMessage("");
    }
  };

  const updateMoneyField = (
    field: "contract_value",
    value: string,
  ) => updateField(field, value.replace(/[^\d]/g, ""));

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors = validate(values);

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setSubmitState("error");
      setSubmitMessage("Vui lòng kiểm tra lại các trường được đánh dấu.");
      return;
    }

    const payload = buildContractPayload(values, initialValues?.contract_id);

    try {
      setSubmitState("submitting");
      setSubmitMessage("");
      const result = await onSubmit?.(payload);
      if (result?.status === "AWAITING_INPUT") {
        const serverErrors: FieldErrors = {};
        for (const missing of result.missing_fields) {
          if (missing.field in values) {
            serverErrors[missing.field as keyof ContractFormState] = missing.reason;
          }
        }
        setErrors(serverErrors);
        setDataIssues(result.data_issues);
        setSubmitState("error");
        setSubmitMessage(result.summary);
        return;
      }
      if (result?.status === "AWAITING_CONFIRMATION") {
        setErrors({});
        setDataIssues(result.data_issues);
        setMarginRecommendation(result.gross_margin_recommendation);
        setSubmitState("confirmation");
        setSubmitMessage(result.summary);
        return;
      }
      setSubmitState("success");
      setSubmitMessage(
        onSubmit
          ? "Hồ sơ hợp đồng đã được tiếp nhận và xác thực thành công."
          : "Dữ liệu hợp đồng hợp lệ và sẵn sàng để gửi.",
      );
    } catch (error) {
      setSubmitState("error");
      setSubmitMessage(
        error instanceof Error ? error.message : "Không thể gửi biểu mẫu. Vui lòng thử lại.",
      );
    }
  };

  const handleReset = () => {
    setValues(initialState);
    setErrors({});
    setDataIssues([]);
    setMarginRecommendation(null);
    setSubmitState("idle");
    setSubmitMessage("");
  };

  const applyMarginRecommendation = () => {
    if (!marginRecommendation) return;
    const percentage = marginRecommendation.recommended_gross_margin * 100;
    setValues((current) => ({ ...current, gross_margin: String(percentage) }));
    setErrors((current) => ({ ...current, gross_margin: undefined }));
    setMarginRecommendation(null);
    setSubmitState("confirmation");
    setSubmitMessage("Đã áp dụng đề xuất. Vui lòng gửi lại để bắt đầu pipeline.");
  };

  const describedBy = (field: keyof ContractFormState, hintId?: string) =>
    [hintId, errors[field] ? `${field}-error` : undefined].filter(Boolean).join(" ") || undefined;

  return (
    <form
      className={cn(
        "mx-auto w-full max-w-5xl overflow-hidden rounded-2xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] shadow-[0_24px_80px_rgba(0,0,0,.28)] ring-1 ring-white/[0.03]",
        className,
      )}
      onSubmit={handleSubmit}
      noValidate
    >
      <header className="relative overflow-hidden border-b border-[var(--fin-soft-border)] px-5 py-6 sm:px-7">
        <div className="absolute inset-y-0 right-0 w-56 bg-[radial-gradient(circle_at_center,rgba(52,211,153,.14),transparent_68%)]" />
        <div className="relative flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.18em] text-emerald-400">
              <FileCheck2 className="size-4" aria-hidden="true" />
              Hồ sơ tài trợ
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-[var(--fin-text)] sm:text-3xl">
              Thông tin hợp đồng
            </h1>
            <p className="mt-2 max-w-2xl text-base leading-7 text-[var(--fin-muted)]">
              Cung cấp dữ liệu hợp đồng để hệ thống phân tích tài chính và đánh giá nhu cầu vốn.
            </p>
          </div>
          <span className="inline-flex w-fit items-center gap-2 rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1.5 text-sm font-medium text-amber-300">
            <span className="size-1.5 rounded-full bg-amber-300" />
            Chờ hoàn tất hồ sơ
          </span>
        </div>
      </header>

      <div className="grid gap-5 p-5 sm:p-7 lg:grid-cols-2">
        <section className="rounded-xl border border-[var(--fin-soft-border)] bg-black/10 p-4 sm:p-5">
          <SectionHeading
            icon={FileText}
            title="Thông tin cơ bản"
            description="Định danh hợp đồng, khách hàng và trạng thái xử lý."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="contract_id">
              Mã hợp đồng
              <div className="relative">
                <FileText className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="contract_id"
                  name="contract_id"
                  value={initialValues?.contract_id ?? values.contract_id}
                  className={cn(inputClassName, "cursor-not-allowed pl-10 text-[var(--fin-muted)]")}
                  placeholder={
                    contractIdPreviewStatus === "error"
                      ? "Sẽ được cấp khi gửi"
                      : "Đang cấp mã dự kiến..."
                  }
                  autoComplete="off"
                  readOnly
                  aria-readonly="true"
                  aria-invalid={Boolean(errors.contract_id)}
                  aria-describedby={describedBy("contract_id", "contract-id-preview-hint")}
                />
              </div>
              <span
                id="contract-id-preview-hint"
                className={cn(
                  "mt-1.5 block text-sm font-normal",
                  contractIdPreviewStatus === "error"
                    ? "text-amber-300"
                    : "text-[var(--fin-muted)]",
                )}
              >
                {contractIdPreviewStatus === "loading" && "Đang lấy mã hợp đồng dự kiến..."}
                {contractIdPreviewStatus === "ready" && "Backend sẽ cấp lại mã chính thức khi lưu."}
                {contractIdPreviewStatus === "error" && (
                  <>
                    Không lấy được mã dự kiến. Backend sẽ cấp mã chính thức khi gửi.
                    {onRetryContractIdPreview && (
                      <button
                        type="button"
                        onClick={onRetryContractIdPreview}
                        className="ml-2 font-semibold text-amber-200 underline decoration-amber-300/50 underline-offset-2 transition hover:text-amber-100"
                        title={contractIdPreviewError || undefined}
                      >
                        Thử lại
                      </button>
                    )}
                  </>
                )}
              </span>
              <FieldError id="contract_id-error" message={errors.contract_id} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="customer_id">
              Mã khách hàng<RequiredMark />
              <div className="relative">
                <Building2 className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="customer_id"
                  name="customer_id"
                  value={values.customer_id}
                  onChange={(event) => updateField("customer_id", event.target.value)}
                  className={cn(inputClassName, "pl-10")}
                  placeholder="VD: CUS-001"
                  autoComplete="off"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.customer_id)}
                  aria-describedby={describedBy("customer_id")}
                />
              </div>
              <FieldError id="customer_id-error" message={errors.customer_id} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="start_date">
              Ngày bắt đầu<RequiredMark />
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="start_date"
                  name="start_date"
                  type="date"
                  value={values.start_date}
                  onChange={(event) => updateField("start_date", event.target.value)}
                  className={cn(inputClassName, "pl-10 scheme-dark")}
                  disabled={disabled}
                  aria-invalid={Boolean(errors.start_date)}
                  aria-describedby={describedBy("start_date")}
                />
              </div>
              <FieldError id="start_date-error" message={errors.start_date} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="end_date">
              Ngày kết thúc<RequiredMark />
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="end_date"
                  name="end_date"
                  type="date"
                  min={values.start_date}
                  value={values.end_date}
                  onChange={(event) => updateField("end_date", event.target.value)}
                  className={cn(inputClassName, "pl-10 scheme-dark")}
                  disabled={disabled}
                  aria-invalid={Boolean(errors.end_date)}
                  aria-describedby={describedBy("end_date")}
                />
              </div>
              <FieldError id="end_date-error" message={errors.end_date} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)] sm:col-span-2" htmlFor="description">
              Mô tả hợp đồng<RequiredMark />
              <textarea
                id="description"
                name="description"
                rows={4}
                value={values.description}
                onChange={(event) => updateField("description", event.target.value)}
                className={textareaClassName}
                placeholder="Mô tả dịch vụ OPC chính, phạm vi và mục tiêu triển khai..."
                disabled={disabled}
                aria-invalid={Boolean(errors.description)}
                aria-describedby={describedBy("description")}
              />
              <FieldError id="description-error" message={errors.description} />
            </label>
          </div>
        </section>

        <section className="rounded-xl border border-[var(--fin-soft-border)] bg-black/10 p-4 sm:p-5">
          <SectionHeading
            icon={Landmark}
            title="Thông tin tài chính"
            description="Giá trị thương mại, điều khoản thanh toán và biên lợi nhuận dự kiến."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="contract_value">
              Giá trị hợp đồng<RequiredMark />
              <div className="relative">
                <BadgeDollarSign className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="contract_value"
                  name="contract_value"
                  inputMode="numeric"
                  value={values.contract_value}
                  onChange={(event) => updateMoneyField("contract_value", event.target.value)}
                  className={cn(inputClassName, "pl-10 pr-12")}
                  placeholder="VD: 1.200.000.000"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.contract_value)}
                  aria-describedby={describedBy("contract_value", "contract-value-hint")}
                />
                <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm font-medium text-[var(--fin-muted)]">
                  VND
                </span>
              </div>
              <span id="contract-value-hint" className="mt-1.5 block text-sm font-normal text-[var(--fin-muted)]">
                {formatCurrency(values.contract_value)}
              </span>
              <FieldError id="contract_value-error" message={errors.contract_value} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="gross_margin">
              Biên lợi nhuận gộp
              <div className="relative">
                <Percent className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="gross_margin"
                  name="gross_margin"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={values.gross_margin}
                  onChange={(event) => updateField("gross_margin", event.target.value)}
                  className={cn(inputClassName, "pl-10 pr-9")}
                  placeholder="VD: 25"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.gross_margin)}
                  aria-describedby={describedBy("gross_margin", "gross-margin-hint")}
                />
                <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm font-medium text-[var(--fin-muted)]">
                  %
                </span>
              </div>
              <span id="gross-margin-hint" className="mt-1.5 block text-sm font-normal text-[var(--fin-muted)]">
                {values.gross_margin
                  ? `Giá trị gửi đi: ${Number(values.gross_margin) / 100}`
                  : "Để trống để Finance Agent đề xuất từ mô tả dịch vụ."}
              </span>
              <FieldError id="gross_margin-error" message={errors.gross_margin} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)] sm:col-span-2" htmlFor="payment_terms">
              Điều khoản thanh toán<RequiredMark />
              <select
                id="payment_terms"
                name="payment_terms"
                value={values.payment_terms}
                onChange={(event) => updateField("payment_terms", event.target.value)}
                className={inputClassName}
                disabled={disabled}
                aria-invalid={Boolean(errors.payment_terms)}
                aria-describedby={describedBy("payment_terms")}
              >
                <option value="" disabled>
                  Chọn điều khoản thanh toán
                </option>
                {paymentTermOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <FieldError id="payment_terms-error" message={errors.payment_terms} />
            </label>
          </div>
        </section>
      </div>

      {marginRecommendation ? (
        <section
          className="mx-5 mb-5 rounded-xl border border-amber-300/25 bg-amber-300/8 p-4 sm:mx-7 sm:p-5"
          aria-live="polite"
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-base font-semibold text-amber-200">
                <Sparkles className="size-4" aria-hidden="true" />
                Gross margin do Finance Agent đề xuất
              </h2>
              <p className="mt-3 text-2xl font-semibold text-[var(--fin-text)]">
                {new Intl.NumberFormat("vi-VN", {
                  style: "percent",
                  maximumFractionDigits: 2,
                }).format(marginRecommendation.recommended_gross_margin)}
              </p>
              <p className="mt-1 text-sm text-amber-100/80">
                Dịch vụ chính: {marginRecommendation.primary_service.service_name}
                {" "}({marginRecommendation.primary_service.service_id})
              </p>
              {marginRecommendation.confidence != null ? (
                <p className="mt-1 text-sm text-[var(--fin-muted)]">
                  Độ tin cậy mapping: {Math.round(marginRecommendation.confidence * 100)}%
                </p>
              ) : null}
              <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--fin-muted)]">
                {marginRecommendation.reasoning}
              </p>
              {marginRecommendation.alternative_services.length > 0 ? (
                <p className="mt-2 text-sm text-[var(--fin-muted)]">
                  Dịch vụ liên quan: {marginRecommendation.alternative_services
                    .map((service) => service.service_name)
                    .join(", ")}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={applyMarginRecommendation}
              className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-amber-300 px-4 text-sm font-semibold text-amber-950 transition hover:bg-amber-200 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-amber-300/30"
            >
              <Sparkles className="size-4" aria-hidden="true" />
              Áp dụng đề xuất
            </button>
          </div>
        </section>
      ) : null}

      {dataIssues.length > 0 ? (
        <section
          className="mx-5 mb-5 rounded-xl border border-red-400/25 bg-red-400/8 p-4 sm:mx-7"
          aria-live="polite"
        >
          <h2 className="flex items-center gap-2 text-base font-semibold text-red-300">
            <CircleAlert className="size-4" aria-hidden="true" />
            Dữ liệu nền cần được bổ sung
          </h2>
          <ul className="mt-3 space-y-2 text-sm leading-6 text-red-100/80">
            {dataIssues.map((issue, index) => (
              <li key={`${issue.table}-${issue.record}-${index}`}>
                <span className="font-medium text-red-200">
                  {issue.table} · {issue.record}:
                </span>{" "}
                {issue.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="border-t border-[var(--fin-soft-border)] bg-black/10 px-5 py-5 sm:px-7">
        <div className="flex flex-col-reverse gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-h-5" aria-live="polite">
            {submitMessage ? (
              <p
                className={cn(
                  "flex items-center gap-2 text-base",
                  submitState === "success"
                    ? "text-emerald-400"
                    : submitState === "confirmation"
                      ? "text-amber-300"
                      : "text-red-400",
                )}
              >
                {submitState === "success" ? (
                  <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                ) : submitState === "confirmation" ? (
                  <Sparkles className="size-4 shrink-0" aria-hidden="true" />
                ) : (
                  <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
                )}
                {submitMessage}
              </p>
            ) : (
              <p className="text-sm text-[var(--fin-muted)]">
                Finance Agent sẽ kiểm tra và chỉ ra thông tin cần bổ sung sau khi gửi.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={handleReset}
              disabled={disabled || submitState === "submitting"}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-[var(--fin-soft-border)] px-4 text-base font-medium text-[var(--fin-muted)] transition hover:border-white/20 hover:bg-white/5 hover:text-[var(--fin-text)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw className="size-4" aria-hidden="true" />
              Đặt lại
            </button>
            <button
              type="submit"
              disabled={disabled || submitState === "submitting"}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-emerald-400 px-5 text-base font-semibold text-emerald-950 shadow-[0_8px_24px_rgba(52,211,153,.16)] transition hover:bg-emerald-300 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-emerald-400/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitState === "submitting" ? (
                <span className="size-4 animate-spin rounded-full border-2 border-emerald-950/30 border-t-emerald-950" />
              ) : (
                <Send className="size-4" aria-hidden="true" />
              )}
              {submitState === "submitting" ? "Đang gửi..." : submitLabel}
            </button>
          </div>
        </div>
      </footer>
    </form>
  );
}

export default ContractForm;
