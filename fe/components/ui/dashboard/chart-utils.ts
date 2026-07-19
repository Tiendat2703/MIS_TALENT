export type ChartPoint = { x: number; y: number };

export function smoothPath(points: ChartPoint[]) {
  if (points.length < 2) return "";

  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`;

    const previous = points[index - 1];
    const previousPrevious = points[index - 2] ?? previous;
    const next = points[index + 1] ?? point;
    const tension = 0.18;
    const controlOneX = previous.x + (point.x - previousPrevious.x) * tension;
    const controlOneY = previous.y + (point.y - previousPrevious.y) * tension;
    const controlTwoX = point.x - (next.x - previous.x) * tension;
    const controlTwoY = point.y - (next.y - previous.y) * tension;

    return `${path} C ${controlOneX} ${controlOneY}, ${controlTwoX} ${controlTwoY}, ${point.x} ${point.y}`;
  }, "");
}

export function scaleSeries(
  values: readonly number[],
  width: number,
  height: number,
  padding: { left: number; right: number; top: number; bottom: number },
  minValue: number,
  maxValue: number,
) {
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  return values.map((value, index) => ({
    x: padding.left + (index / Math.max(values.length - 1, 1)) * chartWidth,
    y: padding.top + ((maxValue - value) / (maxValue - minValue)) * chartHeight,
  }));
}
