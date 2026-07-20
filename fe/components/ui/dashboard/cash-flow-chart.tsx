"use client";

import { useState } from "react";
import { scaleSeries, smoothPath } from "./chart-utils";

const WIDTH = 680;
const HEIGHT = 300;
const PADDING = { left: 46, right: 18, top: 16, bottom: 34 };
const months = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"];
const gridValues = [0, 0.5, 1, 1.5, 2, 2.5];

const series = [
  { id: "inflow", label: "Tiền vào", values: [1.35, 1.12, 1.85, 1.42, 2.06, 1.88, 2.24], color: "#34d399" },
  { id: "outflow", label: "Tiền ra", values: [1.1, 1.04, 1.38, 1.19, 1.62, 1.57, 1.73], color: "#a1a1aa" },
  { id: "net-cash", label: "Dòng tiền thuần", values: [0.25, 0.08, 0.47, 0.23, 0.44, 0.31, 0.51], color: "var(--fin-net-cash)" },
] as const;

interface HoveredPoint {
  x: number;
  y: number;
  label: string;
  value: number;
  color: string;
}

export function CashFlowChart() {
  const plotBottom = HEIGHT - PADDING.bottom;
  const [hoveredPoint, setHoveredPoint] = useState<HoveredPoint | null>(null);

  return (
    <div className="relative group/chart w-full">
      <div className="mb-4 flex flex-wrap items-center justify-start gap-4 text-xs text-zinc-400 sm:justify-end">
        {series.map((item) => (
          <span key={item.id} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Dòng tiền doanh nghiệp từ tháng một đến tháng bảy">
        <defs>
          {series.map((item) => (
            <linearGradient key={item.id} id={`${item.id}-area`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={item.color} stopOpacity="0.17" />
              <stop offset="100%" stopColor={item.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>

        {gridValues.map((value) => {
          const y = PADDING.top + ((2.5 - value) / 2.5) * (HEIGHT - PADDING.top - PADDING.bottom);
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
          const points = scaleSeries(item.values, WIDTH, HEIGHT, PADDING, 0, 2.5);
          const path = smoothPath(points);
          const area = `${path} L ${points.at(-1)?.x} ${plotBottom} L ${points[0].x} ${plotBottom} Z`;
          return (
            <g key={item.id}>
              <path d={area} fill={`url(#${item.id}-area)`} />
              <path d={path} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              {points.map((point, index) => {
                const isHovered = hoveredPoint && hoveredPoint.x === point.x && hoveredPoint.y === point.y;
                return (
                  <circle
                    key={months[index]}
                    cx={point.x}
                    cy={point.y}
                    r={isHovered ? 5.5 : 3.5}
                    fill={isHovered ? item.color : "var(--fin-surface)"}
                    stroke={item.color}
                    strokeWidth={isHovered ? 1.5 : 2}
                    className="cursor-pointer transition-all duration-150"
                    onMouseEnter={() =>
                      setHoveredPoint({
                        x: point.x,
                        y: point.y,
                        label: `${item.label} (${months[index]})`,
                        value: item.values[index],
                        color: item.color,
                      })
                    }
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                );
              })}
            </g>
          );
        })}
      </svg>

      {hoveredPoint && (
        <div
          className="pointer-events-none absolute z-30 rounded-md border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]/95 px-2.5 py-1.5 text-[10px] font-semibold text-[var(--fin-text)] shadow-lg backdrop-blur-xs transition-all duration-150"
          style={{
            left: `${(hoveredPoint.x / WIDTH) * 100}%`,
            top: `${(hoveredPoint.y / HEIGHT) * 100}%`,
            transform: "translate(-50%, -130%)",
          }}
        >
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="size-1.5 rounded-full" style={{ backgroundColor: hoveredPoint.color }} />
            <span>{hoveredPoint.label}:</span>
            <span className="font-mono font-bold text-emerald-300">{hoveredPoint.value.toLocaleString("vi-VN")} tỷ ₫</span>
          </div>
        </div>
      )}
    </div>
  );
}
