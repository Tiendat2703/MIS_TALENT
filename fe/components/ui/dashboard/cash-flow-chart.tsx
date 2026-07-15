import { scaleSeries, smoothPath } from "./chart-utils";

const WIDTH = 680;
const HEIGHT = 300;
const PADDING = { left: 46, right: 18, top: 16, bottom: 34 };
const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"];
const gridValues = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22];

const series = [
  { id: "inflow", label: "Inflow", values: [15, 12, 18, 14, 20, 18, 22], color: "#34d399" },
  { id: "outflow", label: "Outflow", values: [12, 10, 13, 11, 15, 14, 16], color: "#a1a1aa" },
  { id: "net-cash", label: "Net cash", values: [5, 4, 6, 5, 8, 7, 9], color: "#f4f4f5" },
] as const;

export function CashFlowChart() {
  const plotBottom = HEIGHT - PADDING.bottom;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-start gap-4 text-xs text-zinc-400 sm:justify-end">
        {series.map((item) => (
          <span key={item.id} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Cash flow from January to July">
        <defs>
          {series.map((item) => (
            <linearGradient key={item.id} id={`${item.id}-area`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={item.color} stopOpacity="0.17" />
              <stop offset="100%" stopColor={item.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>

        {gridValues.map((value) => {
          const y = PADDING.top + ((22 - value) / 18) * (HEIGHT - PADDING.top - PADDING.bottom);
          return (
            <g key={value}>
              <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} stroke="rgba(255,255,255,.07)" />
              <text x={PADDING.left - 12} y={y + 4} textAnchor="end" fill="#71717a" fontSize="11">{value}</text>
            </g>
          );
        })}

        {months.map((month, index) => {
          const x = PADDING.left + (index / (months.length - 1)) * (WIDTH - PADDING.left - PADDING.right);
          return <text key={month} x={x} y={HEIGHT - 8} textAnchor="middle" fill="#71717a" fontSize="11">{month}</text>;
        })}

        {series.map((item) => {
          const points = scaleSeries(item.values, WIDTH, HEIGHT, PADDING, 4, 22);
          const path = smoothPath(points);
          const area = `${path} L ${points.at(-1)?.x} ${plotBottom} L ${points[0].x} ${plotBottom} Z`;
          return (
            <g key={item.id}>
              <path d={area} fill={`url(#${item.id}-area)`} />
              <path d={path} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              {points.map((point, index) => (
                <circle key={months[index]} cx={point.x} cy={point.y} r="3.5" fill="#0f1210" stroke={item.color} strokeWidth="2" />
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
