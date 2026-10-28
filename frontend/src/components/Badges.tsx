import { Badge } from "./Primitives";
import type { CostCoverage, Severity } from "../types/api";
import { coverageLabel } from "../utils/format";

export function SeverityBadge({ severity }: { severity: Severity | string }) {
  const tone = severity === "HIGH" ? "danger" : severity === "MEDIUM" ? "warning" : "neutral";
  return (
    <Badge tone={tone} dot>
      {severity === "HIGH" ? "High" : severity === "MEDIUM" ? "Medium" : "Low"}
    </Badge>
  );
}

export function CoverageBadge({ value }: { value: CostCoverage | string | null }) {
  const tone =
    value === "COMPLETE"
      ? "positive"
      : value === "PARTIAL"
        ? "warning"
        : value === "MISSING"
          ? "danger"
          : "neutral";
  return <Badge tone={tone}>{coverageLabel(value)}</Badge>;
}

export function ValidationBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge>Unknown</Badge>;
  if (status === "PASS") return <Badge tone="positive" dot>Validation passed</Badge>;
  if (status === "PASS_WITH_WARNINGS")
    return <Badge tone="warning" dot>Pass with warnings</Badge>;
  return <Badge tone="danger" dot>Validation failed</Badge>;
}

export function SplitBadge({ split }: { split: string }) {
  return <Badge tone="neutral" className="badge--mono">{split}</Badge>;
}

export function RoiValue({
  value,
  available,
  status,
  roas = false,
}: {
  value: number | string | null;
  available: boolean | string;
  status?: string;
  roas?: boolean;
}) {
  const isAvailable = available === true || available === "true";
  if (!isAvailable || value === null || value === "") {
    return (
      <span className="roi-unavailable" title={status ? status.replaceAll("_", " ").toLowerCase() : "Not available"}>
        Not available
      </span>
    );
  }
  const numeric = typeof value === "number" ? value : Number(value);
  return (
    <span className={numeric < 0 ? "value--negative" : "value--positive"}>
      {roas ? `${numeric.toFixed(2)}×` : `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`}
    </span>
  );
}
