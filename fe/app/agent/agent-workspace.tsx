"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Bar from "@/components/ui/about/Bar";
import { API_REQUEST_HEADERS, apiUrl } from "@/lib/api";
import { ACTIVE_RUN_STORAGE_KEY } from "@/lib/run-session";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  CirclePause,
  Clock3,
  ListChecks,
  LoaderCircle,
  Play,
  Scale,
  ShieldCheck,
} from "lucide-react";

type AgentId = "Finance" | "Risk" | "Decision" | "Validator";
type AgentStatus = "Idle" | "Working" | "Waiting" | "Done" | "Review" | "Error";
type ConnectionStatus = "idle" | "starting" | "connected" | "reconnecting" | "review" | "completed" | "error";
type LogFilter = "All" | AgentId;
type LogStatus = "Started" | "Working" | "Completed" | "Review" | "Error" | "Cancelled" | "Handoff" | "Update";

type PipelineEvent = {
  run_id?: string;
  seq?: number;
  ts?: string;
  type: string;
  agent?: string;
  target_agent?: string;
  tool_name?: string;
  task?: string;
  status?: string;
  summary?: string;
};

type AgentRuntimeState = {
  status: AgentStatus;
  task: string;
};

type ActivityItem = {
  id: string;
  agentId: AgentId | null;
  title: string;
  description: string;
  status: LogStatus;
  startedAt?: string;
  finishedAt?: string;
  startSeq?: number;
  endSeq?: number;
  type: string;
  events: PipelineEvent[];
};

const AGENT_IDS: AgentId[] = ["Finance", "Risk", "Decision", "Validator"];

const agents = {
  Finance: {
    name: "Finance Agent",
    role: "Chuẩn hóa và phân tích dữ liệu tài chính",
    accent: "#34d399",
    icon: BarChart3,
    summary: "Đối soát dữ liệu, phân tích thanh khoản, biên lợi nhuận và nhu cầu vốn trước khi chuyển sang đánh giá rủi ro.",
  },
  Risk: {
    name: "Risk Agent",
    role: "Đánh giá rủi ro và tuân thủ",
    accent: "#fbbf24",
    icon: ShieldCheck,
    summary: "Áp dụng các chính sách kiểm soát, xác định mức độ rủi ro và tạo Risk Pack cho từng hợp đồng.",
  },
  Decision: {
    name: "Decision Agent",
    role: "Đề xuất quyết định và điều kiện",
    accent: "#38bdf8",
    icon: Scale,
    summary: "Kết hợp kết quả Finance và Risk để tạo Decision Card, điều kiện bảo vệ và yêu cầu phê duyệt khi cần.",
  },
  Validator: {
    name: "Validator Agent",
    role: "Kiểm soát chất lượng và chốt cổng QC",
    accent: "#fb7185",
    icon: ListChecks,
    summary: "Đối chiếu quy trình, nguồn dữ liệu, output schema và ranh giới thẩm quyền sau mỗi agent trước khi cho phép pipeline đi tiếp.",
  },
} as const;

const TOOL_LABELS: Record<string, string> = {
  load_and_validate: "Kiểm tra và chuẩn hóa dữ liệu đầu vào",
  reconcile_bank: "Đối soát hóa đơn với giao dịch ngân hàng",
  liquidity_funding: "Phân tích thanh khoản và nhu cầu vốn",
  classify_invoice: "Phân loại trạng thái hóa đơn",
  margin_analysis: "Phân tích biên lợi nhuận",
  missing_data: "Xác định dữ liệu tài chính còn thiếu",
  list_bank_products: "Đọc danh mục dịch vụ ngân hàng",
  precheck_performance_bond: "Kiểm tra điều kiện bảo lãnh thực hiện",
  precheck_trade_finance: "Kiểm tra điều kiện tài trợ thương mại",
  load_validation_evidence: "Thu thập bằng chứng kiểm soát chất lượng",
};

const TASK_LABELS: Record<string, string> = {
  "Finance → Risk → Decision pipeline started": "Khởi tạo quy trình Finance, Risk và Decision",
  "Gated pipeline: Finance → Validate → Risk → Validate → Decision": "Khởi tạo quy trình bốn agent có cổng kiểm soát",
  "Persist Finance Batch Pack": "Lưu kết quả phân tích tài chính",
  "Build and persist Risk Batch Pack": "Xây dựng và lưu Risk Pack",
  "Risk Pack persisted": "Lưu Risk Pack",
  "Load Finance and Risk Batch Packs": "Nạp kết quả từ Finance và Risk",
  "Load Finance, Risk, and Credit Profiles": "Nạp Finance, Risk và Credit Profile",
  "Pipeline complete; precheck approval is pending": "Hoàn tất phân tích, đang chờ phê duyệt",
};

function createInitialAgentStates(): Record<AgentId, AgentRuntimeState> {
  return {
    Finance: { status: "Idle", task: "Chưa bắt đầu" },
    Risk: { status: "Idle", task: "Đang chờ kết quả từ Finance Agent" },
    Decision: { status: "Idle", task: "Đang chờ kết quả từ Risk Agent" },
    Validator: { status: "Idle", task: "Đang chờ kết quả từ các agent nghiệp vụ" },
  };
}

function resolveAgentId(name?: string): AgentId | null {
  if (!name) return null;
  const normalized = name.toLowerCase().replaceAll("_", " ");
  if (normalized.includes("finance")) return "Finance";
  if (normalized.includes("risk")) return "Risk";
  if (normalized.includes("decision")) return "Decision";
  if (normalized.includes("validator") || normalized.includes("validate")) return "Validator";
  return null;
}

function formatAgentName(name?: string): string {
  const agentId = resolveAgentId(name);
  if (agentId) return agents[agentId].name;
  return name?.replaceAll("_", " ") || "Pipeline";
}

function humanizeTask(task?: string, toolName?: string): string {
  if (toolName && TOOL_LABELS[toolName]) return TOOL_LABELS[toolName];
  if (!task) return "Cập nhật trạng thái";
  if (TASK_LABELS[task]) return TASK_LABELS[task];

  const toolMatch = task.match(/^(?:Run tool|Tool)\s+([a-z0-9_]+)(?:\s+completed)?$/i);
  if (toolMatch) return TOOL_LABELS[toolMatch[1]] || toolMatch[1].replaceAll("_", " ");

  if (task.startsWith("Handoff from ")) {
    const [, source = "agent trước", target = "agent tiếp theo"] = task.match(/^Handoff from (.+) to (.+)$/) || [];
    return `Chuyển giao từ ${formatAgentName(source)} sang ${formatAgentName(target)}`;
  }

  if (task.endsWith(" started")) return `${formatAgentName(task.slice(0, -8))} bắt đầu xử lý`;
  if (task.endsWith(" completed")) return `${formatAgentName(task.slice(0, -10))} hoàn tất xử lý`;
  return task.replaceAll("_", " ");
}

function summarizeTechnicalOutput(summary?: string): string {
  if (!summary) return "Hoàn tất và lưu kết quả thành công.";

  const caseCount = summary.match(/["']case_count["']:\s*(\d+)/)?.[1];
  const missingCount = summary.match(/["']count["']:\s*(\d+)/)?.[1];
  const riskLevels = Array.from(summary.matchAll(/overall_risk_level["']?:\s*["']([A-Z]+)["']/g)).map((match) => match[1]);
  const details: string[] = [];

  if (caseCount) details.push(`Đã xử lý ${caseCount} hợp đồng`);
  if (riskLevels.length > 0) details.push(`Mức rủi ro cao nhất: ${riskLevels.includes("HIGH") ? "HIGH" : riskLevels[0]}`);
  if (missingCount) details.push(`Phát hiện ${missingCount} mục dữ liệu cần bổ sung`);

  return details.length > 0 ? `${details.join(". ")}.` : "Hoàn tất và lưu kết quả thành công.";
}

function describeEvent(event: PipelineEvent): string {
  const agentId = resolveAgentId(event.agent);
  const targetAgent = resolveAgentId(event.target_agent);

  if (event.type === "agent_handoff") {
    return targetAgent
      ? `Kết quả đã sẵn sàng và được chuyển sang ${agents[targetAgent].name}.`
      : "Kết quả đã được chuyển sang bước tiếp theo.";
  }
  if (event.type === "agent_started" && agentId) return agents[agentId].summary;
  if (event.type === "validation_started") return agents.Validator.summary;
  if (event.type === "validation_finished") return event.summary || "Cổng kiểm soát đã PASS, pipeline được phép tiếp tục.";
  if (event.type === "validation_challenge") return event.summary || "Validator phát hiện vấn đề cần xem xét trước khi pipeline tiếp tục.";
  if (event.type === "tool_started") return "Đang thực hiện tác vụ này. Kết quả sẽ được cập nhật trên cùng một dòng khi hoàn tất.";
  if (event.type === "tool_finished") return summarizeTechnicalOutput(event.summary);
  if (event.type === "approval_requested" || event.type === "run_review") {
    return "Pipeline đã hoàn tất phần phân tích tự động và cần người có thẩm quyền xem xét.";
  }
  if (event.type === "run_error") return "Pipeline dừng do lỗi. Mở chi tiết kỹ thuật để kiểm tra nguyên nhân.";
  if (event.type === "run_cancelled") return "Pipeline đã bị hủy trước khi hoàn tất.";
  if (event.type === "run_finished" || event.type === "risk_finished" || event.type === "agent_finished") {
    return agentId ? `${agents[agentId].name} đã hoàn tất phần việc được giao.` : "Pipeline đã hoàn tất.";
  }
  if (event.status === "done") return summarizeTechnicalOutput(event.summary);
  return agentId ? agents[agentId].summary : "Pipeline vừa cập nhật trạng thái.";
}

function logStatusForEvent(event: PipelineEvent): LogStatus {
  if (event.type === "run_started" || event.type === "agent_started") return "Started";
  if (event.type === "agent_handoff") return "Handoff";
  if (event.type === "approval_requested" || event.type === "run_review" || event.status === "review") return "Review";
  if (event.type === "run_error" || event.status === "error") return "Error";
  if (event.type === "run_cancelled" || event.status === "cancelled") return "Cancelled";
  if (event.type === "tool_finished" || event.type === "agent_finished" || event.type === "risk_finished" || event.type === "run_finished" || event.status === "done") return "Completed";
  if (event.type === "tool_started" || event.status === "running") return "Working";
  return "Update";
}

function toolEventKey(event: PipelineEvent, agentId: AgentId | null): string {
  const tool = event.tool_name || humanizeTask(event.task, event.tool_name).toLowerCase();
  return `${event.run_id || "run"}:${agentId || "pipeline"}:${tool}`;
}

function buildActivityItems(events: PipelineEvent[]): ActivityItem[] {
  const ordered = [...events].reverse();
  const items: ActivityItem[] = [];
  const openTools = new Map<string, ActivityItem>();

  for (const event of ordered) {
    const agentId = resolveAgentId(event.agent);
    const eventId = `${event.run_id || "run"}-${event.seq || items.length}`;

    if (event.type === "tool_started") {
      const item: ActivityItem = {
        id: eventId,
        agentId,
        title: humanizeTask(event.task, event.tool_name),
        description: describeEvent(event),
        status: "Working",
        startedAt: event.ts,
        startSeq: event.seq,
        type: event.type,
        events: [event],
      };
      items.push(item);
      openTools.set(toolEventKey(event, agentId), item);
      continue;
    }

    if (event.type === "tool_finished") {
      const key = toolEventKey(event, agentId);
      const openItem = openTools.get(key);
      if (openItem) {
        openItem.status = "Completed";
        openItem.description = describeEvent(event);
        openItem.finishedAt = event.ts;
        openItem.endSeq = event.seq;
        openItem.events.push(event);
        openTools.delete(key);
        continue;
      }
    }

    const closesAgentWork = event.type === "agent_handoff"
      || event.type === "agent_finished"
      || event.type === "validation_finished"
      || event.type === "validation_challenge"
      || event.type === "risk_finished"
      || event.type === "run_finished";

    if (agentId && closesAgentWork) {
      for (const [key, openItem] of openTools) {
        if (openItem.agentId !== agentId) continue;
        openItem.status = "Completed";
        openItem.description = `Tác vụ kết thúc khi ${agents[agentId].name} hoàn tất bước xử lý.`;
        openItem.finishedAt = event.ts;
        openItem.endSeq = event.seq;
        openTools.delete(key);
      }
    }

    if (event.type === "run_error" || event.type === "run_cancelled") {
      for (const [key, openItem] of openTools) {
        openItem.status = event.type === "run_error" ? "Error" : "Cancelled";
        openItem.description = event.type === "run_error"
          ? "Tác vụ dừng do pipeline gặp lỗi."
          : "Tác vụ dừng vì pipeline đã bị hủy.";
        openItem.finishedAt = event.ts;
        openItem.endSeq = event.seq;
        openTools.delete(key);
      }
    }

    items.push({
      id: eventId,
      agentId,
      title: humanizeTask(event.task, event.tool_name),
      description: describeEvent(event),
      status: logStatusForEvent(event),
      startedAt: event.ts,
      finishedAt: event.status === "done" ? event.ts : undefined,
      startSeq: event.seq,
      endSeq: event.seq,
      type: event.type,
      events: [event],
    });
  }

  return items.reverse();
}

function formatEventTime(timestamp?: string): string {
  if (!timestamp) return "Bây giờ";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Bây giờ";
  return new Intl.DateTimeFormat("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function agentStatusLabel(status: AgentStatus): string {
  const labels: Record<AgentStatus, string> = {
    Idle: "Chưa chạy",
    Working: "Đang chạy",
    Waiting: "Đang chờ",
    Done: "Hoàn tất",
    Review: "Chờ duyệt",
    Error: "Có lỗi",
  };
  return labels[status];
}

function logStatusLabel(status: LogStatus): string {
  const labels: Record<LogStatus, string> = {
    Started: "Bắt đầu",
    Working: "Đang chạy",
    Completed: "Hoàn tất",
    Review: "Chờ duyệt",
    Error: "Lỗi",
    Cancelled: "Đã hủy",
    Handoff: "Chuyển giao",
    Update: "Cập nhật",
  };
  return labels[status];
}

function connectionLabel(status: ConnectionStatus): string {
  const labels: Record<ConnectionStatus, string> = {
    idle: "Chưa kết nối",
    starting: "Đang khởi tạo",
    connected: "Đang nhận sự kiện",
    reconnecting: "Đang kết nối lại",
    review: "Đang chờ phê duyệt",
    completed: "Đã hoàn tất",
    error: "Kết nối lỗi",
  };
  return labels[status];
}

function StatusIcon({ status }: { status: LogStatus }) {
  if (status === "Started") return <Play className="size-4" strokeWidth={1.8} />;
  if (status === "Working") return <LoaderCircle className="size-4 animate-spin" strokeWidth={1.8} />;
  if (status === "Completed") return <CheckCircle2 className="size-4" strokeWidth={1.8} />;
  if (status === "Handoff") return <ArrowRight className="size-4" strokeWidth={1.8} />;
  if (status === "Review") return <CirclePause className="size-4" strokeWidth={1.8} />;
  if (status === "Error" || status === "Cancelled") return <CircleAlert className="size-4" strokeWidth={1.8} />;
  return <Activity className="size-4" strokeWidth={1.8} />;
}

function logStatusClasses(status: LogStatus): string {
  if (status === "Started") return "border-zinc-400/30 bg-zinc-400/[0.08] text-zinc-300";
  if (status === "Working") return "border-sky-400/40 bg-sky-400/10 text-sky-300";
  if (status === "Review" || status === "Handoff") return "border-amber-400/40 bg-amber-400/10 text-amber-200";
  if (status === "Error" || status === "Cancelled") return "border-rose-400/40 bg-rose-400/10 text-rose-300";
  if (status === "Completed") return "border-emerald-400/40 bg-emerald-400/10 text-emerald-300";
  return "border-white/15 bg-white/5 text-zinc-300";
}

function AgentStage({
  id,
  index,
  selected,
  active,
  state,
  eventCount,
  onSelect,
}: {
  id: AgentId;
  index: number;
  selected: boolean;
  active: boolean;
  state: AgentRuntimeState;
  eventCount: number;
  onSelect: () => void;
}) {
  const agent = agents[id];
  const Icon = agent.icon;

  return (
    <li className="relative min-w-0">
      {index < AGENT_IDS.length - 1 && (
        <span className="absolute left-[calc(50%+2.5rem)] right-[calc(-50%+2.5rem)] top-9 hidden h-px bg-white/10 lg:block" aria-hidden="true" />
      )}
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={`relative z-10 flex h-full min-h-40 w-full flex-col rounded-xl border p-4 text-left transition duration-200 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${
          active
            ? "border-emerald-400/55 bg-emerald-400/[0.08] shadow-[0_0_32px_rgba(52,211,153,.15),inset_0_1px_0_rgba(255,255,255,.08)]"
            : selected
              ? "border-white/20 bg-white/[0.045]"
              : "border-white/10 bg-white/[0.025] hover:border-white/20 hover:bg-white/[0.04]"
        }`}
      >
        <div className="flex items-start justify-between gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg border border-white/10 bg-zinc-950" style={{ color: agent.accent }}>
            <Icon className="size-5" strokeWidth={1.8} />
          </span>
          <span className="font-mono text-[10px] tabular-nums text-zinc-600">0{index + 1}</span>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
          {active && <span className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.9)]" aria-label="Đang hoạt động" />}
        </div>
        <p className="mt-1 text-xs leading-5 text-zinc-500">{agent.role}</p>

        <div className="mt-auto flex items-end justify-between gap-3 pt-4">
          <span className="text-xs font-medium" style={{ color: state.status === "Idle" ? "#71717a" : agent.accent }}>
            {agentStatusLabel(state.status)}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-zinc-600">{eventCount} sự kiện</span>
        </div>
      </button>
    </li>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const agentName = item.agentId ? agents[item.agentId].name : "Pipeline";
  const time = formatEventTime(item.finishedAt || item.startedAt);

  return (
    <article className={`group rounded-xl border p-4 transition-colors ${item.status === "Working" ? "border-sky-400/25 bg-sky-400/[0.035]" : "border-white/[0.08] bg-zinc-950/55 hover:border-white/15"}`}>
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border ${logStatusClasses(item.status)}`}>
          <StatusIcon status={item.status} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-xs font-medium text-zinc-500">{agentName}</span>
                <span className="font-mono text-[10px] tabular-nums text-zinc-700">#{item.startSeq ?? "-"}{item.endSeq && item.endSeq !== item.startSeq ? `-${item.endSeq}` : ""}</span>
              </div>
              <h3 className="mt-1 text-sm font-semibold leading-5 text-zinc-100 sm:text-[15px]">{item.title}</h3>
            </div>
            <span className={`shrink-0 rounded-md border px-2 py-1 text-[10px] font-medium ${logStatusClasses(item.status)}`}>
              {logStatusLabel(item.status)}
            </span>
          </div>

          <p className="mt-2 max-w-[75ch] text-xs leading-5 text-zinc-400 sm:text-sm">{item.description}</p>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="flex items-center gap-1.5 font-mono text-[10px] tabular-nums text-zinc-600">
              <Clock3 className="size-3" strokeWidth={1.8} />
              {time}
            </span>
            <details className="group/details">
              <summary className="flex cursor-pointer list-none items-center gap-1 text-[11px] font-medium text-zinc-500 transition hover:text-zinc-300">
                Chi tiết kỹ thuật
                <ChevronDown className="size-3 transition-transform group-open/details:rotate-180" strokeWidth={1.8} />
              </summary>
              <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-white/[0.08] bg-black/50 p-3 font-mono text-[10px] leading-5 text-zinc-500">
                {JSON.stringify(item.events, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      </div>
    </article>
  );
}

export function AgentWorkspace() {
  const router = useRouter();
  const [selected, setSelected] = useState<AgentId>("Finance");
  const [logFilter, setLogFilter] = useState<LogFilter>("All");
  const [activeAgent, setActiveAgent] = useState<AgentId | null>(null);
  const [agentStates, setAgentStates] = useState<Record<AgentId, AgentRuntimeState>>(createInitialAgentStates);
  const [activity, setActivity] = useState<PipelineEvent[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const eventStreamRef = useRef<AbortController | null>(null);
  const startRequestRef = useRef<AbortController | null>(null);
  const dashboardRedirectedRef = useRef(false);

  useEffect(() => {
    const storedRunId = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!storedRunId || !/^\d+$/.test(storedRunId)) return;
    const restoreTimer = window.setTimeout(() => setSessionId(Number(storedRunId)), 0);
    return () => window.clearTimeout(restoreTimer);
  }, []);

  const activityItems = useMemo(() => buildActivityItems(activity), [activity]);
  const filteredItems = useMemo(
    () => activityItems.filter((item) => logFilter === "All" || item.agentId === logFilter),
    [activityItems, logFilter],
  );
  const completedTaskCount = activityItems.filter((item) => item.status === "Completed").length;
  const completedAgentCount = AGENT_IDS.filter((id) => agentStates[id].status === "Done").length;

  const agentEventCounts = useMemo(() => {
    return AGENT_IDS.reduce<Record<AgentId, number>>((counts, id) => {
      counts[id] = activity.filter((event) => resolveAgentId(event.agent) === id).length;
      return counts;
    }, { Finance: 0, Risk: 0, Decision: 0, Validator: 0 });
  }, [activity]);

  const handlePipelineEvent = useCallback((event: PipelineEvent) => {
    if (event.type === "heartbeat") return;

    const eventAgent = resolveAgentId(event.agent);
    const targetAgent = resolveAgentId(event.target_agent);
    const task = humanizeTask(event.task, event.tool_name);

    setActivity((current) => {
      const duplicate = event.seq !== undefined
        && current.some((item) => item.run_id === event.run_id && item.seq === event.seq);
      return duplicate ? current : [event, ...current].slice(0, 80);
    });

    setAgentStates((current) => {
      const next = { ...current };

      if (event.type === "agent_handoff") {
        if (eventAgent) next[eventAgent] = { status: "Done", task };
        if (targetAgent) next[targetAgent] = { status: "Working", task: `Đang nhận kết quả từ ${eventAgent ? agents[eventAgent].name : "agent trước"}` };
        return next;
      }

      if (eventAgent) {
        let status = current[eventAgent].status;
        if (event.status === "running" || event.type === "agent_started") status = "Working";
        if (event.status === "review" || event.type === "approval_requested" || event.type === "run_review") status = "Review";
        if (event.type === "agent_finished" || event.type === "validation_finished" || event.type === "risk_finished" || event.type === "run_finished") status = "Done";
        if (event.status === "error" || event.type === "run_error") status = "Error";
        if (event.status === "awaiting_input") status = "Waiting";
        next[eventAgent] = { status, task };
      } else if (event.type === "run_error") {
        for (const id of AGENT_IDS) {
          if (next[id].status === "Working") next[id] = { status: "Error", task };
        }
      }

      return next;
    });

    if (event.type === "agent_handoff" && targetAgent) {
      setActiveAgent(targetAgent);
      setSelected(targetAgent);
    } else if (eventAgent) {
      setSelected(eventAgent);
      if (event.type === "agent_finished" || event.type === "validation_finished" || event.type === "validation_challenge" || event.type === "risk_finished" || event.type === "run_review" || event.type === "approval_requested") {
        setActiveAgent(null);
      } else {
        setActiveAgent(eventAgent);
      }
    }

    if (event.type === "run_review") {
      setConnectionStatus("review");
      setActiveAgent(null);
    }

    if (event.type === "run_finished") {
      setConnectionStatus("completed");
      setActiveAgent(null);
      eventStreamRef.current?.abort();
      eventStreamRef.current = null;
    }

    if ((event.type === "run_review" || event.type === "run_finished") && !dashboardRedirectedRef.current) {
      dashboardRedirectedRef.current = true;
      eventStreamRef.current?.abort();
      eventStreamRef.current = null;
      window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
      router.replace("/dashboard");
    }

    if (event.type === "run_error" || event.type === "run_cancelled") {
      setConnectionStatus("error");
      setErrorMessage(event.task || "Pipeline dừng trước khi hoàn tất.");
      setActiveAgent(null);
      eventStreamRef.current?.abort();
      eventStreamRef.current = null;
    }
  }, [router]);

  const startPipeline = useCallback(async () => {
    startRequestRef.current?.abort();
    const controller = new AbortController();
    startRequestRef.current = controller;

    eventStreamRef.current?.abort();
    eventStreamRef.current = null;

    setConnectionStatus("starting");
    setErrorMessage("");
    setActivity([]);
    setAgentStates(createInitialAgentStates());
    setActiveAgent(null);
    setSelected("Finance");
    setLogFilter("All");
    setSessionId(null);
    dashboardRedirectedRef.current = false;
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);

    try {
      const response = await fetch(apiUrl("/runs/validated"), {
        method: "POST",
        headers: {
          Accept: "application/json",
          ...API_REQUEST_HEADERS,
        },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`API returned ${response.status} ${response.statusText}`);

      const payload = await response.json() as { session_id?: number };
      if (typeof payload.session_id !== "number") throw new Error("API response did not include a valid session_id.");
      if (controller.signal.aborted) return;
      window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, String(payload.session_id));
      setSessionId(payload.session_id);
    } catch (error) {
      if (controller.signal.aborted) return;
      setConnectionStatus("error");
      setErrorMessage(error instanceof Error ? error.message : "Không thể khởi động pipeline.");
    } finally {
      if (startRequestRef.current === controller) startRequestRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (sessionId === null) return;

    const controller = new AbortController();
    eventStreamRef.current = controller;

    async function waitBeforeReconnect() {
      await new Promise<void>((resolve) => {
        const onAbort = () => {
          window.clearTimeout(timeout);
          resolve();
        };
        const timeout = window.setTimeout(() => {
          controller.signal.removeEventListener("abort", onAbort);
          resolve();
        }, 1_500);
        controller.signal.addEventListener("abort", onAbort, { once: true });
      });
    }

    async function connectToEventStream() {
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(apiUrl(`/runs/${sessionId}/events`), {
            cache: "no-store",
            headers: {
              Accept: "text/event-stream",
              "Cache-Control": "no-cache",
              ...API_REQUEST_HEADERS,
            },
            signal: controller.signal,
          });
          if (!response.ok || !response.body) {
            throw new Error(`Event API returned ${response.status} ${response.statusText}`);
          }

          setConnectionStatus("connected");
          setErrorMessage("");

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

              try {
                handlePipelineEvent(JSON.parse(data) as PipelineEvent);
              } catch {
                setErrorMessage("API trả về event không đúng định dạng.");
              }
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          setErrorMessage(
            error instanceof Error
              ? `Kết nối event bị gián đoạn: ${error.message}`
              : "Kết nối event bị gián đoạn. Hệ thống đang kết nối lại.",
          );
        }

        if (!controller.signal.aborted) {
          setConnectionStatus("reconnecting");
          await waitBeforeReconnect();
        }
      }
    }

    void connectToEventStream();

    return () => {
      controller.abort();
      if (eventStreamRef.current === controller) eventStreamRef.current = null;
    };
  }, [handlePipelineEvent, sessionId]);

  useEffect(() => {
    return () => {
      startRequestRef.current?.abort();
      startRequestRef.current = null;
      eventStreamRef.current?.abort();
      eventStreamRef.current = null;
    };
  }, []);

  const pipelineIsBusy = connectionStatus === "starting"
    || connectionStatus === "connected"
    || connectionStatus === "reconnecting"
    || connectionStatus === "review";

  const currentAgent = activeAgent ? agents[activeAgent] : null;
  const currentTitle = activeAgent
    ? humanizeTask(agentStates[activeAgent].task)
    : connectionStatus === "review"
      ? "Pipeline đang chờ phê duyệt"
      : connectionStatus === "completed"
        ? "Pipeline đã hoàn tất"
        : connectionStatus === "starting"
          ? "Đang khởi tạo pipeline"
          : "Sẵn sàng chạy pipeline";
  const currentDescription = activeAgent
    ? currentAgent?.summary
    : connectionStatus === "review"
      ? "Validator Agent đã hoàn tất kiểm soát hoặc phát hiện nội dung cần người có thẩm quyền xem xét."
      : connectionStatus === "completed"
        ? "Finance, Risk, Decision và Validator Agent đã hoàn tất toàn bộ quy trình."
        : "Nhấn Start Pipeline để bắt đầu và theo dõi công việc của từng agent theo thời gian thực.";

  return (
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-[var(--fin-bg)] text-[var(--fin-text)]">
      <Bar />

      <main className="mx-auto w-full max-w-[1440px] px-4 pb-12 pt-28 sm:px-6 sm:pt-32 lg:px-8 xl:px-10">
        <header className="flex flex-col gap-5 border-b border-white/10 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className={`flex items-center gap-2 text-xs font-medium ${connectionStatus === "error" ? "text-rose-300" : connectionStatus === "connected" ? "text-emerald-300" : "text-zinc-500"}`}>
                <span className={`size-1.5 rounded-full ${connectionStatus === "connected" ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,.8)]" : connectionStatus === "error" ? "bg-rose-400" : "bg-zinc-600"}`} />
                {connectionLabel(connectionStatus)}
              </span>
              {sessionId && <span className="font-mono text-[11px] tabular-nums text-zinc-600">RUN #{sessionId}</span>}
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-white sm:text-3xl">Agent execution monitor</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">Theo dõi công việc, kết quả và các cổng kiểm soát giữa Finance, Risk, Decision và Validator Agent.</p>
          </div>

          <button
            type="button"
            onClick={startPipeline}
            disabled={pipelineIsBusy}
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-zinc-100 px-5 text-sm font-semibold text-zinc-950 transition hover:bg-white active:translate-y-px disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
          >
            <Play className="size-4" fill="currentColor" strokeWidth={1.8} />
            {connectionStatus === "starting" ? "Đang khởi tạo..." : pipelineIsBusy ? "Pipeline đang chạy" : sessionId ? "Chạy pipeline mới" : "Start Pipeline"}
          </button>
        </header>

        {errorMessage && (
          <div className="mt-5 flex items-start gap-3 rounded-xl border border-rose-400/25 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-200">
            <CircleAlert className="mt-0.5 size-4 shrink-0" strokeWidth={1.8} />
            <p>{errorMessage}</p>
          </div>
        )}

        <section className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,.5fr)]">
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/70 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,.05)] sm:p-6">
            <div className="absolute inset-y-0 left-0 w-px bg-emerald-400/70" aria-hidden="true" />
            <div className="flex items-start gap-4">
              <span className={`flex size-11 shrink-0 items-center justify-center rounded-xl border ${activeAgent ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300" : "border-white/10 bg-white/[0.04] text-zinc-500"}`}>
                {activeAgent ? <LoaderCircle className="size-5 animate-spin" strokeWidth={1.8} /> : <Activity className="size-5" strokeWidth={1.8} />}
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium text-zinc-500">Công việc hiện tại</p>
                <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-white sm:text-2xl">{currentTitle}</h2>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-400">{currentDescription}</p>
                {currentAgent && (
                  <div className="mt-4 flex items-center gap-2 text-xs font-medium" style={{ color: currentAgent.accent }}>
                    <span className="size-1.5 rounded-full bg-current shadow-[0_0_8px_currentColor]" />
                    {currentAgent.name} đang xử lý
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 divide-x divide-white/10 rounded-2xl border border-white/10 bg-white/[0.025]">
            <div className="p-4 sm:p-5">
              <p className="font-mono text-xl font-semibold tabular-nums text-white">{completedAgentCount}/{AGENT_IDS.length}</p>
              <p className="mt-1 text-[11px] leading-4 text-zinc-600">Agent hoàn tất</p>
            </div>
            <div className="p-4 sm:p-5">
              <p className="font-mono text-xl font-semibold tabular-nums text-white">{completedTaskCount}</p>
              <p className="mt-1 text-[11px] leading-4 text-zinc-600">Task hoàn tất</p>
            </div>
            <div className="p-4 sm:p-5">
              <p className="font-mono text-xl font-semibold tabular-nums text-white">{activity.length}</p>
              <p className="mt-1 text-[11px] leading-4 text-zinc-600">Event đã nhận</p>
            </div>
          </div>
        </section>

        <section className="mt-6">
          <div className="mb-4">
            <h2 className="text-base font-semibold text-white">Luồng xử lý</h2>
            <p className="mt-1 text-xs text-zinc-600">Chọn một agent để xem log liên quan.</p>
          </div>
          <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {AGENT_IDS.map((id, index) => (
              <AgentStage
                key={id}
                id={id}
                index={index}
                selected={selected === id}
                active={activeAgent === id}
                state={agentStates[id]}
                eventCount={agentEventCounts[id]}
                onSelect={() => {
                  setSelected(id);
                  setLogFilter(id);
                }}
              />
            ))}
          </ol>
        </section>

        <section className="mt-8 border-t border-white/10 pt-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-white">Nhật ký hoạt động</h2>
              <p className="mt-1 max-w-2xl text-sm leading-6 text-zinc-500">Các event bắt đầu và kết thúc của cùng một tool được gộp thành một task. Dữ liệu kỹ thuật được ẩn mặc định.</p>
            </div>
            <div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-white/10 bg-zinc-950/60 p-1">
              {(["All", ...AGENT_IDS] as LogFilter[]).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setLogFilter(filter)}
                  className={`shrink-0 rounded-md px-3 py-2 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${
                    logFilter === filter ? "bg-white/10 text-white" : "text-zinc-500 hover:bg-white/[0.05] hover:text-zinc-300"
                  }`}
                >
                  {filter === "All" ? "Tất cả" : agents[filter].name.replace(" Agent", "")}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5">
            {filteredItems.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.015] px-5 py-14 text-center">
                <Activity className="mx-auto size-6 text-zinc-700" strokeWidth={1.6} />
                <p className="mt-4 text-sm font-medium text-zinc-300">Chưa có hoạt động để hiển thị</p>
                <p className="mt-1 text-xs text-zinc-600">Bắt đầu pipeline hoặc chọn bộ lọc khác.</p>
              </div>
            ) : (
              <div className="grid gap-3">
                {filteredItems.map((item) => <ActivityRow key={item.id} item={item} />)}
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
