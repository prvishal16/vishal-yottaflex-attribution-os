import {
  Archive,
  Download,
  FileJson,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import {
  api,
  type ExportFileFormat,
  type RunExportFileFormat,
} from "../api/client";
import type { ModelName } from "../types/api";
import { DropdownMenu, type MenuItem } from "./Primitives";

export type ExportMenuFormat = RunExportFileFormat;

export interface ExportOption {
  format: ExportMenuFormat;
  label: string;
  description: string;
  href: string;
}

const FORMAT_ICONS: Record<ExportMenuFormat, typeof FileText> = {
  csv: FileText,
  json: FileJson,
  xlsx: FileSpreadsheet,
  pdf: FileText,
  sql: Archive,
  zip: Archive,
};

export function formatOptions(
  href: (format: ExportFileFormat) => string,
  overrides: Partial<Record<ExportFileFormat, string>> = {},
): ExportOption[] {
  const formats: ExportFileFormat[] = ["csv", "json", "xlsx", "pdf"];
  const defaults: Record<ExportFileFormat, { label: string; description: string }> = {
    csv: { label: "CSV", description: "Flat table of every matching record." },
    json: {
      label: "JSON",
      description: "Structured rows plus run, filter and model context.",
    },
    xlsx: {
      label: "XLSX workbook",
      description: "Summary first, then the full record sheets.",
    },
    pdf: {
      label: "PDF summary",
      description: "Printable scope, reconciliation and page numbers.",
    },
  };
  return formats.map((format) => ({
    format,
    label: defaults[format].label,
    description: overrides[format] ?? defaults[format].description,
    href: href(format),
  }));
}

function filenameFromDisposition(header: string | null, fallback: string) {
  if (!header) return fallback;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match ? match[1] : fallback;
}

async function downloadFile(url: string, fallbackName: string) {
  const response = await fetch(url, { headers: { Accept: "*/*" } });
  if (!response.ok) {
    let detail = `Export failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the status message for non-JSON error bodies.
    }
    throw new Error(detail);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filenameFromDisposition(
    response.headers.get("content-disposition"),
    fallbackName,
  );
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export function ExportMenu({
  options,
  buttonLabel = "Export",
  align = "right",
  size = "md",
  variant = "secondary",
  rowCount,
  note,
  label,
}: {
  options: ExportOption[];
  buttonLabel?: string;
  align?: "left" | "right";
  size?: "sm" | "md";
  variant?: "primary" | "secondary" | "ghost";
  rowCount?: number;
  note?: ReactNode;
  label?: ReactNode;
}) {
  const [pending, setPending] = useState<ExportMenuFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const items: MenuItem[] = options.map((option) => ({
    key: option.format,
    label: option.label,
    description: option.description,
    icon: FORMAT_ICONS[option.format],
    href: option.href,
  }));

  async function run(format: ExportMenuFormat) {
    const option = options.find((candidate) => candidate.format === format);
    if (!option) return;
    setError(null);
    setPending(format);
    try {
      await downloadFile(option.href, `yottaflex-export.${format}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Export failed.");
    } finally {
      setPending(null);
    }
  }

  if (pending) {
    return (
      <span className="button button--secondary button--md is-loading" aria-live="polite">
        <Loader2 size={15} className="is-spinning" /> Preparing {pending.toUpperCase()}
      </span>
    );
  }

  return (
    <div className="export-control">
      <DropdownMenu
        buttonLabel={buttonLabel}
        label={label}
        icon={Download}
        items={items}
        align={align}
        size={size}
        variant={variant}
        onSelect={(key) => void run(key as ExportMenuFormat)}
      />
      {rowCount !== undefined ? (
        <span className="export-control__count">
          {rowCount} row{rowCount === 1 ? "" : "s"} in file
        </span>
      ) : null}
      {note ? <span className="export-control__note">{note}</span> : null}
      {error ? (
        <span className="export-control__error" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function CampaignExportMenu({
  runId,
  model,
  sort,
  order,
  channelId,
  search,
  coverage,
  rowCount,
}: {
  runId: string | null;
  model: ModelName;
  sort: string;
  order: "asc" | "desc";
  channelId?: string | null;
  search?: string;
  coverage?: string;
  rowCount?: number;
}) {
  const options = { model, sort, order, channelId, search, coverage };
  const items = formatOptions(
    (format) => api.campaignPerformanceExportUrl(runId, format, options),
    {
      csv: "Every matching campaign row, not only the visible page.",
      xlsx: "Summary, Campaigns, Attribution and Data Quality sheets.",
      pdf: "Printable ledger with reconciliation summary and page numbers.",
    },
  );
  return <ExportMenu options={items} rowCount={rowCount} />;
}
