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
import { useEffect, useMemo, useState } from "react";
import { CashFlowChart } from "./cash-flow-chart";

type ApprovalStatus = "pending" | "approved" | "review" | "rejected";
type RiskLevel = "low" | "medium" | "high" | "critical";
type FilterStatus = "all" | ApprovalStatus;

type ContractRisk = {
  title: string;
  description: string;
  severity: RiskLevel;
};

type AgentTriggeredRule = {
  ruleId: string;
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
  amount: number;
  startDate: string;
  endDate: string;
  submittedAt: string;
  paymentTerms: string;
  contractType: string;
  owner: string;
  summary: string;
  aiOption: string;
  aiConfidence: number;
  reasons: string[];
  risks: ContractRisk[];
  safeguards: string[];
  riskLevel: RiskLevel;
  status: ApprovalStatus;
  source: "api" | "demo";
  agentRisk: AgentRiskSnapshot;
  bankPrecheck: BankPrecheck;
};

type ApiContract = {
  session_id: number;
  contract_id: string;
  generated_at?: string | null;
  finance?: {
    contract_name?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    funding_need_type?: string | null;
    requested_amount?: number | null;
    contract_value?: number | null;
    gross_margin?: number | null;
    status?: string | null;
    additional_funding_need?: number | null;
    worst_month_after?: number | null;
  } | null;
  risk?: {
    overall_risk_level?: string | null;
    human_approval_required?: boolean | null;
    triggered_rule_ids?: string[];
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
      severity?: string | null;
      required_action?: string | null;
      message?: string | null;
    }>;
    alerts?: Array<{
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
    capital_need?: number | null;
    requires_founder_confirmation?: boolean | null;
    approval_status?: boolean | null;
    eligible_score?: number | null;
    precheck_note?: string | null;
    is_preliminary?: boolean | null;
  } | null;
};

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://cc10-113-23-125-3.ngrok-free.app"
).replace(/\/+$/, "");
const API_REQUEST_HEADERS = {
  "ngrok-skip-browser-warning": "true",
};

const demoContracts: ContractRecord[] = [
  {
    id: "CON-004",
    title: "Triển khai mạng lưới hợp tác xã 20 tỉnh",
    counterparty: "Liên minh HTX Bình Minh",
    amount: 4_200_000_000,
    startDate: "2026-06-01",
    endDate: "2027-03-31",
    submittedAt: "2026-07-18T09:42:00+07:00",
    paymentTerms: "Bảo lãnh thực hiện · thanh toán theo nghiệm thu",
    contractType: "Mở rộng vận hành",
    owner: "Nguyễn Thanh Hà",
    summary: "Mở rộng nền tảng điều phối và báo cáo cho 20 đơn vị cấp tỉnh, triển khai theo ba giai đoạn.",
    aiOption: "APPROVE_WITH_CONDITION",
    aiConfidence: 78,
    reasons: [
      "Biên lợi nhuận 24% vẫn cao hơn ngưỡng tối thiểu của danh mục.",
      "Dòng tiền âm sâu nhất rơi vào giai đoạn triển khai thứ hai trước khi nghiệm thu.",
      "Giá trị hợp đồng vượt hạn mức tự phê duyệt và cần xác nhận của nhà sáng lập.",
    ],
    risks: [
      {
        title: "Áp lực vốn lưu động",
        description: "Khoảng trống tiền mặt có thể kéo dài 6–8 tuần nếu biên bản nghiệm thu giai đoạn hai chậm.",
        severity: "high",
      },
      {
        title: "Rủi ro bảo lãnh thực hiện",
        description: "Ngân hàng có thể yêu cầu ký quỹ bổ sung khi tiến độ giải ngân lệch kế hoạch.",
        severity: "medium",
      },
    ],
    safeguards: [
      "Chỉ khởi động giai đoạn hai sau khi nhận đủ 30% giá trị nghiệm thu đầu tiên.",
      "Duy trì quỹ dự phòng tối thiểu 620 triệu đồng trong suốt thời gian triển khai.",
    ],
    riskLevel: "high",
    status: "review",
    source: "demo",
    agentRisk: {
      available: false,
      contractId: "CON-004",
      overallRiskLevel: null,
      totalRulesTriggered: 0,
      triggeredRuleIds: [],
      totalAlertsDetected: 0,
      totalProposedAlerts: 0,
      insufficientEvidenceCount: 0,
      humanReviewRequired: false,
      totalRulesEvaluated: 0,
      notTriggeredCount: 0,
      insufficientEvidenceRuleCount: 0,
      triggeredRules: [],
      alerts: [],
      evidenceGaps: [],
      requiredActions: [],
    },
    bankPrecheck: {
      available: false,
      requestType: null,
      requestedAmount: null,
      eligibleScore: null,
      precheckNote: null,
      approvalStatus: false,
      requiresFounderConfirmation: false,
    },
  },
  {
    id: "CON-005",
    title: "Quy trình chứng từ và báo cáo thương mại",
    counterparty: "An Phú Export Services",
    amount: 1_850_000_000,
    startDate: "2026-06-08",
    endDate: "2026-12-31",
    submittedAt: "2026-07-17T15:18:00+07:00",
    paymentTerms: "L/C trả chậm · 30/70",
    contractType: "Tài trợ thương mại",
    owner: "Trần Minh Khoa",
    summary: "Số hoá luồng chứng từ xuất khẩu, đối soát vận chuyển và lập báo cáo theo từng lô hàng.",
    aiOption: "REJECT_MISSING_EVIDENCE",
    aiConfidence: 84,
    reasons: [
      "Chưa có xác nhận có hiệu lực từ nhà cung cấp nước ngoài.",
      "Hồ sơ bảo hiểm vận chuyển thiếu phạm vi bồi thường do chậm giao hàng.",
      "Thời gian thu tiền dự kiến dài hơn chu kỳ thanh toán nhà cung cấp 47 ngày.",
    ],
    risks: [
      {
        title: "Thiếu chứng từ trọng yếu",
        description: "Chữ ký nhà cung cấp và giấy phép vận chuyển chưa được xác minh độc lập.",
        severity: "critical",
      },
      {
        title: "Lệch chu kỳ thanh toán",
        description: "Doanh nghiệp phải ứng vốn trước khi ngân hàng giải phóng khoản L/C.",
        severity: "high",
      },
    ],
    safeguards: [
      "Tạm dừng phát hành L/C cho đến khi hồ sơ được công chứng và đối chiếu.",
      "Bổ sung bảo hiểm trì hoãn vận chuyển vào điều kiện giải ngân.",
    ],
    riskLevel: "critical",
    status: "pending",
    source: "demo",
    agentRisk: {
      available: false,
      contractId: "CON-005",
      overallRiskLevel: null,
      totalRulesTriggered: 0,
      triggeredRuleIds: [],
      totalAlertsDetected: 0,
      totalProposedAlerts: 0,
      insufficientEvidenceCount: 0,
      humanReviewRequired: false,
      totalRulesEvaluated: 0,
      notTriggeredCount: 0,
      insufficientEvidenceRuleCount: 0,
      triggeredRules: [],
      alerts: [],
      evidenceGaps: [],
      requiredActions: [],
    },
    bankPrecheck: {
      available: false,
      requestType: null,
      requestedAmount: null,
      eligibleScore: null,
      precheckNote: null,
      approvalStatus: false,
      requiresFounderConfirmation: false,
    },
  },
  {
    id: "CON-003",
    title: "Tự động hoá trung tâm chăm sóc khách hàng",
    counterparty: "Tân Cảng Digital",
    amount: 1_250_000_000,
    startDate: "2026-05-16",
    endDate: "2026-11-30",
    submittedAt: "2026-07-17T10:05:00+07:00",
    paymentTerms: "Theo mốc · 30/40/30",
    contractType: "Triển khai phần mềm",
    owner: "Lê Gia Hân",
    summary: "Tích hợp tổng đài, phân loại yêu cầu và dashboard SLA trên hạ tầng hiện hữu của khách hàng.",
    aiOption: "APPROVE_WITH_CONDITION",
    aiConfidence: 72,
    reasons: [
      "Biên lợi nhuận dự kiến 31% tạo đủ vùng đệm cho chi phí triển khai.",
      "Kế hoạch nhân sự phụ thuộc vào một nhóm kỹ thuật đang vận hành dự án khác.",
      "Mốc thanh toán cuối chỉ được kích hoạt sau nghiệm thu toàn bộ SLA.",
    ],
    risks: [
      {
        title: "Nút thắt nhân sự",
        description: "Hai kỹ sư tích hợp chủ chốt đang được phân bổ đồng thời cho dự án CON-002.",
        severity: "medium",
      },
    ],
    safeguards: ["Khoá lịch đội tích hợp trước ngày khởi động và bổ sung nguồn lực dự phòng theo tuần."],
    riskLevel: "medium",
    status: "pending",
    source: "demo",
    agentRisk: {
      available: false,
      contractId: "CON-003",
      overallRiskLevel: null,
      totalRulesTriggered: 0,
      triggeredRuleIds: [],
      totalAlertsDetected: 0,
      totalProposedAlerts: 0,
      insufficientEvidenceCount: 0,
      humanReviewRequired: false,
      totalRulesEvaluated: 0,
      notTriggeredCount: 0,
      insufficientEvidenceRuleCount: 0,
      triggeredRules: [],
      alerts: [],
      evidenceGaps: [],
      requiredActions: [],
    },
    bankPrecheck: {
      available: false,
      requestType: null,
      requestedAmount: null,
      eligibleScore: null,
      precheckNote: null,
      approvalStatus: false,
      requiresFounderConfirmation: false,
    },
  },
  {
    id: "CON-002",
    title: "Thiết lập luồng xử lý đơn hàng ERP-light",
    counterparty: "Thịnh Vượng Retail",
    amount: 980_000_000,
    startDate: "2026-05-05",
    endDate: "2026-09-30",
    submittedAt: "2026-07-15T14:26:00+07:00",
    paymentTerms: "Theo tiến độ · 40/30/30",
    contractType: "Tích hợp hệ thống",
    owner: "Phạm Quốc Bảo",
    summary: "Chuẩn hoá quy trình đơn hàng, tồn kho và phê duyệt chiết khấu cho 12 điểm bán.",
    aiOption: "APPROVE",
    aiConfidence: 86,
    reasons: [
      "Đối tác có lịch sử thanh toán đúng hạn trong 18 tháng gần nhất.",
      "Khoản tạm ứng 40% đủ bù chi phí triển khai ban đầu.",
      "Phạm vi và tiêu chí nghiệm thu đã được định lượng trong phụ lục.",
    ],
    risks: [
      {
        title: "Áp lực biên lợi nhuận",
        description: "Chi phí tích hợp tăng trên 9% sẽ đưa biên dự án xuống gần ngưỡng cảnh báo.",
        severity: "low",
      },
    ],
    safeguards: ["Mọi yêu cầu ngoài phạm vi phải được định giá và ký phụ lục trước khi thực hiện."],
    riskLevel: "low",
    status: "approved",
    source: "demo",
    agentRisk: {
      available: false,
      contractId: "CON-002",
      overallRiskLevel: null,
      totalRulesTriggered: 0,
      triggeredRuleIds: [],
      totalAlertsDetected: 0,
      totalProposedAlerts: 0,
      insufficientEvidenceCount: 0,
      humanReviewRequired: false,
      totalRulesEvaluated: 0,
      notTriggeredCount: 0,
      insufficientEvidenceRuleCount: 0,
      triggeredRules: [],
      alerts: [],
      evidenceGaps: [],
      requiredActions: [],
    },
    bankPrecheck: {
      available: false,
      requestType: null,
      requestedAmount: null,
      eligibleScore: null,
      precheckNote: null,
      approvalStatus: false,
      requiresFounderConfirmation: false,
    },
  },
  {
    id: "CON-001",
    title: "Dịch vụ hỗ trợ vận hành định kỳ",
    counterparty: "Nam Việt Logistics",
    amount: 720_000_000,
    startDate: "2026-04-20",
    endDate: "2026-10-20",
    submittedAt: "2026-07-14T08:54:00+07:00",
    paymentTerms: "Thanh toán hàng tháng · Net 15",
    contractType: "Dịch vụ định kỳ",
    owner: "Vũ Khánh Linh",
    summary: "Vận hành báo cáo quản trị, kiểm soát SLA và hỗ trợ xử lý sự cố theo tháng.",
    aiOption: "APPROVE",
    aiConfidence: 91,
    reasons: [
      "Doanh thu định kỳ và lịch thanh toán Net 15 giúp dòng tiền ổn định.",
      "Biên lợi nhuận 30% cao hơn mức trung vị của nhóm dịch vụ.",
      "Không có cảnh báo tuân thủ hoặc giao dịch bất thường liên quan đến đối tác.",
    ],
    risks: [
      {
        title: "Rủi ro tập trung thấp",
        description: "Giá trị hợp đồng chiếm 7,4% doanh thu dự kiến của danh mục hiện tại.",
        severity: "low",
      },
    ],
    safeguards: ["Đối soát SLA và công nợ vào ngày làm việc cuối cùng mỗi tháng."],
    riskLevel: "low",
    status: "approved",
    source: "demo",
    agentRisk: {
      available: false,
      contractId: "CON-001",
      overallRiskLevel: null,
      totalRulesTriggered: 0,
      triggeredRuleIds: [],
      totalAlertsDetected: 0,
      totalProposedAlerts: 0,
      insufficientEvidenceCount: 0,
      humanReviewRequired: false,
      totalRulesEvaluated: 0,
      notTriggeredCount: 0,
      insufficientEvidenceRuleCount: 0,
      triggeredRules: [],
      alerts: [],
      evidenceGaps: [],
      requiredActions: [],
    },
    bankPrecheck: {
      available: false,
      requestType: null,
      requestedAmount: null,
      eligibleScore: null,
      precheckNote: null,
      approvalStatus: false,
      requiresFounderConfirmation: false,
    },
  },
];

const optionLabels: Record<string, string> = {
  APPROVE: "Nên duyệt",
  APPROVE_WITH_CONDITION: "Duyệt có điều kiện",
  REJECT_MISSING_EVIDENCE: "Từ chối · thiếu hồ sơ",
  NO_SUITABLE_PRODUCT: "Chưa có phương án phù hợp",
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

function normalizeStatus(value?: string | null, approvalStatus?: boolean | null): ApprovalStatus {
  if (approvalStatus) return "approved";
  if (value === "reject") return "rejected";
  if (value === "review") return "review";
  return "pending";
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
  const riskLevel = normalizeRiskLevel(decision.risk_level ?? item.risk?.overall_risk_level);
  const triggeredRules = item.risk?.triggered_rule_ids ?? [];
  const contractValue = finance.contract_value ?? finance.requested_amount ?? 0;

  return {
    id: item.contract_id,
    runId: item.session_id,
    title: finance.contract_name || `Hợp đồng ${item.contract_id}`,
    counterparty: "Đối tác đã nhập từ hồ sơ",
    amount: contractValue,
    startDate: finance.start_date || "",
    endDate: finance.end_date || "",
    submittedAt: item.generated_at || new Date().toISOString(),
    paymentTerms: paymentLabel(finance.funding_need_type),
    contractType: finance.funding_need_type?.replaceAll("_", " ") || "Hợp đồng thương mại",
    owner: "Finance team",
    summary: finance.status
      ? `Hồ sơ đã hoàn tất bước ${finance.status.toLowerCase()} và đang chờ quyết định cuối.`
      : "Hồ sơ hợp đồng được nhập vào pipeline phân tích tài chính và rủi ro.",
    aiOption: decision.recommended_option || "PENDING_ANALYSIS",
    aiConfidence: riskLevel === "low" ? 88 : riskLevel === "medium" ? 76 : 68,
    reasons: [
      `Giá trị hợp đồng ${formatCompactCurrency(contractValue)} đã được đối chiếu với năng lực vốn hiện tại.`,
      finance.gross_margin != null
        ? `Biên lợi nhuận dự kiến ${(finance.gross_margin * 100).toFixed(1)}% theo phân tích tài chính.`
        : "AI đang hoàn thiện đối chiếu biên lợi nhuận và dòng tiền.",
      decision.requires_founder_confirmation
        ? "Quyết định cần người có thẩm quyền xác nhận trước khi thực thi."
        : "Hồ sơ nằm trong hạn mức phê duyệt hiện tại.",
    ],
    risks: triggeredRules.length
      ? triggeredRules.slice(0, 3).map((ruleId) => ({
          title: `Quy tắc ${ruleId}`,
          description: "Quy tắc kiểm soát đã được kích hoạt; mở Decision Card để xem bằng chứng chi tiết.",
          severity: riskLevel,
        }))
      : [{
          title: "Chưa ghi nhận cảnh báo trọng yếu",
          description: "AI không tìm thấy quy tắc rủi ro nào bị kích hoạt trong dữ liệu hiện có.",
          severity: "low",
        }],
    safeguards: [
      "Xác minh lại điều kiện thanh toán và bộ chứng từ trước khi ký quyết định.",
      "Theo dõi chênh lệch dòng tiền trong suốt thời gian thực hiện hợp đồng.",
    ],
    riskLevel,
    status: normalizeStatus(decision.decision_status, decision.approval_status),
    source: "api",
    agentRisk: {
      available: Boolean(item.risk),
      contractId: item.contract_id,
      overallRiskLevel: item.risk?.overall_risk_level
        ? normalizeRiskLevel(item.risk.overall_risk_level)
        : null,
      totalRulesTriggered: item.risk?.total_rules_triggered ?? triggeredRules.length,
      triggeredRuleIds: triggeredRules,
      totalAlertsDetected: item.risk?.total_alerts_detected ?? 0,
      totalProposedAlerts: item.risk?.total_proposed_alerts ?? 0,
      insufficientEvidenceCount: item.risk?.insufficient_evidence_count ?? 0,
      humanReviewRequired: item.risk?.human_review_required
        ?? item.risk?.human_approval_required
        ?? false,
      totalRulesEvaluated: item.risk?.total_rules_evaluated ?? 0,
      notTriggeredCount: item.risk?.not_triggered_count ?? 0,
      insufficientEvidenceRuleCount: item.risk?.insufficient_evidence_rule_count ?? 0,
      triggeredRules: (item.risk?.triggered_rules ?? []).map((rule) => ({
        ruleId: rule.rule_id || "UNKNOWN_RULE",
        severity: normalizeRiskLevel(rule.severity),
        requiredAction: rule.required_action || "",
        message: rule.message || "",
      })),
      alerts: (item.risk?.alerts ?? []).flatMap((match) => match.alert ? [{
        alertId: match.alert.alert_id || "UNKNOWN_ALERT",
        alertType: match.alert.alert_type || "Risk alert",
        severity: normalizeRiskLevel(match.alert.severity),
        riskScore: match.alert.risk_score ?? null,
        description: match.alert.description || "",
        recommendedAction: match.alert.recommended_action || "",
      }] : []),
      evidenceGaps: item.risk?.evidence_gaps ?? [],
      requiredActions: item.risk?.required_actions ?? [],
    },
    bankPrecheck: {
      available: Boolean(item.decision || finance.funding_need_type),
      requestType: finance.funding_need_type ?? null,
      requestedAmount: decision.capital_need ?? finance.requested_amount ?? null,
      eligibleScore: decision.eligible_score ?? null,
      precheckNote: decision.precheck_note ?? null,
      approvalStatus: decision.approval_status ?? false,
      requiresFounderConfirmation: decision.requires_founder_confirmation ?? false,
    },
  };
}

async function fetchApiContracts(signal?: AbortSignal): Promise<ContractRecord[]> {
  const response = await fetch(`${API_BASE_URL}/contracts?latest_only=true`, {
    cache: "no-store",
    headers: API_REQUEST_HEADERS,
    signal,
  });
  if (!response.ok) throw new Error(`Contract API returned ${response.status}`);
  const payload = (await response.json()) as { contracts?: ApiContract[] };
  return (payload.contracts ?? []).map(mapApiContract);
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatCompactCurrency(value: number): string {
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

const sampleRiskSnapshots: AgentRiskSnapshot[] = [
  {
    available: true,
    contractId: "CON-UPLOAD-002",
    overallRiskLevel: "high",
    totalRulesTriggered: 1,
    triggeredRuleIds: ["RR-002"],
    totalAlertsDetected: 1,
    totalProposedAlerts: 0,
    insufficientEvidenceCount: 4,
    humanReviewRequired: true,
    totalRulesEvaluated: 7,
    notTriggeredCount: 2,
    insufficientEvidenceRuleCount: 4,
    triggeredRules: [
      {
        ruleId: "RR-002",
        severity: "high",
        requiredAction: "Recommend working capital option or phase delivery",
        message: "The Finance Feature Pack satisfies the rule condition.",
      },
    ],
    alerts: [
      {
        alertId: "AL-002",
        alertType: "Cashflow shortage",
        severity: "high",
        riskScore: 76,
        description: "Projected closing cash below reserve minimum",
        recommendedAction: "Evaluate working capital line",
      },
    ],
    evidenceGaps: [
      "RR-001:transaction_risk_score",
      "RR-004:document_sent_to_partner",
      "RR-006:confidence_score",
      "RR-007:delivery_delay_days",
    ],
    requiredActions: ["Recommend working capital option or phase delivery"],
  },
];

const severityOrder: Array<RiskLevel | "none"> = ["critical", "high", "medium", "low", "none"];
const severityLabels: Record<RiskLevel | "none", string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "Không kích hoạt",
};
function EnterpriseRiskChart({
  contracts,
  dataMode,
}: {
  contracts: ContractRecord[];
  dataMode: "api" | "demo";
}) {
  const snapshots = useMemo(
    () => dataMode === "api"
      ? contracts.map((contract) => contract.agentRisk).filter((risk) => risk.available)
      : sampleRiskSnapshots,
    [contracts, dataMode],
  );

  const totalRulesEvaluated = snapshots.reduce((total, risk) => total + risk.totalRulesEvaluated, 0);
  const totalRulesTriggered = snapshots.reduce((total, risk) => total + risk.totalRulesTriggered, 0);
  const insufficientEvidenceRuleCount = snapshots.reduce((total, risk) => total + risk.insufficientEvidenceRuleCount, 0);
  const notTriggeredCount = snapshots.reduce((total, risk) => total + risk.notTriggeredCount, 0);
  const totalAlertsDetected = snapshots.reduce((total, risk) => total + risk.totalAlertsDetected, 0);
  const totalProposedAlerts = snapshots.reduce((total, risk) => total + risk.totalProposedAlerts, 0);
  const evidenceGapCount = snapshots.reduce((total, risk) => total + risk.insufficientEvidenceCount, 0);
  const humanReviewCount = snapshots.filter((risk) => risk.humanReviewRequired).length;
  const triggeredRules = snapshots.flatMap((risk) => risk.triggeredRules.map((rule) => ({
    ...rule,
    contractId: risk.contractId,
  }))).slice(0, 3);
  const activeAlerts = snapshots.flatMap((risk) => risk.alerts.map((alert) => ({
    ...alert,
    contractId: risk.contractId,
  }))).slice(0, 2);
  const highestSeverity = severityOrder.find((level) => snapshots.some((risk) => (risk.overallRiskLevel ?? "none") === level)) ?? "none";
  const evaluationStatuses = [
    { label: "Triggered", value: totalRulesTriggered, color: "bg-red-400" },
    { label: "Thiếu bằng chứng", value: insufficientEvidenceRuleCount, color: "bg-amber-200" },
    { label: "Không kích hoạt", value: notTriggeredCount, color: "bg-emerald-300" },
  ];

  return (
    <section className="h-full overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
      <header className="flex items-start justify-between gap-4 border-b border-[var(--fin-soft-border)] px-5 py-5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-300">Risk Agent output</p>
          <h3 className="mt-2 text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Báo cáo rủi ro hiện tại</h3>
          <p className="mt-1 max-w-sm text-xs leading-5 text-[var(--fin-muted)]">Rule evaluations, alerts và hành động do Risk Agent trả về.</p>
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
        {snapshots.length === 0 ? (
          <div className="flex min-h-72 flex-col items-center justify-center rounded-lg border border-dashed border-[var(--fin-soft-border)] px-5 text-center">
            <AlertTriangle className="size-5 text-[var(--fin-muted)]" strokeWidth={1.6} aria-hidden="true" />
            <p className="mt-4 text-xs font-semibold text-[var(--fin-text)]">Risk Agent chưa trả RiskPack</p>
            <p className="mt-1 max-w-xs text-[11px] leading-5 text-[var(--fin-muted)]">Chart sẽ xuất hiện khi pipeline có ít nhất một hợp đồng hoàn tất bước Risk.</p>
          </div>
        ) : (
          <>
            {humanReviewCount > 0 && (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-red-400/25 bg-red-400/[0.075] px-3.5 py-3 shadow-[inset_3px_0_0_rgba(248,113,113,.8)]">
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="size-3.5 text-red-300" strokeWidth={1.8} aria-hidden="true" />
                  <div>
                    <p className="text-[10px] font-semibold text-red-200">Cần human review</p>
                    <p className="mt-0.5 text-[10px] text-[var(--fin-muted)]">{humanReviewCount}/{snapshots.length} RiskPack yêu cầu người có thẩm quyền xem xét.</p>
                  </div>
                </div>
                <span className="font-mono text-sm font-semibold text-red-200">{humanReviewCount}</span>
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
                    <article key={`${alert.contractId}:${alert.alertId}`} className="rounded-lg border border-red-400/20 bg-red-400/[0.045] p-3.5 shadow-[inset_3px_0_0_rgba(248,113,113,.72)]">
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
                <div key={`${rule.contractId}:${rule.ruleId}`} className="mt-3 grid grid-cols-[auto_1fr] gap-3">
                  <span className="h-fit rounded-md border border-red-400/25 bg-red-400/[0.08] px-2 py-1 font-mono text-[9px] font-semibold text-red-300">{rule.ruleId}</span>
                  <div>
                    <p className="text-[10px] leading-4 text-[var(--fin-muted)]">{rule.message}</p>
                    {rule.requiredAction && <p className="mt-1 text-[10px] font-medium leading-4 text-[var(--fin-text)]">Action: {rule.requiredAction}</p>}
                  </div>
                </div>
              ))}
            </section>

            <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--fin-soft-border)] pt-4 text-[9px] text-[var(--fin-muted)]">
              <span>{evidenceGapCount} evidence fields · {totalProposedAlerts} proposed alerts</span>
              <span>{dataMode === "api" ? "Nguồn: RiskPack" : "Mẫu thật: api.json"}</span>
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
  source: "api" | "sample";
};

const samplePrecheckRow: PrecheckRow = {
  contractId: "CON-UPLOAD-002",
  requestType: "PERFORMANCE_BOND",
  requestedAmount: 300_000_000,
  eligibleScore: null,
  precheckNote: null,
  approvalStatus: false,
  requiresFounderConfirmation: true,
  request: {
    approvalId: "96c15aad-caa8-47b4-8dbf-f230fd969ee8",
    contractId: "CON-UPLOAD-002",
    tool: "precheck_performance_bond",
    arguments: { contract_id: "CON-UPLOAD-002", amount: 300_000_000 },
  },
  source: "sample",
};

const requestTypeLabels: Record<string, string> = {
  PERFORMANCE_BOND: "Bảo lãnh thực hiện",
  TRADE_FINANCE: "Tài trợ thương mại / L/C",
  WORKING_CAPITAL: "Vốn lưu động",
  RECEIVABLE_FINANCING: "Tài trợ khoản phải thu",
};

function BankPrecheckApprovals({
  contracts,
  dataMode,
  onResult,
  onReconnect,
  isReconnecting,
  connectionIssue,
}: {
  contracts: ContractRecord[];
  dataMode: "api" | "demo";
  onResult: (contractId: string, result: {
    eligibleScore: number | null;
    precheckNote: string | null;
    approvalStatus: boolean;
  }) => void;
  onReconnect: () => Promise<void>;
  isReconnecting: boolean;
  connectionIssue: string;
}) {
  const [pendingRequests, setPendingRequests] = useState<Record<string, PendingApprovalRequest>>({});
  const [processing, setProcessing] = useState<{ contractId: string; approved: boolean } | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, "approved" | "rejected">>({});
  const [notice, setNotice] = useState("");
  const [isLoadingRequests, setIsLoadingRequests] = useState(true);

  useEffect(() => {
    if (dataMode !== "api") return;
    const controller = new AbortController();
    const runIds = Array.from(new Set(contracts.flatMap((contract) => contract.runId ? [contract.runId] : [])));

    async function loadPendingRequests() {
      if (runIds.length === 0) return;
      try {
        const responses = await Promise.all(runIds.map(async (runId) => {
          const response = await fetch(`${API_BASE_URL}/runs/${runId}/approvals`, {
            signal: controller.signal,
            cache: "no-store",
            headers: API_REQUEST_HEADERS,
          });
          if (!response.ok) return [];
          const requests = await response.json();
          return (Array.isArray(requests) ? requests : []).map((request: {
            approval_id?: string;
            contract_id?: string;
            tool?: string;
            arguments?: Record<string, unknown>;
          }) => ({
            approvalId: request.approval_id || "",
            contractId: request.contract_id || "",
            runId,
            tool: request.tool || "bank_precheck",
            arguments: request.arguments ?? {},
          })).filter((request: PendingApprovalRequest) => request.approvalId && request.contractId);
        }));

        if (!controller.signal.aborted) {
          const indexed: Record<string, PendingApprovalRequest> = {};
          responses.flat().forEach((request) => { indexed[request.contractId] = request; });
          setPendingRequests(indexed);
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") setNotice("Chưa tải được danh sách approval từ pipeline.");
      } finally {
        if (!controller.signal.aborted) setIsLoadingRequests(false);
      }
    }

    void loadPendingRequests();
    return () => controller.abort();
  }, [contracts, dataMode]);

  const rows = useMemo<PrecheckRow[]>(() => {
    if (dataMode === "demo") return [samplePrecheckRow];
    return contracts
      .filter((contract) => (
        contract.bankPrecheck.requiresFounderConfirmation
        || contract.bankPrecheck.approvalStatus
        || Boolean(pendingRequests[contract.id])
      ))
      .map((contract) => ({
        contractId: contract.id,
        runId: contract.runId,
        requestType: contract.bankPrecheck.requestType || "BANK_PRECHECK",
        requestedAmount: contract.bankPrecheck.requestedAmount,
        eligibleScore: contract.bankPrecheck.eligibleScore,
        precheckNote: contract.bankPrecheck.precheckNote,
        approvalStatus: contract.bankPrecheck.approvalStatus,
        requiresFounderConfirmation: contract.bankPrecheck.requiresFounderConfirmation,
        request: pendingRequests[contract.id],
        source: "api" as const,
      }));
  }, [contracts, dataMode, pendingRequests]);

  const pendingCount = rows.filter((row) => row.request && !row.approvalStatus && !resolutions[row.contractId]).length;
  const completedCount = rows.filter((row) => row.approvalStatus || resolutions[row.contractId] === "approved").length;
  const eligibleCount = rows.filter((row) => row.eligibleScore != null && row.eligibleScore >= 70).length;

  const submitApproval = async (row: PrecheckRow, approved: boolean) => {
    if (row.source !== "api" || !row.runId || !row.request?.approvalId) return;
    setProcessing({ contractId: row.contractId, approved });
    setNotice("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/runs/${row.runId}/approvals/${row.request.approvalId}?approved=${approved}`,
        { method: "POST", headers: API_REQUEST_HEADERS },
      );
      if (!response.ok) throw new Error(`Approval API returned ${response.status}`);
      const payload = await response.json();
      const decision = (payload.decision_result?.decisions ?? []).find(
        (item: { contract_id?: string }) => item.contract_id === row.contractId,
      );
      if (!decision) throw new Error("Updated Decision Card is missing");
      if (approved && (decision.eligible_score == null || !decision.precheck_note)) {
        throw new Error("Bank precheck did not return score and note");
      }

      onResult(row.contractId, {
        eligibleScore: decision.eligible_score ?? null,
        precheckNote: decision.precheck_note ?? null,
        approvalStatus: decision.approval_status ?? false,
      });
      setResolutions((current) => ({ ...current, [row.contractId]: approved ? "approved" : "rejected" }));
      setPendingRequests((current) => {
        const next = { ...current };
        delete next[row.contractId];
        return next;
      });
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
          <h3 className="mt-2 text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Khoản vay cần chấp thuận kiểm tra ngân hàng</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--fin-muted)]">
            Eligibility score và pre-check note chỉ xuất hiện sau khi người dùng cho phép Decision Agent gọi API ngân hàng.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-px overflow-hidden rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-soft-border)]">
          {[
            { label: "Chờ duyệt", value: pendingCount },
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
                const resolution = resolutions[row.contractId];
                const isCompleted = row.approvalStatus || resolution === "approved";
                const isRejected = resolution === "rejected";
                const scoreTone = row.eligibleScore == null
                  ? "bg-white/[0.06]"
                  : row.eligibleScore >= 70 ? "bg-emerald-300" : "bg-red-400";

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
                      {row.requestedAmount != null ? formatCompactCurrency(row.requestedAmount) : "—"}
                    </td>
                    <td className="px-4 py-4">
                      {row.eligibleScore != null ? (
                        <div className="w-32">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className={`font-mono text-lg font-semibold ${row.eligibleScore >= 70 ? "text-emerald-300" : "text-red-300"}`}>{row.eligibleScore}</span>
                            <span className="text-[9px] text-[var(--fin-muted)]">/ 100</span>
                          </div>
                          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                            <div className={`h-full rounded-full ${scoreTone}`} style={{ width: `${row.eligibleScore}%` }} />
                          </div>
                        </div>
                      ) : (
                        <div>
                          <span className="font-mono text-sm text-[var(--fin-muted)]">—</span>
                          <p className="mt-1 text-[9px] text-[var(--fin-muted)]">Có sau approval</p>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <p className={`text-[11px] leading-5 ${row.precheckNote ? "text-[var(--fin-text)]" : "text-[var(--fin-muted)]"}`}>
                        {row.precheckNote || "Chưa gọi API ngân hàng nên chưa có pre-check note."}
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
                      ) : row.source === "sample" ? (
                        <button
                          type="button"
                          onClick={() => void onReconnect()}
                          disabled={isReconnecting}
                          className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-amber-300/25 bg-amber-300/[0.08] px-3 text-[10px] font-semibold text-amber-100 transition hover:bg-amber-300/[0.14] active:translate-y-px disabled:cursor-wait disabled:opacity-55 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-200/70"
                        >
                          <RefreshCw className={`size-3 ${isReconnecting ? "animate-spin motion-reduce:animate-none" : ""}`} aria-hidden="true" />
                          {isReconnecting ? "Đang kết nối…" : "Kết nối API để duyệt"}
                        </button>
                      ) : row.request ? (
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void submitApproval(row, false)}
                            disabled={isProcessing}
                            className="min-h-9 rounded-lg border border-red-400/20 px-3 text-[10px] font-semibold text-red-300 transition hover:bg-red-400/[0.08] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300/60"
                          >
                            Từ chối
                          </button>
                          <button
                            type="button"
                            onClick={() => void submitApproval(row, true)}
                            disabled={isProcessing}
                            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-emerald-300 px-3 text-[10px] font-bold text-[#07110c] transition hover:bg-emerald-200 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200"
                          >
                            {isProcessing ? <RefreshCw className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check className="size-3" aria-hidden="true" />}
                            {isProcessing ? "Đang gọi API…" : "Duyệt & kiểm tra"}
                          </button>
                        </div>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-[var(--fin-muted)]">
                          <Clock3 className="size-3" aria-hidden="true" /> {isLoadingRequests ? "Đang tải…" : "Chưa có request"}
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
        <span>{dataMode === "api" ? "Nguồn: /runs/{id}/approvals" : `Dữ liệu mẫu chỉ xem · API: ${API_BASE_URL}`}</span>
      </footer>
    </section>
  );
}

export function ContractApprovalWorkspace() {
  const [contracts, setContracts] = useState<ContractRecord[]>(demoContracts);
  const [selectedId, setSelectedId] = useState(demoContracts[0].id);
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [query, setQuery] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(true);
  const [dataMode, setDataMode] = useState<"api" | "demo">("demo");
  const [apiConnectionIssue, setApiConnectionIssue] = useState("");
  const [actionState, setActionState] = useState<"idle" | "saving">("idle");
  const [notice, setNotice] = useState("");

  const selectedForDetail = contracts.find((item) => item.id === selectedId);
  const selectedRunId = selectedForDetail?.runId;
  const selectedSource = selectedForDetail?.source;

  const loadContracts = async () => {
    setIsRefreshing(true);
    setApiConnectionIssue("");
    try {
      const apiContracts = await fetchApiContracts();
      setContracts(apiContracts);
      setDataMode("api");
      if (apiContracts.length > 0) {
        setSelectedId((current) => apiContracts.some((item) => item.id === current) ? current : apiContracts[0].id);
      }
    } catch (error) {
      setDataMode("demo");
      setApiConnectionIssue(
        error instanceof Error
          ? `Không kết nối được ${API_BASE_URL}: ${error.message}`
          : `Không kết nối được ${API_BASE_URL}.`,
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();

    async function hydrateContracts() {
      try {
        const apiContracts = await fetchApiContracts(controller.signal);
        setContracts(apiContracts);
        setDataMode("api");
        setApiConnectionIssue("");
        if (apiContracts.length > 0) {
          setSelectedId((current) => apiContracts.some((item) => item.id === current) ? current : apiContracts[0].id);
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          setDataMode("demo");
          setApiConnectionIssue(
            error instanceof Error
              ? `Không kết nối được ${API_BASE_URL}: ${error.message}`
              : `Không kết nối được ${API_BASE_URL}.`,
          );
        }
      } finally {
        if (!controller.signal.aborted) setIsRefreshing(false);
      }
    }

    void hydrateContracts();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedRunId || selectedSource !== "api") return;
    const controller = new AbortController();

    async function loadDecisionDetail() {
      try {
        const [decisionResponse, runResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/runs/${selectedRunId}/decision`, {
            signal: controller.signal,
            cache: "no-store",
            headers: API_REQUEST_HEADERS,
          }),
          fetch(`${API_BASE_URL}/runs/${selectedRunId}`, {
            signal: controller.signal,
            cache: "no-store",
            headers: API_REQUEST_HEADERS,
          }),
        ]);
        if (!decisionResponse.ok || !runResponse.ok) return;
        const decisionPayload = await decisionResponse.json();
        const runPayload = await runResponse.json();
        const decision = (decisionPayload.decisions ?? []).find((item: { contract_id?: string }) => item.contract_id === selectedId);
        const risk = (runPayload.risk_pack?.packs ?? []).find((item: { contract_id?: string }) => item.contract_id === selectedId);

        setContracts((current) => current.map((item) => {
          if (item.id !== selectedId) return item;
          const evaluations = (risk?.rule_evaluations ?? []).filter((entry: { status?: string }) => entry.status !== "NOT_TRIGGERED");
          return {
            ...item,
            aiOption: decision?.recommended_option ?? item.aiOption,
            aiConfidence: decision?.eligible_score ?? item.aiConfidence,
            reasons: decision?.reasons?.length ? decision.reasons : item.reasons,
            safeguards: decision?.protective_condition ? [decision.protective_condition] : item.safeguards,
            bankPrecheck: decision
              ? {
                  ...item.bankPrecheck,
                  available: true,
                  requestedAmount: decision.capital_need ?? item.bankPrecheck.requestedAmount,
                  eligibleScore: decision.eligible_score ?? null,
                  precheckNote: decision.precheck_note ?? null,
                  approvalStatus: decision.approval_status ?? false,
                  requiresFounderConfirmation: decision.requires_founder_confirmation ?? false,
                }
              : item.bankPrecheck,
            riskLevel: risk?.overall_risk_level ? normalizeRiskLevel(risk.overall_risk_level) : item.riskLevel,
            agentRisk: risk
              ? {
                  available: true,
                  contractId: item.id,
                  overallRiskLevel: risk.overall_risk_level ? normalizeRiskLevel(risk.overall_risk_level) : null,
                  totalRulesTriggered: risk.summary?.total_rules_triggered ?? risk.triggered_rule_ids?.length ?? 0,
                  triggeredRuleIds: risk.triggered_rule_ids ?? [],
                  totalAlertsDetected: risk.summary?.total_alerts_detected ?? risk.alerts?.length ?? 0,
                  totalProposedAlerts: risk.summary?.total_proposed_alerts ?? risk.proposed_alerts?.length ?? 0,
                  insufficientEvidenceCount: risk.insufficient_evidence?.length ?? 0,
                  humanReviewRequired: risk.summary?.human_review_required ?? risk.human_approval_required ?? false,
                  totalRulesEvaluated: risk.rule_evaluations?.length ?? 0,
                  notTriggeredCount: risk.rule_evaluations?.filter((entry: { status?: string }) => entry.status === "NOT_TRIGGERED").length ?? 0,
                  insufficientEvidenceRuleCount: risk.rule_evaluations?.filter((entry: { status?: string }) => entry.status === "INSUFFICIENT_EVIDENCE").length ?? 0,
                  triggeredRules: (risk.rule_evaluations ?? [])
                    .filter((entry: { status?: string }) => entry.status === "TRIGGERED")
                    .map((entry: {
                      rule_id?: string;
                      severity?: string;
                      required_action?: string;
                      message?: string;
                    }) => ({
                      ruleId: entry.rule_id || "UNKNOWN_RULE",
                      severity: normalizeRiskLevel(entry.severity),
                      requiredAction: entry.required_action || "",
                      message: entry.message || "",
                    })),
                  alerts: (risk.alerts ?? []).flatMap((match: {
                    alert?: {
                      alert_id?: string;
                      alert_type?: string;
                      severity?: string;
                      risk_score?: number | null;
                      description?: string;
                      recommended_action?: string;
                    };
                  }) => match.alert ? [{
                    alertId: match.alert.alert_id || "UNKNOWN_ALERT",
                    alertType: match.alert.alert_type || "Risk alert",
                    severity: normalizeRiskLevel(match.alert.severity),
                    riskScore: match.alert.risk_score ?? null,
                    description: match.alert.description || "",
                    recommendedAction: match.alert.recommended_action || "",
                  }] : []),
                  evidenceGaps: risk.insufficient_evidence ?? [],
                  requiredActions: risk.required_actions ?? [],
                }
              : item.agentRisk,
            risks: evaluations.length
              ? evaluations.slice(0, 4).map((entry: {
                  rule_id?: string;
                  risk_type?: string;
                  severity?: string;
                  message?: string;
                  observed_value?: string;
                  required_action?: string;
                  missing_fields?: string[];
                }) => ({
                  title: entry.risk_type || entry.rule_id || "Cảnh báo rủi ro",
                  description: [
                    entry.message || `Giá trị quan sát: ${entry.observed_value || "cần xác minh thêm"}.`,
                    entry.missing_fields?.length ? `Thiếu: ${entry.missing_fields.join(", ")}.` : "",
                    entry.required_action ? `Hành động: ${entry.required_action}.` : "",
                  ].filter(Boolean).join(" "),
                  severity: normalizeRiskLevel(entry.severity),
                }))
              : item.risks,
          };
        }));
      } catch (error) {
        if ((error as Error).name !== "AbortError") setNotice("Chưa tải được chi tiết AI mới nhất; đang hiển thị bản tóm tắt.");
      }
    }

    void loadDecisionDetail();
    return () => controller.abort();
  }, [selectedId, selectedRunId, selectedSource]);

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
    value: contracts.reduce((sum, item) => sum + item.amount, 0),
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

  const applyDecision = (status: ApprovalStatus) => {
    if (!selected) return;
    setActionState("saving");
    setNotice("");
    setContracts((current) => current.map((item) => item.id === selected.id ? { ...item, status } : item));
    const actionLabel = status === "approved" ? "duyệt" : status === "rejected" ? "từ chối" : "chuyển sang xem xét";
    setNotice(`Đã ${actionLabel} ${selected.id} trong hàng chờ hợp đồng. Quyền gọi API ngân hàng được quản lý riêng ở bảng Bank pre-check bên dưới.`);
    setActionState("idle");
  };

  if (!selected) return null;

  return (
    <div className="mx-auto w-full max-w-[1600px]">
      <section className="mb-5 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-2 rounded-md border border-emerald-400/15 bg-emerald-400/[0.06] px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
              <span className="size-1.5 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,.7)]" />
              Approval workspace
            </span>
            <span className="text-xs text-[var(--fin-muted)]">
              {dataMode === "api" ? "Dữ liệu trực tiếp từ pipeline" : "Dữ liệu minh hoạ · API chưa kết nối"}
            </span>
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
          onClick={() => void loadContracts()}
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

      <div className="mt-5 grid min-w-0 gap-5 xl:grid-cols-[minmax(0,1fr)_23rem]">
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
                          Tin cậy {item.aiConfidence}%
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
                <span className="font-mono text-[10px] text-emerald-300">{selected.aiConfidence}% confidence</span>
              </div>
              <p className="mt-2 text-sm font-semibold tracking-[-0.02em] text-[var(--fin-text)]">{optionLabels[selected.aiOption] ?? selected.aiOption}</p>
              <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full rounded-full bg-emerald-300 transition-[width] duration-500" style={{ width: `${selected.aiConfidence}%` }} />
              </div>
            </section>

            <section className="mt-6">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--fin-muted)]">Vì sao AI đưa ra phương án này</p>
              <ol className="mt-3 space-y-3">
                {selected.reasons.map((reason, index) => (
                  <li key={`${selected.id}-reason-${index}`} className="flex gap-3 text-xs leading-5 text-[var(--fin-muted)]">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-white/[0.05] font-mono text-[9px] font-semibold text-[var(--fin-text)]">{String(index + 1).padStart(2, "0")}</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="mt-6 border-t border-[var(--fin-soft-border)] pt-5">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--fin-muted)]">Rule evaluations cần chú ý</p>
                <span className="font-mono text-[10px] text-[var(--fin-muted)]">{selected.agentRisk.available ? `${selected.risks.length} items` : "NO RISK PACK"}</span>
              </div>
              {selected.agentRisk.available ? (
                <div className="mt-3 space-y-2">
                  {selected.risks.map((risk, index) => (
                    <article key={`${selected.id}-risk-${index}`} className="rounded-lg bg-white/[0.028] p-3.5 ring-1 ring-inset ring-white/[0.055]">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="text-xs font-semibold text-[var(--fin-text)]">{risk.title}</h3>
                        <RiskBadge level={risk.severity} />
                      </div>
                      <p className="mt-2 text-[11px] leading-5 text-[var(--fin-muted)]">{risk.description}</p>
                    </article>
                  ))}
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
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.035em] text-[var(--fin-text)]">Tài chính & rủi ro doanh nghiệp</h2>
            <p className="mt-1.5 max-w-xl text-xs leading-5 text-[var(--fin-muted)]">Bối cảnh vận hành hỗ trợ người phê duyệt trước khi ra quyết định với từng hợp đồng.</p>
          </div>
          <p className="font-mono text-[10px] text-[var(--fin-muted)]">CẬP NHẬT TỪ DANH MỤC HIỆN TẠI</p>
        </header>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(20rem,.75fr)]">
          <section className="overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
            <header className="flex flex-col justify-between gap-4 border-b border-[var(--fin-soft-border)] px-5 py-5 sm:flex-row sm:items-start">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-300">7-month view</p>
                <h3 className="mt-2 text-base font-semibold tracking-[-0.025em] text-[var(--fin-text)]">Dòng tiền doanh nghiệp</h3>
                <p className="mt-1 text-xs leading-5 text-[var(--fin-muted)]">Tiền vào, tiền ra và dòng tiền thuần theo tháng.</p>
              </div>
              <div className="grid grid-cols-2 gap-5 text-left sm:text-right">
                <div>
                  <p className="text-[10px] text-[var(--fin-muted)]">Dòng tiền thuần T7</p>
                  <p className="mt-1 font-mono text-sm font-semibold text-emerald-300">+510 triệu ₫</p>
                </div>
                <div>
                  <p className="text-[10px] text-[var(--fin-muted)]">So với T6</p>
                  <p className="mt-1 font-mono text-sm font-semibold text-[var(--fin-text)]">+64,5%</p>
                </div>
              </div>
            </header>
            <div className="px-3 pb-4 pt-5 sm:px-5"><CashFlowChart /></div>
          </section>

          <EnterpriseRiskChart contracts={contracts} dataMode={dataMode} />
        </div>

        <BankPrecheckApprovals
          contracts={contracts}
          dataMode={dataMode}
          onResult={updateBankPrecheckResult}
          onReconnect={loadContracts}
          isReconnecting={isRefreshing}
          connectionIssue={apiConnectionIssue}
        />
      </section>
    </div>
  );
}
