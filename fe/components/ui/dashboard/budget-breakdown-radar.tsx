const WIDTH = 620;
const HEIGHT = 540;
const CENTER = { x: WIDTH / 2, y: 266 };
const RADIUS = 185;

const categories = [
  { name: "Land Acquisition", value: "9.8m (-2%)", tone: "positive" },
  { name: "Design & Architecture", value: "3.5m (+9%)", tone: "negative" },
  { name: "Materials & Supplies", value: "8.7m (+2%)", tone: "negative" },
  { name: "Labor & Contractors", value: "12.3m (+2.5%)", tone: "negative" },
  { name: "Permits & Legal", value: "1.6m (-11%)", tone: "positive" },
  { name: "Marketing & Sales", value: "4.8m (-4%)", tone: "positive" },
  { name: "Miscellaneous", value: "2.1m (+5%)", tone: "negative" },
] as const;

const budget = [0.9, 0.62, 0.82, 0.96, 0.58, 0.76, 0.54];
const actual = [0.35, 0.86, 0.24, 0.72, 0.15, 0.32, 0.88];

function polarPoint(index: number, scale: number) {
  const angle = -Math.PI / 2 + (index / categories.length) * Math.PI * 2;
  return {
    x: CENTER.x + Math.cos(angle) * RADIUS * scale,
    y: CENTER.y + Math.sin(angle) * RADIUS * scale,
  };
}

function polygon(values: readonly number[]) {
  return values.map((value, index) => {
    const point = polarPoint(index, value);
    return `${point.x},${point.y}`;
  }).join(" ");
}

export function BudgetBreakdownRadar() {
  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Budget breakdown radar chart">
      {[0.2, 0.4, 0.6, 0.8, 1].map((level) => (
        <polygon key={level} points={polygon(Array(categories.length).fill(level))} fill="none" stroke="rgba(255,255,255,.10)" />
      ))}
      {categories.map((category, index) => {
        const edge = polarPoint(index, 1);
        return <line key={category.name} x1={CENTER.x} y1={CENTER.y} x2={edge.x} y2={edge.y} stroke="rgba(255,255,255,.08)" />;
      })}

      <polygon points={polygon(actual)} fill="rgba(52,211,153,.10)" stroke="#34d399" strokeWidth="2.5" />
      <polygon points={polygon(budget)} fill="rgba(161,161,170,.06)" stroke="#71717a" strokeWidth="2" strokeDasharray="7 6" />

      {actual.map((value, index) => {
        const point = polarPoint(index, value);
        return <circle key={`actual-${categories[index].name}`} cx={point.x} cy={point.y} r="4" fill="#34d399" />;
      })}
      {budget.map((value, index) => {
        const point = polarPoint(index, value);
        return <circle key={`budget-${categories[index].name}`} cx={point.x} cy={point.y} r="3.5" fill="#71717a" />;
      })}

      {categories.map((category, index) => {
        const point = polarPoint(index, 1.22);
        const anchor = point.x < CENTER.x - 20 ? "end" : point.x > CENTER.x + 20 ? "start" : "middle";
        return (
          <text key={category.name} x={point.x} y={point.y - 6} textAnchor={anchor} fill="#a1a1aa" fontSize="11">
            <tspan x={point.x}>{category.name}</tspan>
            <tspan x={point.x} dy="15" fill={category.tone === "positive" ? "#34d399" : "#f87171"} fontWeight="700">{category.value}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
