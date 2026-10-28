import { formatCurrency, formatNumber } from "../utils/format";

interface TooltipEntry {
  name?: string;
  dataKey?: string | number;
  value?: number | string;
  color?: string;
  stroke?: string;
  fill?: string;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  currency?: boolean;
  labelRenderer?: (label: string | number | undefined) => string;
}

export function ChartTooltip({
  active,
  payload,
  label,
  currency = true,
  labelRenderer,
}: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <span className="chart-tooltip__label">
        {labelRenderer ? labelRenderer(label) : label}
      </span>
      {payload.map((entry) => {
        const numeric = Number(entry.value ?? 0);
        return (
          <div className="chart-tooltip__row" key={String(entry.dataKey ?? entry.name)}>
            <span
              className="chart-tooltip__swatch"
              style={{ background: entry.color ?? entry.stroke ?? entry.fill ?? "var(--lime)" }}
            />
            <span>{entry.name}</span>
            <strong>{currency ? formatCurrency(numeric) : formatNumber(numeric)}</strong>
          </div>
        );
      })}
    </div>
  );
}
