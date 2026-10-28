import type { CostCoverage, ModelName, Severity } from "../types/api";

const integerFormatter = new Intl.NumberFormat("en-IE", { maximumFractionDigits: 0 });
const decimalFormatter = new Intl.NumberFormat("en-IE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const compactFormatter = new Intl.NumberFormat("en-IE", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function formatCurrency(
  value: number | string | null | undefined,
  options: { compact?: boolean; decimals?: boolean; currency?: string } = {},
) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const currency = options.currency ?? "EUR";
  const formatter = options.compact ? compactFormatter : options.decimals ? decimalFormatter : integerFormatter;
  return `${currency === "EUR" ? "€" : `${currency} `}${formatter.format(numeric)}`;
}

export function formatNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? integerFormatter.format(numeric) : "—";
}

export function formatDecimal(value: number | string | null | undefined, digits = 2) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return numeric.toLocaleString("en-IE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(
  value: number | string | null | undefined,
  options: { signed?: boolean; digits?: number } = {},
) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const formatted = `${formatDecimal(Math.abs(numeric), options.digits ?? 1)}%`;
  if (numeric < 0) return `−${formatted}`;
  return options.signed ? `+${formatted}` : formatted;
}

export function formatSignedCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const formatted = formatCurrency(Math.abs(value));
  if (value === 0) return formatted;
  return value > 0 ? `+${formatted}` : `−${formatted}`;
}

export function formatPp(
  value: number | string | null | undefined,
  options: { signed?: boolean; digits?: number } = {},
) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const digits = options.digits ?? 2;
  const normalised = Object.is(numeric, -0) ? 0 : numeric;
  const rounded = Number(normalised.toFixed(digits));
  if (rounded === 0) return `${formatDecimal(0, digits)} pp`;
  const formatted = formatDecimal(Math.abs(rounded), digits);
  const sign = rounded < 0 ? "−" : options.signed ? "+" : "";
  return `${sign}${formatted} pp`;
}

export function formatRoas(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? `${formatDecimal(numeric, 2)}×` : "—";
}

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const normalized = value.includes("T") ? value : value.includes(" ") ? value.replace(" ", "T") : `${value}T00:00:00`;
  const date = new Date(normalized.endsWith("Z") || /[+-]\d\d:\d\d$/.test(normalized) ? normalized : `${normalized}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = {}) {
  const date = parseDate(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...options,
  }).format(date);
}

export function formatDateTime(value: string | null | undefined) {
  const date = parseDate(value);
  if (!date) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function formatMonth(value: string) {
  const date = parseDate(`${value}-01`);
  if (!date) return value;
  return new Intl.DateTimeFormat("en-GB", { month: "short", year: "2-digit" }).format(date);
}

export const MODEL_LABELS: Record<ModelName, string> = {
  first_touch: "First touch",
  last_touch: "Last touch",
  linear: "Linear",
};

export function modelLabel(model: string) {
  return MODEL_LABELS[model as ModelName] ?? humanize(model);
}

export function humanize(value: string | null | undefined) {
  if (!value) return "—";
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function issueLabel(value: string | null | undefined) {
  if (!value) return "—";
  const labels: Record<string, string> = {
    DUPLICATE_REVENUE: "Duplicate revenue",
    POST_CONVERSION_TOUCH: "Post-conversion touch",
    CURRENCY_MISMATCH: "Currency mismatch",
    MISSING_CAMPAIGN_COST: "Missing campaign cost",
    UNSUPPORTED_IDENTITY_LINK: "Unsupported identity link",
  };
  return labels[value] ?? humanize(value);
}

export function coverageLabel(value: CostCoverage | string | null | undefined) {
  if (!value) return "—";
  const labels: Record<string, string> = {
    COMPLETE: "Complete",
    PARTIAL: "Partial",
    MISSING: "Missing",
    NO_COST_BASIS: "No cost basis",
  };
  return labels[value] ?? humanize(value);
}

export function outcomeLabel(value: string) {
  const labels: Record<string, string> = {
    ELIGIBLE: "Eligible",
    POST_CONVERSION: "After conversion",
    OUTSIDE_WINDOW: "Outside lookback",
    IDENTITY_UNRESOLVED: "Unresolved identity",
    CONSENT_DENIED: "Consent denied",
    NO_CAMPAIGN: "No campaign",
  };
  return labels[value] ?? humanize(value);
}

export function severityRank(value: Severity) {
  return value === "HIGH" ? 3 : value === "MEDIUM" ? 2 : 1;
}

export function truncateHash(value: string | null | undefined, length = 12) {
  if (!value) return "—";
  return value.length <= length ? value : `${value.slice(0, length)}…`;
}

export function splitLabel(value: string) {
  return value === "train" ? "Train" : value === "validation" ? "Validation" : "Test";
}

export function initials(value: string) {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
