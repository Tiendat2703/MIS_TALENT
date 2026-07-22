"use client";

import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Eye,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, API_REQUEST_HEADERS, apiUrl } from "@/lib/api";

type ApprovalStatus = "pending" | "approved" | "review" | "rejected";
type RiskLevel = "low" | "medium" | "high" | "critical";
type RiskScope = "CONTRACT" | "PORTFOLIO";
type FilterStatus = "all" | ApprovalStatus;

type ContractRisk = {
  title: string;
  description: string;
  severity: RiskLevel;
  status: string;
  scope: RiskScope;
};

type AgentTriggeredRule = {
  ruleId: string;
  scope: RiskScope;
  severity: RiskLevel;
  requiredAction: string;
  message: string;
};

type AgentAlert = {
  alertId: string;
  alertType: string;
  severity: RiskLevel;
  riskScore: number | null;
  description: string;
  recommendedAction: string;
  matchedRuleIds: string[];
};

type AgentRiskSnapshot = {
  available: boolean;
  contractId: string;
  overallRiskLevel: RiskLevel | null;
  totalRulesTriggered: number;
  triggeredRuleIds: string[];
  totalAlertsDetected: number;
  totalProposedAlerts: number;
  insufficientEvidenceCount: number;
  humanReviewRequired: boolean;
  totalRulesEvaluated: number;
  notTriggeredCount: number;
  insufficientEvidenceRuleCount: number;
  triggeredRules: AgentTriggeredRule[];
  alerts: AgentAlert[];
  evidenceGaps: string[];
  requiredActions: string[];
  portfolioRisks: ContractRisk[];
  portfolioAlerts: AgentAlert[];
  highestPortfolioRiskLevel: RiskLevel | null;
  portfolioApprovalRequired: boolean;
};

type BankPrecheck = {
  available: boolean;
  requestType: string | null;
  requestedAmount: number | null;
  eligibleScore: number | null;
  precheckNote: string | null;
  approvalStatus: boolean;
  requiresFounderConfirmation: boolean;
};

type ContractRecord = {
  id: string;
  runId?: number;
  title: string;
  counterparty: string;
  amount: number | null;
  startDate: string;
  endDate: string;
  submittedAt: string;
  paymentTerms: string;
  contractType: string;
  owner: string;
  summary: string;
  aiOption: string;
  aiConfidence: number | null;
  reasons: string[];
  risks: ContractRisk[];
  safeguards: string[];
  riskLevel: RiskLevel;
  status: ApprovalStatus;
  agentRisk: AgentRiskSnapshot;
  bankPrecheck: BankPrecheck;
};

type ApiContract = {
  session_id: number;
  contract_id: string;
  generated_at?: string | null;
  finance?: {
    contract_lifecycle?: string | null;
    assessment_type?: string | null;
    finance_status?: string | null;
    contract_name?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    funding_need_type?: string | null;
    requested_amount?: number | null;
    contract_value?: number | null;
    gross_margin?: number | null;
    confidence_score?: number | null;
    status?: string | null;
    additional_funding_need?: number | null;
    worst_month_after?: number | null;
  } | null;
  risk?: {
    overall_risk_level?: string | null;
    risk_assessment_status?: "COMPLETE" | "INCOMPLETE" | null;
    review_priority?: string | null;
    triggered_rule_approval_required?: boolean | null;
    manual_evidence_review_required?: boolean | null;
    human_approval_required?: boolean | null;
    triggered_rule_ids?: string[];
    contract_triggered_rule_ids?: string[];
    portfolio_triggered_rule_ids?: string[];
    highest_contract_triggered_severity?: string | null;
    highest_portfolio_triggered_severity?: string | null;
    portfolio_transaction_approval_required?: boolean;
    total_rules_triggered?: number;
    total_alerts_detected?: number;
    total_proposed_alerts?: number;
    insufficient_evidence_count?: number;
    highest_severity?: string | null;
    human_review_required?: boolean | null;
    total_rules_evaluated?: number;
    not_triggered_count?: number;
    insufficient_evidence_rule_count?: number;
    triggered_rules?: Array<{
      rule_id?: string | null;
      scope?: string | null;
      severity?: string | null;
      required_action?: string | null;
      message?: string | null;
    }>;
    rule_evaluations?: Array<{
      rule_id?: string | null;
      scope?: string | null;
      status?: string | null;
      severity?: string | null;
      required_action?: string | null;
      message?: string | null;
    }>;
    alerts?: Array<{
      matched_rule_ids?: string[];
      alert?: {
        alert_id?: string | null;
        alert_type?: string | null;
        severity?: string | null;
        risk_score?: number | null;
        description?: string | null;
        recommended_action?: string | null;
      } | null;
    }>;
    evidence_gaps?: string[];
    required_actions?: string[];
  } | null;
  decision?: {
    recommended_option?: string | null;
    decision_status?: string | null;
    risk_level?: string | null;
    risk_assessment_status?: "COMPLETE" | "INCOMPLETE" | null;
    review_priority?: string | null;
    capital_need?: number | null;
    funding_need_type?: string | null;
    selected_bank_product_id?: string | null;
    selected_bank_product_name?: string | null;
    requires_founder_confirmation?: boolean | null;
    approval_status?: boolean | null;
    eligible_score?: number | null;
    human_confirmation_status?: string | null;
    external_api_submission_approval_status?: string | null;
    bank_precheck_status?: string | null;
    eligibility_score?: number | null;
    precheck_note?: string | null;
    is_preliminary?: boolean | null;
    contract_status?: string | null;
    assessment_type?: string | null;
    required_actions?: Array<{ action?: string; owner?: string }>;
    human_confirmation_points?: string[];
    is_final_decision?: boolean;
  } | null;
};

type ApiPendingApproval = {
  approval_id?: string;
  contract_id?: string;
  session_id?: number;
  status?: string;
  result?: {
    eligible_score?: number | null;
    precheck_note?: string | null;
  } | null;
  tool?: string;
  arguments?: Record<string, unknown>;
};

type DashboardBootstrap = {
  contracts: ContractRecord[];
  pendingRequests: Record<string, PendingApprovalRequest>;
  approvalIssue: string;
};

type RunDecisionDetail = {
  contract_id?: string;
  recommended_option?: string;
  reasons?: string[];
  protective_condition?: string;
  capital_need?: number | null;
  funding_need_type?: string | null;
  selected_bank_product_id?: string | null;
  selected_bank_product_name?: string | null;
  eligible_score?: number | null;
  eligibility_score?: number | null;
  precheck_note?: string | null;
  approval_status?: boolean;
  external_api_submission_approval_status?: string;
  bank_precheck_status?: string;
  requires_founder_confirmation?: boolean;
  required_actions?: Array<{ action?: string; owner?: string }>;
  human_confirmation_points?: string[];
};

type RunRiskEvaluation = {
  status?: string;
  rule_id?: string;
  scope?: string;
  risk_type?: string;
  severity?: string;
  message?: string;
  observed_value?: string;
  required_action?: string;
  missing_fields?: string[];
};

type RunRiskDetail = {
  contract_id?: string;
  overall_risk_level?: string;
  human_approval_required?: boolean;
  triggered_rule_approval_required?: boolean;
  manual_evidence_review_required?: boolean;
  triggered_rule_ids?: string[];
  contract_triggered_rule_ids?: string[];
  portfolio_triggered_rule_ids?: string[];
  highest_contract_triggered_severity?: string | null;
  highest_portfolio_triggered_severity?: string | null;
  portfolio_transaction_approval_required?: boolean;
  summary?: {
    total_rules_triggered?: number;
    total_alerts_detected?: number;
    total_proposed_alerts?: number;
    human_review_required?: boolean;
  };
  rule_evaluations?: RunRiskEvaluation[];
  alerts?: Array<{
    matched_rule_ids?: string[];
    alert?: {
      alert_id?: string;
      alert_type?: string;
      severity?: string;
      risk_score?: number | null;
      description?: string;
      recommended_action?: string;
    };
  }>;
  proposed_alerts?: unknown[];
  insufficient_evidence?: string[];
  required_actions?: string[];
};

type RunDetailPayload = {
  decisions?: RunDecisionDetail[];
  risk_pack?: { packs?: RunRiskDetail[] } | null;
};

const optionLabels: Record<string, string> = {
  APPROVE: "Nên duyệt",
  APPROVE_WITH_CONDITION: "Duyệt có điều kiện",
  TEMPORARY_REJECT_RISK: "Tạm từ chối · rủi ro",
  REJECT_MISSING_EVIDENCE: "Từ chối · thiếu hồ sơ",
  NO_SUITABLE_PRODUCT: "Chưa có phương án phù hợp",
  CONTINUE_AS_PLANNED: "Tiếp tục theo kế hoạch",
  CONTINUE_WITH_ACTIONS: "Tiếp tục kèm hành động",
  ESCALATE_FOR_REVIEW: "Chuyển cấp xem xét",
  RECOMMEND_RENEGOTIATION: "Đề nghị đàm phán lại",
  RECOMMEND_HOLD: "Đề nghị tạm giữ",
  NEED_MORE_DATA: "Cần bổ sung dữ liệu",
  PENDING_ANALYSIS: "Đang chờ phân tích",
};

const statusLabels: Record<ApprovalStatus, string> = {
  pending: "Chờ quyết định",
  approved: "Đã duyệt",
  review: "Cần xem xét",
  rejected: "Đã từ chối",
};

const riskLabels: Record<RiskLevel, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
  critical: "Nghiêm trọng",
};

const filters: { value: FilterStatus; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "pending", label: "Chờ duyệt" },
  { value: "review", label: "Xem xét" },
  { value: "approved", label: "Đã duyệt" },
  { value: "rejected", label: "Từ chối" },
];

function normalizeRiskLevel(value?: string | null): RiskLevel {
  const normalized = value?.toLowerCase();
  if (normalized === "critical" || normalized === "high" || normalized === "medium") return normalized;
  return "low";
}

function normalizeRiskScope(value?: string | null): RiskScope {
  return value?.toUpperCase() === "PORTFOLIO" ? "PORTFOLIO" : "CONTRACT";
}

function mapRiskEvaluation(entry: RunRiskEvaluation): ContractRisk {
  return {
    title: entry.risk_type || entry.rule_id || "Cảnh báo rủi ro",
    description: [
      entry.message || `Giá trị quan sát: ${entry.observed_value || "cần xác minh thêm"}.`,
      entry.missing_fields?.length ? `Thiếu: ${entry.missing_fields.join(", ")}.` : "",
      entry.required_action ? `Hành động: ${entry.required_action}.` : "",
    ].filter(Boolean).join(" "),
    severity: normalizeRiskLevel(entry.severity),
    status: entry.status || "INSUFFICIENT_EVIDENCE",
    scope: normalizeRiskScope(entry.scope),
  };
}

function normalizeStatus(value?: string | null, approvalStatus?: boolean | null): ApprovalStatus {
  if (approvalStatus) return "approved";
  if (value === "reject") return "rejected";
  if (value === "review") return "review";
  return "pending";
}

function normalizeEligibilityScore(value?: number | null): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  const normalized = value > 1 ? value / 100 : value;
  return Math.min(1, Math.max(0, normalized));
}

function formatEligibilityScore(value: number): string {
  return value.toFixed(2);
}

function paymentLabel(type?: string | null): string {
  if (type === "PERFORMANCE_BOND") return "Bảo lãnh thực hiện";
  if (type === "TRADE_FINANCE") return "L/C · tài trợ thương mại";
  if (type === "WORKING_CAPITAL") return "Theo tiến độ · vốn lưu động";
  return "Theo điều khoản hợp đồng";
}

function mapApiContract(item: ApiContract): ContractRecord {
  const finance = item.finance ?? {};
  const decision = item.decision ?? {};
  const selectedFundingType = decision.funding_need_type ?? finance.funding_need_type;
  const externalApprovalExecuted =
    decision.external_api_submission_approval_status === "EXECUTED"
    || decision.approval_status === true;
  const rawEvaluations: RunRiskEvaluation[] = item.risk?.rule_evaluations?.map((rule) => ({
    rule_id: rule.rule_id ?? undefined,
    scope: rule.scope ?? undefined,
    status: rule.status ?? undefined,
    severity: rule.severity ?? undefined,
    required_action: rule.required_action ?? undefined,
    message: rule.message ?? undefined,
  })) ?? (item.risk?.triggered_rules ?? []).map((rule) => ({
    rule_id: rule.rule_id ?? undefined,
    scope: rule.scope ?? undefined,
    status: "TRIGGERED",
    severity: rule.severity ?? undefined,
    required_action: rule.required_action ?? undefined,
    message: rule.message ?? undefined,
  }));
  const evaluations = rawEvaluations.map(mapRiskEvaluation);
  const contractRisks = evaluations.filter((risk) => risk.scope === "CONTRACT");
  const portfolioRisks = evaluations.filter((risk) => risk.scope === "PORTFOLIO");
  const contractTriggeredRuleIds = item.risk?.contract_triggered_rule_ids
    ?? contractRisks.filter((risk) => risk.status === "TRIGGERED").map((risk) => risk.title);
  const portfolioTriggeredRuleIds = item.risk?.portfolio_triggered_rule_ids
    ?? portfolioRisks.filter((risk) => risk.status === "TRIGGERED").map((risk) => risk.title);
  const portfolioRuleIdSet = new Set(portfolioTriggeredRuleIds);
  const mappedAlerts: AgentAlert[] = (item.risk?.alerts ?? []).flatMap((match) => match.alert ? [{
    alertId: match.alert.alert_id || "UNKNOWN_ALERT",
    alertType: match.alert.alert_type || "Risk alert",
    severity: normalizeRiskLevel(match.alert.severity),
    riskScore: match.alert.risk_score ?? null,
    description: match.alert.description || "",
    recommendedAction: match.alert.recommended_action || "",
    matchedRuleIds: match.matched_rule_ids ?? [],
  }] : []);
  const portfolioAlerts = mappedAlerts.filter((alert) => (
    alert.matchedRuleIds.some((ruleId) => portfolioRuleIdSet.has(ruleId))
  ));
  const contractAlerts = mappedAlerts.filter((alert) => (
    !alert.matchedRuleIds.some((ruleId) => portfolioRuleIdSet.has(ruleId))
  ));
  const riskLevel = normalizeRiskLevel(
    decision.risk_level ?? item.risk?.highest_contract_triggered_severity,
  );
  const contractValue = finance.contract_value ?? null;

  return {
    id: item.contract_id,
    runId: item.session_id,
    title: finance.contract_name || `Hợp đồng ${item.contract_id}`,
    counterparty: "Chưa có dữ liệu đối tác",
    amount: contractValue,
    startDate: finance.start_date || "",
    endDate: finance.end_date || "",
    submittedAt: item.generated_at || "",
    paymentTerms: paymentLabel(selectedFundingType),
    contractType: decision.selected_bank_product_name
      || selectedFundingType?.replaceAll("_", " ")
      || "Hợp đồng thương mại",
    owner: "Chưa có dữ liệu",
    summary: finance.status
      ? `Hồ sơ đã hoàn tất bước ${finance.status.toLowerCase()} và đang chờ quyết định cuối.`
      : "Hồ sơ hợp đồng được nhập vào pipeline phân tích tài chính và rủi ro.",
    aiOption: decision.recommended_option || "PENDING_ANALYSIS",
    aiConfidence: finance.confidence_score != null
      ? Math.round(finance.confidence_score * 100)
      : null,
    reasons: [],
    risks: contractRisks,
    safeguards: [],
    riskLevel,
    status: normalizeStatus(decision.decision_status, externalApprovalExecuted),
    agentRisk: {
      available: Boolean(item.risk),
      contractId: item.contract_id,
      overallRiskLevel: item.risk?.highest_contract_triggered_severity
        ? normalizeRiskLevel(item.risk.highest_contract_triggered_severity)
        : null,
      totalRulesTriggered: contractTriggeredRuleIds.length,
      triggeredRuleIds: contractTriggeredRuleIds,
      totalAlertsDetected: contractAlerts.length,
      totalProposedAlerts: item.risk?.total_proposed_alerts ?? 0,
      insufficientEvidenceCount: item.risk?.insufficient_evidence_count ?? 0,
      humanReviewRequired: item.risk?.human_review_required
        ?? item.risk?.manual_evidence_review_required
        ?? item.risk?.triggered_rule_approval_required
        ?? item.risk?.human_approval_required
        ?? false,
      totalRulesEvaluated: item.risk?.total_rules_evaluated ?? 0,
      notTriggeredCount: item.risk?.not_triggered_count ?? 0,
      insufficientEvidenceRuleCount: item.risk?.insufficient_evidence_rule_count ?? 0,
      triggeredRules: (item.risk?.triggered_rules ?? []).map((rule) => ({
        ruleId: rule.rule_id || "UNKNOWN_RULE",
        scope: normalizeRiskScope(rule.scope),
        severity: normalizeRiskLevel(rule.severity),
        requiredAction: rule.required_action || "",
        message: rule.message || "",
      })),
      alerts: contractAlerts,
      evidenceGaps: item.risk?.evidence_gaps ?? [],
      requiredActions: item.risk?.required_actions ?? [],
      portfolioRisks,
      portfolioAlerts,
      highestPortfolioRiskLevel: item.risk?.highest_portfolio_triggered_severity
        ? normalizeRiskLevel(item.risk.highest_portfolio_triggered_severity)
        : null,
      portfolioApprovalRequired: item.risk?.portfolio_transaction_approval_required ?? false,
    },
    bankPrecheck: {
      available: Boolean(item.decision || selectedFundingType),
      requestType: selectedFundingType ?? null,
      requestedAmount: decision.capital_need ?? finance.requested_amount ?? null,
      eligibleScore: normalizeEligibilityScore(
        decision.eligibility_score ?? decision.eligible_score,
      ),
      precheckNote: decision.precheck_note ?? null,
      approvalStatus: externalApprovalExecuted,
      requiresFounderConfirmation: decision.requires_founder_confirmation ?? false,
    },
  };
}

async function fetchDashboard(signal?: AbortSignal): Promise<DashboardBootstrap> {
  const response = await fetch(apiUrl("/dashboard?latest_only=true"), {
    cache: "no-store",
    headers: API_REQUEST_HEADERS,
    signal,
  });
  if (!response.ok) throw new Error(`Dashboard API returned ${response.status}`);
  const payload = (await response.json()) as {
    contracts?: ApiContract[];
    pending_approvals?: ApiPendingApproval[];
    approval_errors?: Array<{ session_id?: number; message?: string }>;
  };
  const pendingRequests: Record<string, PendingApprovalRequest> = {};
  (payload.pending_approvals ?? []).forEach((request) => {
    if (!request.approval_id || !request.contract_id || request.session_id == null) return;
    pendingRequests[request.contract_id] = {
      approvalId: request.approval_id,
      contractId: request.contract_id,
      runId: request.session_id,
      status: request.status || "pending",
      result: request.result ? {
        eligibleScore: normalizeEligibilityScore(request.result.eligible_score),
        precheckNote: request.result.precheck_note ?? null,
      } : null,
      tool: request.tool || "bank_precheck",
      arguments: request.arguments ?? {},
    };
  });
  const approvalErrors = payload.approval_errors ?? [];
  return {
    contracts: (payload.contracts ?? []).map(mapApiContract),
    pendingRequests,
    approvalIssue: approvalErrors.length > 0
      ? `Không tải được approval của ${approvalErrors.length} pipeline.`
      : "",
  };
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatCompactCurrency(value: number | null | undefined): string {
  if (value == null) return "Chưa có dữ liệu";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} tỷ ₫`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 0 })} triệu ₫`;
  return formatCurrency(value);
}

function formatDate(value: string): string {
  if (!value) return "Chưa xác định";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

function formatSubmittedAt(value: string): string {
  if (!value) return "Chưa xác định";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function StatusBadge({ status }: { status: ApprovalStatus }) {
  const styles: Record<ApprovalStatus, string> = {
    pending: "border-white/10 bg-white/[0.04] text-[var(--fin-muted)]",
    approved: "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
    review: "border-amber-300/20 bg-amber-300/[0.08] text-amber-200",
    rejected: "border-rose-300/20 bg-rose-300/[0.07] text-rose-200",
  };
  const dots: Record<ApprovalStatus, string> = {
    pending: "bg-zinc-400",
    approved: "bg-emerald-300",
    review: "bg-amber-300",
    rejected: "bg-rose-300",
  };

  return (
    <span className={`inline-flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-[11px] font-semibold ${styles[status]}`}>
      <span className={`size-1.5 rounded-full ${dots[status]}`} aria-hidden="true" />
      {statusLabels[status]}
    </span>
  );
}

function RiskBadge({ level }: { level: RiskLevel }) {
  const styles: Record<RiskLevel, string> = {
    low: "border-emerald-400/20 bg-emerald-400/[0.07] text-emerald-300",
    medium: "border-amber-300/20 bg-amber-300/[0.07] text-amber-200",
    high: "border-red-400/30 bg-red-400/[0.1] text-red-300",
    critical: "border-red-500/45 bg-red-500/20 text-red-200",
  };
  return <span className={`rounded border px-2 py-1 text-[10px] font-semibold ${styles[level]}`}>{riskLabels[level]}</span>;
}

function RuleStatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const isTriggered = normalized === "TRIGGERED";
  const needsEvidence = normalized === "INSUFFICIENT_EVIDENCE";
  const label = isTriggered
    ? "Có rủi ro"
    : needsEvidence
      ? "Cần thêm dữ liệu"
      : "Không dính rule";
  const styles = isTriggered
    ? "border-red-400/30 bg-red-400/[0.12] text-red-200"
    : needsEvidence
      ? "border-amber-300/25 bg-amber-300/[0.09] text-amber-100"
      : "border-emerald-400/25 bg-emerald-400/[0.09] text-emerald-200";

  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold ${styles}`}>
      <span
        className={`size-1.5 rounded-full ${
          isTriggered
            ? "bg-red-300"
            : needsEvidence
              ? "bg-amber-200"
              : "bg-emerald-300"
        }`}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: typeof FileText;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <article className="min-w-0 border-b border-[var(--fin-soft-border)] px-5 py-5 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-[var(--fin-muted)]">{label}</p>
        <Icon className="size-4 text-emerald-300" strokeWidth={1.7} aria-hidden="true" />
      </div>
      <p className="mt-3 font-mono text-2xl font-semibold tracking-[-0.05em] text-[var(--fin-text)] sm:text-[1.7rem]">{value}</p>
      <p className="mt-1.5 text-[11px] text-[var(--fin-muted)]">{note}</p>
    </article>
  );
}

const severityOrder: Array<RiskLevel | "none"> = ["critical", "high", "medium", "low", "none"];
const severityLabels: Record<RiskLevel | "none", string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "Không kích hoạt",
};
function EnterpriseRiskChart({ contracts }: { contracts: ContractRecord[] }) {
  const portfolioSource = useMemo(
    () => contracts
      .filter((contract) => (
        contract.agentRisk.available
        && (
          contract.agentRisk.portfolioRisks.length > 0
          || contract.agentRisk.portfolioAlerts.length > 0
        )
      ))
      .sort((left, right) => (right.runId ?? 0) - (left.runId ?? 0))[0] ?? null,
    [contracts],
  );
  const portfolioRisk = portfolioSource?.agentRisk;
  const portfolioEvaluations = portfolioRisk?.portfolioRisks ?? [];
  const totalRulesEvaluated = portfolioEvaluations.length;
  const triggeredRules = portfolioEvaluations.filter((risk) => risk.status === "TRIGGERED");
  const totalRulesTriggered = triggeredRules.length;
  const insufficientEvidenceRuleCount = portfolioEvaluations.filter((risk) => (
    risk.status === "INSUFFICIENT_EVIDENCE" || risk.status === "RULE_CONFIGURATION_ERROR"
  )).length;
  const notTriggeredCount = portfolioEvaluations.filter((risk) => (
    risk.status === "NOT_TRIGGERED"
    || risk.status === "NOT_APPLICABLE"
    || risk.status === "RULE_INACTIVE"
  )).length;
  const activeAlerts = (portfolioRisk?.portfolioAlerts ?? []).slice(0, 3);
  const totalAlertsDetected = portfolioRisk?.portfolioAlerts.length ?? 0;
  const evidenceGapCount = insufficientEvidenceRuleCount;
  const highestSeverity = portfolioRisk?.highestPortfolioRiskLevel
    ?? severityOrder.find((level) => level !== "none" && triggeredRules.some((risk) => risk.severity === level))
    ?? "none";
  const evaluationStatuses = [
    { label: "Triggered", value: totalRulesTriggered, color: "bg-red-400" },
    { label: "Thiếu bằng chứng", value: insufficientEvidenceRuleCount, color: "bg-amber-200" },
    { label: "Không kích hoạt", value: notTriggeredCount, color: "bg-emerald-300" },
  ];

  return (
    <section className="h-full overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
      <header className="flex items-start justify-between gap-4 border-b border-[var(--fin-soft-border)] px-5 py-5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-300">Portfolio scope</p>
          <h3 className="mt-2 text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Rủi ro toàn hệ thống</h3>
          <p className="mt-1 max-w-sm text-xs leading-5 text-[var(--fin-muted)]">Chỉ hiển thị rủi ro cấp doanh nghiệp, không quy trách nhiệm cho hợp đồng đang chọn.</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[10px] text-[var(--fin-muted)]">Highest severity</p>
          <span className={`mt-2 inline-flex rounded-md px-2 py-1 font-mono text-[11px] font-semibold ${
            highestSeverity === "critical" ? "border border-red-500/40 bg-red-500/20 text-red-200"
              : highestSeverity === "high" ? "border border-red-400/30 bg-red-400/[0.12] text-red-300"
                : highestSeverity === "medium" ? "bg-amber-200/10 text-amber-100"
                  : "bg-emerald-300/10 text-emerald-200"
          }`}>{severityLabels[highestSeverity].toUpperCase()}</span>
        </div>
      </header>

      <div className="p-5">
        {!portfolioSource ? (
          <div className="flex min-h-72 flex-col items-center justify-center rounded-lg border border-dashed border-[var(--fin-soft-border)] px-5 text-center">
            <AlertTriangle className="size-5 text-[var(--fin-muted)]" strokeWidth={1.6} aria-hidden="true" />
            <p className="mt-4 text-xs font-semibold text-[var(--fin-text)]">Chưa có rủi ro cấp doanh nghiệp</p>
            <p className="mt-1 max-w-xs text-[11px] leading-5 text-[var(--fin-muted)]">Business health sẽ cập nhật khi Risk Agent trả rule hoặc alert có scope PORTFOLIO.</p>
          </div>
        ) : (
          <>
            {portfolioRisk?.portfolioApprovalRequired && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-red-400/25 bg-red-400/[0.075] px-3.5 py-3 shadow-[inset_3px_0_0_rgba(248,113,113,.8)]">
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="size-3.5 text-red-300" strokeWidth={1.8} aria-hidden="true" />
                  <div>
                    <p className="text-[10px] font-semibold text-red-200">Cần phê duyệt cấp doanh nghiệp</p>
                    <p className="mt-0.5 text-[10px] text-[var(--fin-muted)]">Có giao dịch portfolio cần người có thẩm quyền xem xét.</p>
                  </div>
                </div>
                <span className="font-mono text-[10px] font-semibold text-red-200">PORTFOLIO</span>
              </div>
            )}

            <section className="mt-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--fin-muted)]">Kết quả đánh giá rule</p>
                <span className="font-mono text-[10px] text-[var(--fin-muted)]">{totalRulesEvaluated} evaluations</span>
              </div>
              <div className="mt-3 flex h-3 overflow-hidden rounded-sm bg-white/[0.05]" role="img" aria-label="Kết quả đánh giá các risk rules">
                {evaluationStatuses.map((status) => status.value > 0 && (
                  <span
                    key={status.label}
                    className={status.color}
                    style={{ width: `${(status.value / Math.max(totalRulesEvaluated, 1)) * 100}%` }}
                    title={`${status.label}: ${status.value}`}
                  />
                ))}
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                {evaluationStatuses.map((status) => (
                  <div key={status.label}>
                    <p className="flex items-center gap-1.5 text-[9px] leading-4 text-[var(--fin-muted)]"><span className={`size-1.5 shrink-0 rounded-full ${status.color}`} />{status.label}</p>
                    <p className="mt-1 font-mono text-sm font-semibold text-[var(--fin-text)]">{status.value}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-5 border-t border-[var(--fin-soft-border)] pt-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--fin-muted)]">Alerts detected</p>
                <span className="font-mono text-[10px] text-[var(--fin-muted)]">{totalAlertsDetected}</span>
              </div>
              {activeAlerts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {activeAlerts.map((alert) => (
                    <article key={alert.alertId} className="rounded-lg border border-red-400/20 bg-red-400/[0.045] p-3.5 shadow-[inset_3px_0_0_rgba(248,113,113,.72)]">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-mono text-[9px] font-semibold text-red-300">{alert.alertId}</p>
                          <h4 className="mt-1 text-xs font-semibold text-[var(--fin-text)]">{alert.alertType}</h4>
                        </div>
                        <div className="flex items-center gap-2">
                          {alert.riskScore != null && <span className="font-mono text-[10px] text-[var(--fin-muted)]">score {alert.riskScore}</span>}
                          <RiskBadge level={alert.severity} />
                        </div>
                      </div>
                      <p className="mt-2 text-[10px] leading-4 text-[var(--fin-muted)]">{alert.description}</p>
                      {alert.recommendedAction && <p className="mt-2 border-l border-red-400/45 pl-2 text-[10px] leading-4 text-[var(--fin-text)]">{alert.recommendedAction}</p>}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-[10px] text-[var(--fin-muted)]">Risk Agent không trả về alert nào.</p>
              )}
            </section>

            <section className="mt-5 border-t border-[var(--fin-soft-border)] pt-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--fin-muted)]">Triggered rules</p>
                <span className="font-mono text-[10px] text-[var(--fin-muted)]">{totalRulesTriggered}</span>
              </div>
              {triggeredRules.map((rule) => (
                <div key={rule.title} className="mt-3 grid grid-cols-[auto_1fr] gap-3">
                  <span className="h-fit rounded-md border border-red-400/25 bg-red-400/[0.08] px-2 py-1 font-mono text-[9px] font-semibold text-red-300">{rule.title}</span>
                  <div>
                    <p className="text-[10px] leading-4 text-[var(--fin-muted)]">{rule.description}</p>
                  </div>
                </div>
              ))}
            </section>

            <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--fin-soft-border)] pt-4 text-[9px] text-[var(--fin-muted)]">
              <span>{evidenceGapCount} evidence gaps</span>
              <span>Nguồn: RiskPack portfolio{portfolioSource.runId ? `, run ${portfolioSource.runId}` : ""}</span>
            </footer>
          </>
        )}
      </div>
    </section>
  );
}

type PendingApprovalRequest = {
  approvalId: string;
  contractId: string;
  runId?: number;
  status: string;
  result: {
    eligibleScore: number | null;
    precheckNote: string | null;
  } | null;
  tool: string;
  arguments: Record<string, unknown>;
};

type PrecheckRow = {
  contractId: string;
  runId?: number;
  requestType: string;
  requestedAmount: number | null;
  eligibleScore: number | null;
  precheckNote: string | null;
  approvalStatus: boolean;
  requiresFounderConfirmation: boolean;
  request?: PendingApprovalRequest;
};

const requestTypeLabels: Record<string, string> = {
  PERFORMANCE_BOND: "Bảo lãnh thực hiện",
  TRADE_FINANCE: "Tài trợ thương mại / L/C",
  WORKING_CAPITAL: "Vốn lưu động",
  RECEIVABLE_FINANCING: "Tài trợ khoản phải thu",
};

function BankPrecheckApprovals({
  contracts,
  pendingRequests,
  isLoadingRequests,
  onResult,
  onRequestResolved,
  connectionIssue,
}: {
  contracts: ContractRecord[];
  pendingRequests: Record<string, PendingApprovalRequest>;
  isLoadingRequests: boolean;
  onResult: (contractId: string, result: {
    eligibleScore: number | null;
    precheckNote: string | null;
    approvalStatus: boolean;
  }) => void;
  onRequestResolved: (contractId: string) => void;
  connectionIssue: string;
}) {
  const [processing, setProcessing] = useState<{ contractId: string; approved: boolean } | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, "approved" | "rejected">>({});
  const [notice, setNotice] = useState("");

  const rows = useMemo<PrecheckRow[]>(() => {
    return contracts
      .filter((contract) => (
        contract.bankPrecheck.approvalStatus
        || contract.bankPrecheck.eligibleScore != null
        || Boolean(contract.bankPrecheck.precheckNote)
        || Boolean(pendingRequests[contract.id])
        || (
          contract.bankPrecheck.requiresFounderConfirmation
          && Boolean(contract.bankPrecheck.requestType)
        )
      ))
      .map((contract) => ({
        contractId: contract.id,
        runId: contract.runId,
        requestType: contract.bankPrecheck.requestType || "BANK_PRECHECK",
        requestedAmount: contract.bankPrecheck.requestedAmount,
        eligibleScore: contract.bankPrecheck.eligibleScore
          ?? pendingRequests[contract.id]?.result?.eligibleScore
          ?? null,
        precheckNote: contract.bankPrecheck.precheckNote
          ?? pendingRequests[contract.id]?.result?.precheckNote
          ?? null,
        approvalStatus: contract.bankPrecheck.approvalStatus,
        requiresFounderConfirmation: contract.bankPrecheck.requiresFounderConfirmation,
        request: pendingRequests[contract.id],
      }));
  }, [contracts, pendingRequests]);

  const pendingCount = rows.filter((row) => row.request && !row.approvalStatus && !resolutions[row.contractId]).length;
  const completedCount = rows.filter((row) => row.approvalStatus || resolutions[row.contractId] === "approved").length;
  const eligibleCount = rows.filter((row) => row.eligibleScore != null && row.eligibleScore >= 0.7).length;
  const missingAmountCount = rows.filter((row) => (
    row.requestedAmount == null
    && !row.request
    && !row.approvalStatus
  )).length;

  const submitApproval = async (row: PrecheckRow, approved: boolean) => {
    if (!row.runId || !row.request?.approvalId) return;
    setProcessing({ contractId: row.contractId, approved });
    setNotice("");

    try {
      const response = await fetch(
        apiUrl(`/runs/${row.runId}/approvals/${row.request.approvalId}?approved=${approved}`),
        { method: "POST", headers: API_REQUEST_HEADERS },
      );
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => null) as {
          detail?: { message?: string } | string;
        } | null;
        const detail = errorPayload?.detail;
        const message = typeof detail === "string" ? detail : detail?.message;
        throw new Error(message || `Approval API returned ${response.status}`);
      }
      const payload = await response.json();
      const decision = (payload.decision_result?.decisions ?? []).find(
        (item: { contract_id?: string }) => item.contract_id === row.contractId,
      );
      if (!decision) throw new Error("Updated Decision Card is missing");
      const score = normalizeEligibilityScore(
        decision.eligibility_score ?? decision.eligible_score,
      );
      const approvalExecuted =
        decision.external_api_submission_approval_status === "EXECUTED"
        || decision.approval_status === true;
      if (approved && (score == null || !decision.precheck_note)) {
        throw new Error("Bank precheck did not return score and note");
      }

      onResult(row.contractId, {
        eligibleScore: score ?? null,
        precheckNote: decision.precheck_note ?? null,
        approvalStatus: approvalExecuted,
      });
      setResolutions((current) => ({ ...current, [row.contractId]: approved ? "approved" : "rejected" }));
      onRequestResolved(row.contractId);
      setNotice(
        approved
          ? `Đã chạy bank pre-check cho ${row.contractId} và nhận kết quả mới.`
          : `Đã từ chối quyền gọi bank pre-check cho ${row.contractId}.`,
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Không thể hoàn tất approval.");
    } finally {
      setProcessing(null);
    }
  };

  return (
    <section className="mt-5 overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
      <header className="flex flex-col justify-between gap-4 border-b border-[var(--fin-soft-border)] px-5 py-5 lg:flex-row lg:items-start">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-300">Human-gated bank API</p>
          <h3 className="mt-2 text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Nhu cầu tài chính và chấp thuận kiểm tra ngân hàng</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--fin-muted)]">
            Chỉ hồ sơ đã có số tiền đề nghị mới tạo được approval request. Giá trị hợp đồng không được dùng thay cho số tiền vay hoặc bảo lãnh.
          </p>
        </div>
        <div className="grid grid-cols-4 gap-px overflow-hidden rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-soft-border)]">
          {[
            { label: "Chờ duyệt", value: pendingCount },
            { label: "Thiếu số tiền", value: missingAmountCount },
            { label: "Đã kiểm tra", value: completedCount },
            { label: "Đủ điều kiện", value: eligibleCount },
          ].map((metric) => (
            <div key={metric.label} className="min-w-24 bg-[var(--fin-bg)] px-3 py-2.5 text-center">
              <p className="text-[9px] text-[var(--fin-muted)]">{metric.label}</p>
              <p className="mt-1 font-mono text-base font-semibold text-[var(--fin-text)]">{metric.value}</p>
            </div>
          ))}
        </div>
      </header>

      {rows.length > 0 ? (
        <div className="fin-scrollbar max-w-full overflow-x-auto">
          <table className="w-full min-w-[1080px] border-collapse text-left">
            <thead>
              <tr className="border-b border-[var(--fin-soft-border)] bg-white/[0.018] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--fin-muted)]">
                <th className="px-5 py-3.5">Contract ID</th>
                <th className="px-4 py-3.5">Request type</th>
                <th className="px-4 py-3.5 text-right">Giá trị đề nghị</th>
                <th className="px-4 py-3.5">Eligibility score</th>
                <th className="w-[28%] px-4 py-3.5">Pre-check note</th>
                <th className="px-4 py-3.5">Approval</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isProcessing = processing?.contractId === row.contractId;
                const requestStatus = row.request?.status || "pending";
                const resolution = resolutions[row.contractId];
                const isCompleted = row.approvalStatus || resolution === "approved";
                const isRejected = resolution === "rejected";
                const isMissingRequestedAmount = row.requestedAmount == null
                  && !row.request
                  && !isCompleted;
                const scoreTone = row.eligibleScore == null
                  ? "bg-white/[0.06]"
                  : row.eligibleScore >= 0.7 ? "bg-emerald-300" : "bg-red-400";

                return (
                  <tr key={row.contractId} className="border-b border-[var(--fin-soft-border)]/70 align-top last:border-b-0">
                    <td className="px-5 py-4">
                      <p className="font-mono text-xs font-semibold text-emerald-300">{row.contractId}</p>
                      <p className="mt-1 text-[10px] text-[var(--fin-muted)]">{row.request?.tool || "Decision Agent pre-check"}</p>
                    </td>
                    <td className="px-4 py-4">
                      <p className="text-xs font-medium text-[var(--fin-text)]">{requestTypeLabels[row.requestType] ?? row.requestType.replaceAll("_", " ")}</p>
                      <p className="mt-1 font-mono text-[10px] text-[var(--fin-muted)]">{row.requestType}</p>
                    </td>
                    <td className="px-4 py-4 text-right font-mono text-xs font-semibold text-[var(--fin-text)]">
                      {row.requestedAmount != null ? formatCompactCurrency(row.requestedAmount) : (
                        <div>
                          <span>—</span>
                          <p className="mt-1 font-sans text-[9px] font-normal text-amber-200/80">Chưa cung cấp</p>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      {row.eligibleScore != null ? (
                        <div className="w-32">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className={`font-mono text-lg font-semibold ${row.eligibleScore >= 0.7 ? "text-emerald-300" : "text-red-300"}`}>{formatEligibilityScore(row.eligibleScore)}</span>
                            <span className="text-[9px] text-[var(--fin-muted)]">/ 1</span>
                          </div>
                          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className={`h-full rounded-full ${scoreTone}`} style={{ width: `${row.eligibleScore * 100}%` }} />
                          </div>
                        </div>
                      ) : (
                        <div>
                          <span className="font-mono text-sm text-[var(--fin-muted)]">—</span>
                          <p className="mt-1 text-[9px] text-[var(--fin-muted)]">
                            {isMissingRequestedAmount ? "Sau khi bổ sung số tiền và duyệt" : "Có sau approval"}
                          </p>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <p className={`text-[11px] leading-5 ${row.precheckNote ? "text-[var(--fin-text)]" : "text-[var(--fin-muted)]"}`}>
                        {row.precheckNote || (
                          isMissingRequestedAmount
                            ? "Chưa thể tạo yêu cầu duyệt: cần bổ sung số tiền vay hoặc bảo lãnh đề nghị."
                            : "Chưa gọi API ngân hàng nên chưa có pre-check note."
                        )}
                      </p>
                    </td>
                    <td className="px-4 py-4">
                      {isCompleted ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/20 bg-emerald-400/[0.08] px-2.5 py-1.5 text-[10px] font-semibold text-emerald-300">
                          <Check className="size-3" aria-hidden="true" /> Đã kiểm tra
                        </span>
                      ) : isRejected ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-red-400/25 bg-red-400/[0.08] px-2.5 py-1.5 text-[10px] font-semibold text-red-300">
                          <X className="size-3" aria-hidden="true" /> Đã từ chối
                        </span>
                      ) : isMissingRequestedAmount ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-300/25 bg-amber-300/[0.08] px-2.5 py-1.5 text-[10px] font-semibold text-amber-100">
                          <AlertTriangle className="size-3" aria-hidden="true" /> Cần nhập số tiền
                        </span>
                      ) : row.request && requestStatus === "executing" ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-amber-200">
                          <RefreshCw className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" /> Đang chạy pre-check…
                        </span>
                      ) : row.request ? (
                        <div className="flex items-center gap-2">
                          {requestStatus === "pending" && (
                            <button
                              type="button"
                              onClick={() => void submitApproval(row, false)}
                              disabled={isProcessing}
                              className="min-h-9 rounded-lg border border-red-400/20 px-3 text-[10px] font-semibold text-red-300 transition hover:bg-red-400/[0.08] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300/60"
                            >
                              Từ chối
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => void submitApproval(row, requestStatus !== "rejected")}
                            disabled={isProcessing}
                            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-emerald-300 px-3 text-[10px] font-bold text-[#07110c] transition hover:bg-emerald-200 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200"
                          >
                            {isProcessing ? <RefreshCw className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check className="size-3" aria-hidden="true" />}
                            {isProcessing
                              ? "Đang xử lý…"
                              : requestStatus === "executed"
                                ? "Áp dụng kết quả"
                                : requestStatus === "failed"
                                  ? "Thử lại pre-check"
                                  : requestStatus === "rejected"
                                    ? "Áp dụng từ chối"
                                    : requestStatus === "approved"
                                      ? "Tiếp tục pre-check"
                                      : "Duyệt & kiểm tra"}
                          </button>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-[var(--fin-muted)]">
                          <Clock3 className="size-3" aria-hidden="true" /> {isLoadingRequests ? "Đang tải…" : "Chưa tạo request"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex min-h-52 flex-col items-center justify-center px-5 text-center">
          <ShieldCheck className="size-5 text-[var(--fin-muted)]" strokeWidth={1.7} aria-hidden="true" />
          <p className="mt-4 text-xs font-semibold text-[var(--fin-text)]">Không có bank pre-check đang chờ</p>
          <p className="mt-1 text-[10px] text-[var(--fin-muted)]">Decision Agent chưa tạo approval request cho danh mục hiện tại.</p>
        </div>
      )}

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--fin-soft-border)] px-5 py-3 text-[9px] text-[var(--fin-muted)]" aria-live="polite">
        <span>{notice || connectionIssue || "Approval chỉ cấp quyền cho đúng tool và arguments đã lưu trong StateStore."}</span>
        <span>Nguồn: /dashboard</span>
      </footer>
    </section>
  );
}

export function ContractApprovalWorkspace() {
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [pendingRequests, setPendingRequests] = useState<Record<string, PendingApprovalRequest>>({});
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [query, setQuery] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [apiConnectionIssue, setApiConnectionIssue] = useState("");
  const [approvalDataIssue, setApprovalDataIssue] = useState("");
  const [actionState, setActionState] = useState<"idle" | "saving">("idle");
  const [notice, setNotice] = useState("");
  const [detailRefreshVersion, setDetailRefreshVersion] = useState(0);
  const detailGenerationRef = useRef(0);
  const detailCacheRef = useRef<Map<number, RunDetailPayload>>(new Map());

  const selectedForDetail = contracts.find((item) => item.id === selectedId);
  const selectedRunId = selectedForDetail?.runId;

  const loadContracts = useCallback(async ({
    signal,
    silent = false,
    invalidateDetails = false,
  }: {
    signal?: AbortSignal;
    silent?: boolean;
    invalidateDetails?: boolean;
  } = {}) => {
    if (invalidateDetails) {
      detailGenerationRef.current += 1;
      detailCacheRef.current.clear();
    }
    if (!silent) setIsRefreshing(true);
    setApiConnectionIssue("");
    try {
      const dashboard = await fetchDashboard(signal);
      const apiContracts = dashboard.contracts;
      setContracts(apiContracts);
      setPendingRequests(dashboard.pendingRequests);
      setApprovalDataIssue(dashboard.approvalIssue);
      if (invalidateDetails) {
        setDetailRefreshVersion(detailGenerationRef.current);
      }
      setSelectedId((current) => (
        apiContracts.some((item) => item.id === current)
          ? current
          : (apiContracts[0]?.id ?? "")
      ));
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      if (!silent) {
        setContracts([]);
        setPendingRequests({});
        setSelectedId("");
      }
      setApiConnectionIssue(
        error instanceof Error
          ? `Không kết nối được ${API_BASE_URL}: ${error.message}`
          : `Không kết nối được ${API_BASE_URL}.`,
      );
    } finally {
      if (!silent && !signal?.aborted) setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function hydrateContracts() {
      await loadContracts({ signal: controller.signal });
    }

    void hydrateContracts();
    return () => controller.abort();
  }, [loadContracts]);

  useEffect(() => {
    const controller = new AbortController();

    async function waitBeforeReconnect() {
      await new Promise<void>((resolve) => {
        const timeout = window.setTimeout(resolve, 1_500);
        controller.signal.addEventListener(
          "abort",
          () => {
            window.clearTimeout(timeout);
            resolve();
          },
          { once: true },
        );
      });
    }

    async function connectToDashboardEvents() {
      let reconnecting = false;
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(apiUrl("/dashboard/events"), {
            cache: "no-store",
            headers: {
              Accept: "text/event-stream",
              "Cache-Control": "no-cache",
              ...API_REQUEST_HEADERS,
            },
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`Dashboard event API returned ${response.status}`);
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
            let boundary = buffer.indexOf("\n\n");

            while (boundary >= 0) {
              const block = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              boundary = buffer.indexOf("\n\n");
              const data = block
                .split("\n")
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trimStart())
                .join("\n");
              if (!data) continue;

              const event = JSON.parse(data) as { type?: string };
              if (event.type === "dashboard_ready") {
                if (reconnecting) {
                  reconnecting = false;
                  void loadContracts({ silent: true, invalidateDetails: true });
                }
              } else if (
                event.type === "run_review"
                || event.type === "run_finished"
                || event.type === "decision_updated"
              ) {
                void loadContracts({ silent: true, invalidateDetails: true });
              }
            }
          }
          reconnecting = true;
        } catch (error) {
          if (controller.signal.aborted) return;
          reconnecting = true;
          console.warn("Dashboard realtime connection interrupted", error);
        }

        if (!controller.signal.aborted) await waitBeforeReconnect();
      }
    }

    void connectToDashboardEvents();
    return () => controller.abort();
  }, [loadContracts]);

  useEffect(() => {
    if (!selectedRunId) return;
    const runId = selectedRunId;
    const requestedVersion = detailRefreshVersion;
    const controller = new AbortController();

    async function loadDecisionDetail() {
      try {
        let detailPayload = detailCacheRef.current.get(runId);
        if (!detailPayload) {
          const response = await fetch(apiUrl(`/runs/${runId}/detail`), {
            signal: controller.signal,
            cache: "no-store",
            headers: API_REQUEST_HEADERS,
          });
          if (!response.ok) return;
          detailPayload = await response.json() as RunDetailPayload;
          if (detailGenerationRef.current !== requestedVersion) return;
          detailCacheRef.current.set(runId, detailPayload);
        }
        if (detailGenerationRef.current !== requestedVersion) return;
        const decision = (detailPayload.decisions ?? []).find((item) => item.contract_id === selectedId);
        const risk = (detailPayload.risk_pack?.packs ?? []).find((item) => item.contract_id === selectedId);

        setContracts((current) => current.map((item) => {
          if (item.id !== selectedId) return item;
          const evaluations = risk?.rule_evaluations ?? [];
          const mappedEvaluations = evaluations.map(mapRiskEvaluation);
          const contractEvaluations = mappedEvaluations.filter((entry) => entry.scope === "CONTRACT");
          const portfolioEvaluations = mappedEvaluations.filter((entry) => entry.scope === "PORTFOLIO");
          const contractTriggeredRuleIds = risk?.contract_triggered_rule_ids
            ?? evaluations
              .filter((entry) => normalizeRiskScope(entry.scope) === "CONTRACT" && entry.status === "TRIGGERED")
              .map((entry) => entry.rule_id || "UNKNOWN_RULE");
          const portfolioTriggeredRuleIds = risk?.portfolio_triggered_rule_ids
            ?? evaluations
              .filter((entry) => normalizeRiskScope(entry.scope) === "PORTFOLIO" && entry.status === "TRIGGERED")
              .map((entry) => entry.rule_id || "UNKNOWN_RULE");
          const portfolioRuleIdSet = new Set(portfolioTriggeredRuleIds);
          const mappedAlerts: AgentAlert[] = (risk?.alerts ?? []).flatMap((match) => match.alert ? [{
            alertId: match.alert.alert_id || "UNKNOWN_ALERT",
            alertType: match.alert.alert_type || "Risk alert",
            severity: normalizeRiskLevel(match.alert.severity),
            riskScore: match.alert.risk_score ?? null,
            description: match.alert.description || "",
            recommendedAction: match.alert.recommended_action || "",
            matchedRuleIds: match.matched_rule_ids ?? [],
          }] : []);
          const portfolioAlerts = mappedAlerts.filter((alert) => (
            alert.matchedRuleIds.some((ruleId) => portfolioRuleIdSet.has(ruleId))
          ));
          const contractAlerts = mappedAlerts.filter((alert) => (
            !alert.matchedRuleIds.some((ruleId) => portfolioRuleIdSet.has(ruleId))
          ));
          return {
            ...item,
            aiOption: decision?.recommended_option ?? item.aiOption,
            reasons: decision?.reasons?.length ? decision.reasons : item.reasons,
            safeguards: decision
              ? [
                  decision.protective_condition,
                  ...(decision.required_actions ?? []).map((entry) => (
                    [entry.action, entry.owner ? `Phụ trách: ${entry.owner}` : ""]
                      .filter(Boolean)
                      .join(" · ")
                  )),
                  ...(decision.human_confirmation_points ?? []).map((entry) => (
                    `Cần xác nhận: ${entry}`
                  )),
                ].filter((entry): entry is string => Boolean(entry))
              : item.safeguards,
            bankPrecheck: decision
              ? {
                  ...item.bankPrecheck,
                  available: true,
                  requestType: decision.funding_need_type
                    ?? item.bankPrecheck.requestType,
                  requestedAmount: decision.capital_need ?? item.bankPrecheck.requestedAmount,
                  eligibleScore: normalizeEligibilityScore(
                    decision.eligibility_score ?? decision.eligible_score,
                  ),
                  precheckNote: decision.precheck_note ?? null,
                  approvalStatus:
                    decision.external_api_submission_approval_status === "EXECUTED"
                    || decision.approval_status === true,
                  requiresFounderConfirmation: decision.requires_founder_confirmation ?? false,
                }
              : item.bankPrecheck,
            riskLevel: risk
              ? normalizeRiskLevel(risk.highest_contract_triggered_severity)
              : item.riskLevel,
            agentRisk: risk
              ? {
                  available: true,
                  contractId: item.id,
                  overallRiskLevel: risk.highest_contract_triggered_severity
                    ? normalizeRiskLevel(risk.highest_contract_triggered_severity)
                    : null,
                  totalRulesTriggered: contractTriggeredRuleIds.length,
                  triggeredRuleIds: contractTriggeredRuleIds,
                  totalAlertsDetected: contractAlerts.length,
                  totalProposedAlerts: risk.summary?.total_proposed_alerts ?? risk.proposed_alerts?.length ?? 0,
                  insufficientEvidenceCount: risk.insufficient_evidence?.length ?? 0,
                  humanReviewRequired: risk.summary?.human_review_required
                    ?? risk.manual_evidence_review_required
                    ?? risk.triggered_rule_approval_required
                    ?? risk.human_approval_required
                    ?? false,
                  totalRulesEvaluated: contractEvaluations.length,
                  notTriggeredCount: contractEvaluations.filter((entry) => entry.status === "NOT_TRIGGERED").length,
                  insufficientEvidenceRuleCount: contractEvaluations.filter((entry) => entry.status === "INSUFFICIENT_EVIDENCE").length,
                  triggeredRules: (risk.rule_evaluations ?? [])
                    .filter((entry: { status?: string }) => entry.status === "TRIGGERED")
                    .map((entry: {
                      rule_id?: string;
                      scope?: string;
                      severity?: string;
                      required_action?: string;
                      message?: string;
                    }) => ({
                      ruleId: entry.rule_id || "UNKNOWN_RULE",
                      scope: normalizeRiskScope(entry.scope),
                      severity: normalizeRiskLevel(entry.severity),
                      requiredAction: entry.required_action || "",
                      message: entry.message || "",
                    })),
                  alerts: contractAlerts,
                  evidenceGaps: risk.insufficient_evidence ?? [],
                  requiredActions: risk.required_actions ?? [],
                  portfolioRisks: portfolioEvaluations,
                  portfolioAlerts,
                  highestPortfolioRiskLevel: risk.highest_portfolio_triggered_severity
                    ? normalizeRiskLevel(risk.highest_portfolio_triggered_severity)
                    : null,
                  portfolioApprovalRequired: risk.portfolio_transaction_approval_required ?? false,
                }
              : item.agentRisk,
            risks: contractEvaluations.length
              ? contractEvaluations
              : item.risks,
          };
        }));
      } catch (error) {
        if ((error as Error).name !== "AbortError") setNotice("Chưa tải được chi tiết AI mới nhất; đang hiển thị bản tóm tắt.");
      }
    }

    void loadDecisionDetail();
    return () => controller.abort();
  }, [detailRefreshVersion, selectedId, selectedRunId]);

  const selected = contracts.find((item) => item.id === selectedId) ?? contracts[0];
  const filteredContracts = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("vi");
    return contracts.filter((item) => {
      const matchesFilter = filter === "all" || item.status === filter;
      const matchesQuery = !normalizedQuery || [item.id, item.title, item.counterparty, item.owner]
        .some((value) => value.toLocaleLowerCase("vi").includes(normalizedQuery));
      return matchesFilter && matchesQuery;
    });
  }, [contracts, filter, query]);

  const counts = useMemo(() => ({
    total: contracts.length,
    awaiting: contracts.filter((item) => item.status === "pending" || item.status === "review").length,
    highRisk: contracts.filter((item) => item.agentRisk.available && (item.riskLevel === "high" || item.riskLevel === "critical")).length,
    value: contracts.reduce((sum, item) => sum + (item.amount ?? 0), 0),
  }), [contracts]);

  const updateBankPrecheckResult = (
    contractId: string,
    result: { eligibleScore: number | null; precheckNote: string | null; approvalStatus: boolean },
  ) => {
    setContracts((current) => current.map((contract) => contract.id === contractId
      ? {
          ...contract,
          bankPrecheck: {
            ...contract.bankPrecheck,
            eligibleScore: result.eligibleScore,
            precheckNote: result.precheckNote,
            approvalStatus: result.approvalStatus,
          },
        }
      : contract));
  };

  const resolvePendingRequest = (contractId: string) => {
    setPendingRequests((current) => {
      const next = { ...current };
      delete next[contractId];
      return next;
    });
  };

  const applyDecision = (status: ApprovalStatus) => {
    if (!selected) return;
    setActionState("saving");
    setNotice("");
    setContracts((current) => current.map((item) => item.id === selected.id ? { ...item, status } : item));
    const actionLabel = status === "approved" ? "duyệt" : status === "rejected" ? "từ chối" : "chuyển sang xem xét";
    setNotice(`Đã ${actionLabel} ${selected.id} trong hàng chờ hợp đồng. Quyền gọi API ngân hàng được quản lý riêng ở bảng Bank pre-check bên dưới.`);
    setActionState("idle");
  };

  if (!selected) {
    return (
      <div className="mx-auto flex min-h-[34rem] w-full max-w-[1600px] items-center justify-center">
        <section className="w-full max-w-xl rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-8 text-center">
          {isRefreshing ? (
            <RefreshCw className="mx-auto size-6 animate-spin text-emerald-300 motion-reduce:animate-none" aria-hidden="true" />
          ) : (
            <AlertTriangle className="mx-auto size-6 text-amber-200" aria-hidden="true" />
          )}
          <h1 className="mt-5 text-xl font-semibold text-[var(--fin-text)]">
            {isRefreshing ? "Đang tải dữ liệu thật" : "Không có dữ liệu hợp đồng từ API"}
          </h1>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--fin-muted)]">
            {apiConnectionIssue || "Pipeline hiện chưa trả về hợp đồng nào. Hệ thống không hiển thị dữ liệu thay thế."}
          </p>
          {!isRefreshing && (
            <button
              type="button"
              onClick={() => void loadContracts({ invalidateDetails: true })}
              className="mt-6 inline-flex min-h-10 items-center gap-2 rounded-lg border border-emerald-400/25 bg-emerald-400/[0.08] px-4 text-xs font-semibold text-emerald-200"
            >
              <RefreshCw className="size-3.5" aria-hidden="true" /> Thử kết nối lại
            </button>
          )}
        </section>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      <section className="mb-5 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-2 rounded-md border border-emerald-400/15 bg-emerald-400/[0.06] px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
              <span className="size-1.5 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,.7)]" />
              Approval workspace
            </span>
            <span className="text-xs text-[var(--fin-muted)]">Dữ liệu trực tiếp từ pipeline</span>
          </div>
          <h1 className="mt-4 max-w-3xl text-balance text-3xl font-semibold leading-[1.05] tracking-[-0.055em] text-[var(--fin-text)] sm:text-4xl lg:text-[2.8rem]">
            Hàng chờ phê duyệt hợp đồng
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--fin-muted)]">
            Đối chiếu điều khoản, xem phương án AI và ghi nhận quyết định cuối trên cùng một màn hình.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadContracts({ invalidateDetails: true })}
          disabled={isRefreshing}
          className="inline-flex min-h-10 w-fit items-center gap-2 rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] px-3.5 text-xs font-semibold text-[var(--fin-text)] transition duration-200 hover:border-emerald-400/25 hover:bg-[var(--fin-surface-raised)] active:translate-y-px disabled:cursor-wait disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/70"
        >
          <RefreshCw className={`size-3.5 ${isRefreshing ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />
          Làm mới dữ liệu
        </button>
      </section>

      <section aria-label="Tổng quan phê duyệt" className="grid overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={FileText} label="Tổng hợp đồng" value={String(counts.total).padStart(2, "0")} note="Trong hàng chờ hiện tại" />
        <Metric icon={Clock3} label="Cần quyết định" value={String(counts.awaiting).padStart(2, "0")} note="Bao gồm hồ sơ cần xem xét" />
        <Metric icon={CircleDollarSign} label="Tổng giá trị" value={formatCompactCurrency(counts.value)} note="Giá trị danh nghĩa của danh mục" />
        <Metric icon={AlertTriangle} label="Rủi ro cao" value={String(counts.highRisk).padStart(2, "0")} note="High hoặc critical" />
      </section>

      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_29rem] 2xl:grid-cols-[minmax(0,1fr)_34rem]">
        <section className="min-w-0 overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
          <header className="border-b border-[var(--fin-soft-border)] px-4 py-4 sm:px-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Danh sách hợp đồng</h2>
                <p className="mt-1 text-xs text-[var(--fin-muted)]">Chọn một dòng để xem lý do và rủi ro từ AI.</p>
              </div>
              <label className="relative block w-full lg:max-w-[18rem]">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-[var(--fin-muted)]" aria-hidden="true" />
                <span className="sr-only">Tìm hợp đồng</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Tìm ID, đối tác, người phụ trách…"
                  className="min-h-10 w-full rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-bg)] pl-9 pr-3 text-xs text-[var(--fin-text)] outline-none transition placeholder:text-[var(--fin-muted)] focus:border-emerald-400/35 focus:ring-2 focus:ring-emerald-400/10"
                />
              </label>
            </div>

            <div className="fin-scrollbar mt-4 flex gap-1 overflow-x-auto pb-1" aria-label="Lọc theo trạng thái">
              {filters.map((item) => {
                const count = item.value === "all" ? contracts.length : contracts.filter((contract) => contract.status === item.value).length;
                return (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setFilter(item.value)}
                    className={`inline-flex min-h-8 shrink-0 items-center gap-2 rounded-md px-2.5 text-[11px] font-semibold transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/70 ${
                      filter === item.value
                        ? "bg-emerald-300 text-[#07110c]"
                        : "text-[var(--fin-muted)] hover:bg-white/[0.05] hover:text-[var(--fin-text)]"
                    }`}
                  >
                    {item.label}
                    <span className={`font-mono text-[10px] ${filter === item.value ? "text-[#07110c]/65" : "text-[var(--fin-muted)]"}`}>{count}</span>
                  </button>
                );
              })}
            </div>
          </header>

          <div className="fin-scrollbar max-w-full overflow-x-auto">
            <table className="w-full min-w-[1120px] border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--fin-soft-border)] bg-white/[0.018] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--fin-muted)]">
                  <th className="w-[25%] px-5 py-3.5">Hợp đồng</th>
                  <th className="px-4 py-3.5 text-right">Giá trị</th>
                  <th className="px-4 py-3.5">Thời hạn</th>
                  <th className="px-4 py-3.5">Hình thức trả</th>
                  <th className="px-4 py-3.5">AI đề xuất</th>
                  <th className="px-4 py-3.5">Quyết định</th>
                  <th className="w-10 px-3 py-3.5"><span className="sr-only">Mở chi tiết</span></th>
                </tr>
              </thead>
              <tbody>
                {filteredContracts.map((item) => {
                  const isSelected = item.id === selected.id;
                  return (
                    <tr
                      key={item.id}
                      onClick={() => { setSelectedId(item.id); setNotice(""); }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedId(item.id);
                          setNotice("");
                        }
                      }}
                      tabIndex={0}
                      aria-selected={isSelected}
                      className={`group cursor-pointer border-b border-[var(--fin-soft-border)]/70 outline-none transition duration-200 last:border-b-0 focus-visible:bg-emerald-400/[0.06] ${
                        isSelected ? "bg-emerald-400/[0.055]" : "hover:bg-white/[0.025]"
                      }`}
                    >
                      <td className="px-5 py-4">
                        <div className="flex items-start gap-3">
                          <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border ${isSelected ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : "border-[var(--fin-soft-border)] bg-white/[0.025] text-[var(--fin-muted)]"}`}>
                            <FileText className="size-3.5" strokeWidth={1.8} aria-hidden="true" />
                          </span>
                          <span className="min-w-0">
                            <span className="flex items-center gap-2">
                              <span className="font-mono text-[11px] font-semibold text-emerald-300">{item.id}</span>
                              {item.agentRisk.available ? (
                                <RiskBadge level={item.riskLevel} />
                              ) : (
                                <span className="rounded border border-[var(--fin-soft-border)] px-2 py-1 text-[9px] font-medium text-[var(--fin-muted)]">Chưa có RiskPack</span>
                              )}
                            </span>
                            <span className="mt-1 block max-w-[17rem] truncate text-xs font-semibold text-[var(--fin-text)]">{item.title}</span>
                            <span className="mt-1 block text-[11px] text-[var(--fin-muted)]">{item.counterparty}</span>
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right align-top">
                        <span className="font-mono text-xs font-semibold tabular-nums text-[var(--fin-text)]">{formatCompactCurrency(item.amount)}</span>
                        <span className="mt-1 block text-[10px] text-[var(--fin-muted)]">Nhập {formatSubmittedAt(item.submittedAt)}</span>
                      </td>
                      <td className="px-4 py-4 align-top text-[11px] leading-5 text-[var(--fin-muted)]">
                        <span className="block text-[var(--fin-text)]">{formatDate(item.startDate)}</span>
                        <span>đến {formatDate(item.endDate)}</span>
                      </td>
                      <td className="max-w-[12rem] px-4 py-4 align-top text-[11px] leading-5 text-[var(--fin-muted)]">
                        <span className="line-clamp-2">{item.paymentTerms}</span>
                      </td>
                      <td className="px-4 py-4 align-top">
                        <span className="block max-w-[10rem] text-[11px] font-semibold leading-5 text-[var(--fin-text)]">{optionLabels[item.aiOption] ?? item.aiOption}</span>
                        <span className="mt-1 flex items-center gap-1.5 text-[10px] text-[var(--fin-muted)]">
                          <Sparkles className="size-3 text-emerald-300" aria-hidden="true" />
                          {item.aiConfidence == null ? "Chưa có độ tin cậy dữ liệu" : `Tin cậy dữ liệu ${item.aiConfidence}%`}
                        </span>
                      </td>
                      <td className="px-4 py-4 align-top"><StatusBadge status={item.status} /></td>
                      <td className="px-3 py-4 align-middle">
                        <ChevronRight className={`size-4 transition duration-200 ${isSelected ? "translate-x-0.5 text-emerald-300" : "text-[var(--fin-muted)] group-hover:translate-x-0.5 group-hover:text-[var(--fin-text)]"}`} aria-hidden="true" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {filteredContracts.length === 0 && (
            <div className="flex min-h-64 flex-col items-center justify-center px-5 text-center">
              <Search className="size-5 text-[var(--fin-muted)]" aria-hidden="true" />
              <h3 className="mt-4 text-sm font-semibold text-[var(--fin-text)]">Không có hợp đồng phù hợp</h3>
              <p className="mt-1 max-w-xs text-xs leading-5 text-[var(--fin-muted)]">Thử đổi trạng thái lọc hoặc tìm bằng mã hợp đồng khác.</p>
            </div>
          )}

          <footer className="flex items-center justify-between border-t border-[var(--fin-soft-border)] px-5 py-3 text-[10px] text-[var(--fin-muted)]">
            <span>Hiển thị {filteredContracts.length} / {contracts.length} hợp đồng</span>
            <span className="font-mono">LATEST_ONLY · TRUE</span>
          </footer>
        </section>

        <aside className="min-w-0 self-start overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] xl:sticky xl:top-5">
          <header className="border-b border-[var(--fin-soft-border)] p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="font-mono text-[11px] font-semibold text-emerald-300">{selected.id}</p>
                <h2 className="mt-2 text-pretty text-lg font-semibold leading-6 tracking-[-0.035em] text-[var(--fin-text)]">{selected.title}</h2>
                <p className="mt-1.5 text-xs text-[var(--fin-muted)]">{selected.counterparty}</p>
              </div>
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300">
                <Sparkles className="size-4" strokeWidth={1.8} aria-hidden="true" />
              </span>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-soft-border)]">
              <div className="bg-[var(--fin-bg)] p-3">
                <p className="text-[10px] text-[var(--fin-muted)]">Giá trị</p>
                <p className="mt-1 font-mono text-xs font-semibold text-[var(--fin-text)]">{formatCompactCurrency(selected.amount)}</p>
              </div>
              <div className="bg-[var(--fin-bg)] p-3">
                <p className="text-[10px] text-[var(--fin-muted)]">Mức rủi ro</p>
                <div className="mt-1">
                  {selected.agentRisk.available ? <RiskBadge level={selected.riskLevel} /> : <span className="text-[10px] font-medium text-[var(--fin-muted)]">Chờ Risk Agent</span>}
                </div>
              </div>
            </div>
          </header>

          <div className="fin-scrollbar max-h-[calc(100dvh-15rem)] overflow-y-auto p-5">
            <section>
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--fin-muted)]">AI đề xuất</p>
                <span className="font-mono text-[10px] text-emerald-300">
                  {selected.aiConfidence == null ? "NO DATA CONFIDENCE" : `${selected.aiConfidence}% DATA CONFIDENCE`}
                </span>
              </div>
              <p className="mt-2 text-sm font-semibold tracking-[-0.02em] text-[var(--fin-text)]">{optionLabels[selected.aiOption] ?? selected.aiOption}</p>
              {selected.aiConfidence != null && (
                <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-emerald-300 transition-[width] duration-500" style={{ width: `${selected.aiConfidence}%` }} />
                </div>
              )}
            </section>

            {selected.bankPrecheck.requestType && selected.bankPrecheck.requestedAmount == null && (
              <section className="mt-5 rounded-lg border border-amber-300/25 bg-amber-300/[0.07] p-3.5">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-200" strokeWidth={1.8} aria-hidden="true" />
                  <div>
                    <p className="text-[10px] font-semibold text-amber-100">Chưa có yêu cầu duyệt ngân hàng</p>
                    <p className="mt-1 text-[10px] leading-4 text-[var(--fin-muted)]">
                      {formatCompactCurrency(selected.amount)} là giá trị hợp đồng, không phải số tiền vay hoặc bảo lãnh đề nghị. Cần bổ sung số tiền đề nghị trước khi Decision Agent có thể tạo approval request.
                    </p>
                  </div>
                </div>
              </section>
            )}

            <section className="mt-6 rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-bg)]/70 p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.11em] text-emerald-300">Vì sao AI đưa ra phương án này</p>
              <ol className="mt-4 space-y-3">
                {selected.reasons.map((reason, index) => (
                  <li key={`${selected.id}-reason-${index}`} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 rounded-lg bg-white/[0.035] px-3.5 py-3.5 ring-1 ring-inset ring-white/[0.055]">
                    <span className="flex size-7 items-center justify-center rounded-md bg-emerald-400/[0.09] font-mono text-[10px] font-semibold text-emerald-200">{String(index + 1).padStart(2, "0")}</span>
                    <span className="text-pretty text-sm font-medium leading-6 text-[var(--fin-text)]">{reason}</span>
                  </li>
                ))}
                {selected.reasons.length === 0 && (
                  <li className="rounded-lg border border-dashed border-[var(--fin-soft-border)] px-4 py-5 text-sm leading-6 text-[var(--fin-muted)]">Decision Agent chưa trả lý do cho hợp đồng này.</li>
                )}
              </ol>
            </section>

            <section className="mt-6 border-t border-[var(--fin-soft-border)] pt-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--fin-muted)]">Rule rủi ro của hợp đồng</p>
                <span className="font-mono text-[10px] text-[var(--fin-muted)]">{selected.agentRisk.available ? `${selected.risks.length} items` : "NO RISK PACK"}</span>
              </div>
              {selected.agentRisk.available ? (
                <div className="mt-3 space-y-2">
                  {selected.risks.map((risk, index) => (
                    <article
                      key={`${selected.id}-risk-${index}`}
                      className={`rounded-lg border p-3.5 ${
                        risk.status === "TRIGGERED"
                          ? "border-red-400/25 bg-red-400/[0.07]"
                          : risk.status === "INSUFFICIENT_EVIDENCE"
                            ? "border-amber-300/20 bg-amber-300/[0.055]"
                            : "border-emerald-400/20 bg-emerald-400/[0.055]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className={`text-sm font-semibold ${
                            risk.status === "TRIGGERED"
                              ? "text-red-100"
                              : risk.status === "INSUFFICIENT_EVIDENCE"
                                ? "text-amber-100"
                                : "text-emerald-100"
                          }`}>{risk.title}</h3>
                          <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.08em] text-[var(--fin-muted)]">{risk.status.replaceAll("_", " ")}</p>
                        </div>
                        <RuleStatusBadge status={risk.status} />
                      </div>
                      <p className="mt-3 text-xs leading-5 text-[var(--fin-muted)]">{risk.description}</p>
                    </article>
                  ))}
                  {selected.risks.length === 0 && (
                    <div className="flex items-start gap-3 rounded-lg border border-emerald-400/20 bg-emerald-400/[0.055] p-4">
                      <Check className="mt-0.5 size-4 shrink-0 text-emerald-300" strokeWidth={2} aria-hidden="true" />
                      <div>
                        <p className="text-sm font-semibold text-emerald-100">Không có rủi ro gắn với hợp đồng</p>
                        <p className="mt-1 text-xs leading-5 text-[var(--fin-muted)]">Các rule scope CONTRACT không ghi nhận rủi ro cho hợp đồng này. Rủi ro doanh nghiệp được đặt tại Business health.</p>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-3 rounded-lg border border-dashed border-[var(--fin-soft-border)] px-3.5 py-4">
                  <p className="text-[11px] leading-5 text-[var(--fin-muted)]">Chưa có RiskPack thật cho hợp đồng này. Dashboard sẽ hiển thị rule evaluations sau khi Risk Agent hoàn tất.</p>
                </div>
              )}
            </section>

            <section className="mt-6 border-t border-[var(--fin-soft-border)] pt-5">
              <div className="flex items-center gap-2 text-emerald-300">
                <ShieldCheck className="size-3.5" strokeWidth={1.8} aria-hidden="true" />
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em]">Điều kiện bảo vệ</p>
              </div>
              <ul className="mt-3 space-y-2.5">
                {selected.safeguards.map((safeguard, index) => (
                  <li key={`${selected.id}-safeguard-${index}`} className="flex gap-2.5 text-[11px] leading-5 text-[var(--fin-muted)]">
                    <Check className="mt-1 size-3 shrink-0 text-emerald-300" strokeWidth={2} aria-hidden="true" />
                    <span>{safeguard}</span>
                  </li>
                ))}
                {selected.safeguards.length === 0 && (
                  <li className="text-[11px] leading-5 text-[var(--fin-muted)]">Decision Agent chưa trả điều kiện bảo vệ.</li>
                )}
              </ul>
            </section>

            <section className="mt-6 border-t border-[var(--fin-soft-border)] pt-5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--fin-muted)]">Thông tin đã nhập</p>
              <dl className="mt-3 space-y-2.5 text-[11px]">
                <div className="flex items-start justify-between gap-4"><dt className="text-[var(--fin-muted)]">Loại hợp đồng</dt><dd className="text-right font-medium text-[var(--fin-text)]">{selected.contractType}</dd></div>
                <div className="flex items-start justify-between gap-4"><dt className="text-[var(--fin-muted)]">Thanh toán</dt><dd className="max-w-[13rem] text-right font-medium leading-4 text-[var(--fin-text)]">{selected.paymentTerms}</dd></div>
                <div className="flex items-start justify-between gap-4"><dt className="text-[var(--fin-muted)]">Phụ trách</dt><dd className="text-right font-medium text-[var(--fin-text)]">{selected.owner}</dd></div>
                <div className="flex items-start justify-between gap-4"><dt className="text-[var(--fin-muted)]">Thời hạn</dt><dd className="text-right font-mono text-[var(--fin-text)]">{formatDate(selected.startDate)} — {formatDate(selected.endDate)}</dd></div>
              </dl>
              <p className="mt-3 rounded-lg bg-[var(--fin-bg)] p-3 text-[11px] leading-5 text-[var(--fin-muted)]">{selected.summary}</p>
            </section>
          </div>

          <footer className="border-t border-[var(--fin-soft-border)] bg-[var(--fin-bg)]/70 p-4">
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => void applyDecision("rejected")}
                disabled={actionState === "saving"}
                className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-rose-300/15 bg-rose-300/[0.04] px-2 text-[11px] font-semibold text-rose-200 transition duration-200 hover:bg-rose-300/[0.09] active:translate-y-px disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300/60"
              >
                <X className="size-3.5" aria-hidden="true" /> Từ chối
              </button>
              <button
                type="button"
                onClick={() => void applyDecision("review")}
                disabled={actionState === "saving"}
                className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-amber-300/15 bg-amber-300/[0.04] px-2 text-[11px] font-semibold text-amber-100 transition duration-200 hover:bg-amber-300/[0.09] active:translate-y-px disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/60"
              >
                <Eye className="size-3.5" aria-hidden="true" /> Xem xét
              </button>
              <button
                type="button"
                onClick={() => void applyDecision("approved")}
                disabled={actionState === "saving"}
                className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg bg-emerald-300 px-2 text-[11px] font-bold text-[#07110c] transition duration-200 hover:bg-emerald-200 active:translate-y-px disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--fin-bg)]"
              >
                <Check className="size-3.5" aria-hidden="true" /> Phê duyệt
              </button>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-[10px] text-[var(--fin-muted)]" aria-live="polite">
              <span className="line-clamp-2">{notice || `Trạng thái hiện tại: ${statusLabels[selected.status]}`}</span>
              <a href={`/agent?contract=${selected.id}`} className="inline-flex shrink-0 items-center gap-1 font-semibold text-emerald-300 transition hover:text-emerald-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/60">
                Mở pipeline <ArrowUpRight className="size-3" aria-hidden="true" />
              </a>
            </div>
          </footer>
        </aside>
      </div>

      <section className="mt-12 border-t border-[var(--fin-soft-border)] pt-8">
        <header className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-emerald-300">Business health</p>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.035em] text-[var(--fin-text)]">Tài chính và rủi ro doanh nghiệp</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-5 text-[var(--fin-muted)]">Bối cảnh toàn hệ thống để theo dõi sức khỏe doanh nghiệp. Các tín hiệu tại đây không được xem là rủi ro của hợp đồng đang chọn.</p>
          </div>
          <p className="font-mono text-[10px] text-[var(--fin-muted)]">CẬP NHẬT TỪ DANH MỤC HIỆN TẠI</p>
        </header>

        <div>
          <EnterpriseRiskChart contracts={contracts} />
        </div>

        <BankPrecheckApprovals
          contracts={contracts}
          pendingRequests={pendingRequests}
          isLoadingRequests={isRefreshing}
          onResult={updateBankPrecheckResult}
          onRequestResolved={resolvePendingRequest}
          connectionIssue={apiConnectionIssue || approvalDataIssue}
        />
      </section>
    </div>
  );
}
