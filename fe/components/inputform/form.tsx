"use client";

import { useMemo, useState, type FormEvent } from "react";
import {
  BadgeDollarSign,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileCheck2,
  FileText,
  Landmark,
  Percent,
  RotateCcw,
  Send,
} from "lucide-react";

import { cn } from "@/lib/utils";
import contractPayloadTemplate from "./contract-payload.json";

export const NEW_CONTRACT_STATUS = "Pending approval" as const;

export type ContractFormData = {
  contract_id: string;
  customer_id: string;
  start_date: string;
  end_date: string;
  status: typeof NEW_CONTRACT_STATUS;
  description: string;
  contract_value: number;
  gross_margin: number;
  payment_terms: string;
  requested_amount: number | null;
  funding_need_type: string | null;
  tenor: string | null;
};

const contractPayloadBase: ContractFormData = {
  ...contractPayloadTemplate,
  status: NEW_CONTRACT_STATUS,
};

type ContractFormState = Omit<
  ContractFormData,
  | "status"
  | "contract_value"
  | "gross_margin"
  | "requested_amount"
  | "funding_need_type"
  | "tenor"
> & {
  contract_value: string;
  gross_margin: string;
  requested_amount: string;
  tenor: string;
};

type FieldErrors = Partial<Record<keyof ContractFormState, string>>;

export type ContractFormProps = {
  initialValues?: Partial<ContractFormData>;
  onSubmit?: (values: ContractFormData) => void | Promise<void>;
  className?: string;
  submitLabel?: string;
  disabled?: boolean;
};

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
      values?.contract_value === undefined ? "" : String(values.contract_value),
    gross_margin:
      values?.gross_margin === undefined ? "" : String(values.gross_margin * 100),
    payment_terms: values?.payment_terms ?? "",
    requested_amount:
      values?.requested_amount == null ? "" : String(values.requested_amount),
    tenor: values?.tenor ?? "",
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
  const requestedAmount = values.requested_amount.trim()
    ? Number(values.requested_amount)
    : null;
  const grossMargin = Number(values.gross_margin);

  if (!values.contract_id.trim()) errors.contract_id = "Vui lòng nhập mã hợp đồng.";
  if (!values.customer_id.trim()) errors.customer_id = "Vui lòng nhập mã khách hàng.";
  if (!values.start_date) errors.start_date = "Vui lòng chọn ngày bắt đầu.";
  if (!values.end_date) errors.end_date = "Vui lòng chọn ngày kết thúc.";
  if (values.start_date && values.end_date && values.end_date < values.start_date) {
    errors.end_date = "Ngày kết thúc phải sau ngày bắt đầu.";
  }
  if (!values.description.trim()) errors.description = "Vui lòng mô tả hợp đồng.";
  if (!Number.isFinite(contractValue) || contractValue <= 0) {
    errors.contract_value = "Giá trị hợp đồng phải lớn hơn 0.";
  }
  if (!Number.isFinite(grossMargin) || grossMargin < 0 || grossMargin > 100) {
    errors.gross_margin = "Biên lợi nhuận phải nằm trong khoảng 0–100%.";
  }
  if (!values.payment_terms.trim()) {
    errors.payment_terms = "Vui lòng nhập điều khoản thanh toán.";
  }
  if (requestedAmount != null && (!Number.isFinite(requestedAmount) || requestedAmount <= 0)) {
    errors.requested_amount = "Số tiền đề nghị phải lớn hơn 0.";
  } else if (requestedAmount != null && contractValue > 0 && requestedAmount > contractValue) {
    errors.requested_amount = "Số tiền đề nghị không được vượt giá trị hợp đồng.";
  }

  return errors;
}

function buildContractPayload(values: ContractFormState): ContractFormData {
  return {
    ...contractPayloadBase,
    ...values,
    contract_id: values.contract_id.trim(),
    customer_id: values.customer_id.trim(),
    description: values.description.trim(),
    payment_terms: values.payment_terms.trim(),
    tenor: values.tenor.trim() || null,
    funding_need_type: null,
    contract_value: Number(values.contract_value),
    gross_margin: Number(values.gross_margin) / 100,
    requested_amount: values.requested_amount.trim()
      ? Number(values.requested_amount)
      : null,
    status: NEW_CONTRACT_STATUS,
  };
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
  onSubmit,
  className,
  submitLabel = "Gửi yêu cầu thẩm định",
  disabled = false,
}: ContractFormProps) {
  const initialState = useMemo(() => toFormState(initialValues), [initialValues]);
  const [values, setValues] = useState<ContractFormState>(initialState);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "success" | "error">(
    "idle",
  );
  const [submitMessage, setSubmitMessage] = useState("");

  const updateField = (field: keyof ContractFormState, value: string) => {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    if (submitState !== "idle") {
      setSubmitState("idle");
      setSubmitMessage("");
    }
  };

  const updateMoneyField = (
    field: "contract_value" | "requested_amount",
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

    const payload = buildContractPayload(values);

    try {
      setSubmitState("submitting");
      setSubmitMessage("");
      await onSubmit?.(payload);
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
    setSubmitState("idle");
    setSubmitMessage("");
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
              Mã hợp đồng <span className="text-emerald-400">*</span>
              <div className="relative">
                <FileText className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="contract_id"
                  name="contract_id"
                  value={values.contract_id}
                  onChange={(event) => updateField("contract_id", event.target.value)}
                  className={cn(inputClassName, "pl-10")}
                  placeholder="VD: CON-001"
                  autoComplete="off"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.contract_id)}
                  aria-describedby={describedBy("contract_id")}
                />
              </div>
              <FieldError id="contract_id-error" message={errors.contract_id} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="customer_id">
              Mã khách hàng <span className="text-emerald-400">*</span>
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
              Ngày bắt đầu <span className="text-emerald-400">*</span>
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
              Ngày kết thúc <span className="text-emerald-400">*</span>
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
              Mô tả hợp đồng <span className="text-emerald-400">*</span>
              <textarea
                id="description"
                name="description"
                rows={4}
                value={values.description}
                onChange={(event) => updateField("description", event.target.value)}
                className={textareaClassName}
                placeholder="Mô tả phạm vi và mục tiêu triển khai..."
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
            title="Tài chính & nhu cầu vốn"
            description="Giá trị thương mại và cấu trúc khoản tài trợ đề nghị."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="contract_value">
              Giá trị hợp đồng <span className="text-emerald-400">*</span>
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
              Biên lợi nhuận gộp <span className="text-emerald-400">*</span>
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
                Giá trị gửi đi: {Number(values.gross_margin || 0) / 100}
              </span>
              <FieldError id="gross_margin-error" message={errors.gross_margin} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="requested_amount">
              Số tiền đề nghị <span className="text-sm font-normal text-[var(--fin-muted)]">(không bắt buộc)</span>
              <div className="relative">
                <Landmark className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="requested_amount"
                  name="requested_amount"
                  inputMode="numeric"
                  value={values.requested_amount}
                  onChange={(event) => updateMoneyField("requested_amount", event.target.value)}
                  className={cn(inputClassName, "pl-10 pr-12")}
                  placeholder="VD: 300.000.000"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.requested_amount)}
                  aria-describedby={describedBy("requested_amount", "requested-amount-hint")}
                />
                <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm font-medium text-[var(--fin-muted)]">
                  VND
                </span>
              </div>
              <span id="requested-amount-hint" className="mt-1.5 block text-sm font-normal text-[var(--fin-muted)]">
                {values.requested_amount
                  ? formatCurrency(values.requested_amount)
                  : "Để trống để Finance tính từ dòng tiền riêng của hợp đồng."}
              </span>
              <FieldError id="requested_amount-error" message={errors.requested_amount} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)]" htmlFor="tenor">
              Thời hạn tài trợ <span className="text-sm font-normal text-[var(--fin-muted)]">(không bắt buộc)</span>
              <div className="relative">
                <Clock3 className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--fin-muted)]" />
                <input
                  id="tenor"
                  name="tenor"
                  value={values.tenor}
                  onChange={(event) => updateField("tenor", event.target.value)}
                  className={cn(inputClassName, "pl-10")}
                  placeholder="VD: 7 months"
                  disabled={disabled}
                  aria-invalid={Boolean(errors.tenor)}
                  aria-describedby={describedBy("tenor")}
                />
              </div>
              <span className="mt-1.5 block text-sm font-normal text-[var(--fin-muted)]">
                Nếu để trống, hệ thống dùng thời gian bắt đầu–kết thúc hợp đồng.
              </span>
              <FieldError id="tenor-error" message={errors.tenor} />
            </label>

            <label className="block text-base font-medium text-[var(--fin-text)] sm:col-span-2" htmlFor="payment_terms">
              Điều khoản thanh toán <span className="text-emerald-400">*</span>
              <textarea
                id="payment_terms"
                name="payment_terms"
                rows={4}
                value={values.payment_terms}
                onChange={(event) => updateField("payment_terms", event.target.value)}
                className={textareaClassName}
                placeholder="Nhập lịch thanh toán, tỷ lệ ứng trước và điều kiện nghiệm thu..."
                disabled={disabled}
                aria-invalid={Boolean(errors.payment_terms)}
                aria-describedby={describedBy("payment_terms")}
              />
              <FieldError id="payment_terms-error" message={errors.payment_terms} />
            </label>
          </div>
        </section>
      </div>

      <footer className="border-t border-[var(--fin-soft-border)] bg-black/10 px-5 py-5 sm:px-7">
        <div className="flex flex-col-reverse gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-h-5" aria-live="polite">
            {submitMessage ? (
              <p
                className={cn(
                  "flex items-center gap-2 text-base",
                  submitState === "success" ? "text-emerald-400" : "text-red-400",
                )}
              >
                {submitState === "success" ? (
                  <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                ) : (
                  <CircleAlert className="size-4 shrink-0" aria-hidden="true" />
                )}
                {submitMessage}
              </p>
            ) : (
              <p className="text-sm text-[var(--fin-muted)]">
                Các trường có dấu <span className="text-emerald-400">*</span> là bắt buộc.
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
