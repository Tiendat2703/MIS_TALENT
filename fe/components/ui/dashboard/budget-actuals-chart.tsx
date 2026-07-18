"use client";

import { useState } from "react";
import { scaleSeries, smoothPath } from "./chart-utils";

const WIDTH = 680;
const HEIGHT = 230;
const PADDING = { left: 46, right: 18, top: 16, bottom: 34 };
const categories = ["Land", "Construction", "Labor", "Materials", "Permits"];
const series = [
  { id: "budget", label: "Budget", values: [8, 7, 10, 9, 11], color: "#71717a", dash: "7 6" },
  { id: "actual", label: "Actual", values: [6, 9, 8, 12, 10], color: "#34d399", dash: undefined },
] as const;

interface HoveredPoint {
  x: number;
  y: number;
  label: string;
  value: number;
  color: string;
}

export function BudgetActualsChart() {
  const [hoveredPoint, setHoveredPoint] = useState<HoveredPoint | null>(null);

  return (
    <div className="relative group/chart w-full">
      <div className="mb-4 flex items-center justify-start gap-4 text-xs text-zinc-400 sm:justify-end">
        {series.map((item) => (
          <span key={item.id} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Budget versus actuals by category">
        {[6, 7, 8, 9, 10, 11, 12].map((value) => {
          const y = PADDING.top + ((12 - value) / 6) * (HEIGHT - PADDING.top - PADDING.bottom);
          return (
            <g key={value}>
              <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} stroke="rgba(255,255,255,.07)" />
              <text x={PADDING.left - 12} y={y + 4} textAnchor="end" fill="#71717a" fontSize="11">{value}M</text>
            </g>
          );
        })}

        {categories.map((category, index) => {
          const x = PADDING.left + (index / (categories.length - 1)) * (WIDTH - PADDING.left - PADDING.right);
          return <text key={category} x={x} y={HEIGHT - 8} textAnchor="middle" fill="#71717a" fontSize="11">{category}</text>;
        })}

        {series.map((item) => {
          const points = scaleSeries(item.values, WIDTH, HEIGHT, PADDING, 6, 12);
          return (
            <g key={item.id}>
              <path
                d={smoothPath(points)}
                fill="none"
                stroke={item.color}
                strokeWidth="3"
                strokeDasharray={item.dash}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {points.map((point, index) => {
                const isHovered = hoveredPoint && hoveredPoint.x === point.x && hoveredPoint.y === point.y;
                return (
                  <circle
                    key={categories[index]}
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
                        label: `${item.label} (${categories[index]})`,
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
            <span className="font-mono text-emerald-300 font-bold">${hoveredPoint.value}M</span>
          </div>
        </div>
      )}
    </div>
  );
}
