import {
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";

import { classNames } from "../utils/format";

type BadgeTone = "neutral" | "accent" | "positive" | "warning" | "danger" | "info" | "violet";

export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={classNames("badge", `badge--${tone}`, className)}>
      {dot ? <span className="badge__dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

export function StatCard({
  label,
  value,
  detail,
  accent = "lime",
  icon: Icon,
  trend,
  className,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  accent?: "lime" | "cyan" | "amber" | "violet" | "rose";
  icon?: LucideIcon;
  trend?: { value: string; direction: "up" | "down" | "flat" };
  className?: string;
}) {
  return (
    <article className={classNames("stat-card", `stat-card--${accent}`, className)}>
      <div className="stat-card__top">
        <span className="eyebrow">{label}</span>
        {Icon ? (
          <span className="stat-card__icon">
            <Icon size={15} strokeWidth={1.8} />
          </span>
        ) : null}
      </div>
      <div className="stat-card__value">{value}</div>
      <div className="stat-card__bottom">
        {detail ? <span className="stat-card__detail">{detail}</span> : <span />}
        {trend ? (
          <span className={classNames("trend", `trend--${trend.direction}`)}>
            {trend.direction === "up" ? (
              <ArrowUpRight size={13} />
            ) : trend.direction === "down" ? (
              <ArrowDownRight size={13} />
            ) : null}
            {trend.value}
          </span>
        ) : null}
      </div>
    </article>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  meta,
}: {
  eyebrow: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        <span className="eyebrow eyebrow--accent">{eyebrow}</span>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
        {meta ? <div className="page-header__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </header>
  );
}

export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
  flush = false,
  footer,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  flush?: boolean;
  footer?: ReactNode;
}) {
  return (
    <section className={classNames("panel", className)}>
      {(title || actions) && (
        <header className="panel__header">
          <div>
            {title ? <h2 className="panel__title">{title}</h2> : null}
            {description ? <p className="panel__description">{description}</p> : null}
          </div>
          {actions ? <div className="panel__actions">{actions}</div> : null}
        </header>
      )}
      <div className={classNames("panel__body", flush && "panel__body--flush")}>{children}</div>
      {footer ? <footer className="panel__footer">{footer}</footer> : null}
    </section>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {Icon ? (
        <span className="empty-state__icon">
          <Icon size={22} strokeWidth={1.6} />
        </span>
      ) : null}
      <h3>{title}</h3>
      {description ? <p>{description}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}

export function LoadingState({ rows = 4, label = "Loading data" }: { rows?: number; label?: string }) {
  return (
    <div className="loading-state" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <span className="skeleton" key={index} style={{ width: `${92 - index * 9}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  compact = false,
}: {
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className={classNames("error-state", compact && "error-state--compact")}>
      <span className="error-state__mark" aria-hidden="true">
        !
      </span>
      <div>
        <strong>Unable to load this view</strong>
        <p>{message}</p>
      </div>
      {onRetry ? (
        <button className="button button--ghost button--sm" type="button" onClick={onRetry}>
          <RefreshCw size={13} /> Retry
        </button>
      ) : null}
    </div>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label?: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          className={classNames("segmented__option", option.value === value && "is-active")}
          onClick={() => onChange(option.value)}
          aria-pressed={option.value === value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ProgressBar({
  value,
  tone = "lime",
  label,
}: {
  value: number;
  tone?: "lime" | "cyan" | "amber" | "rose";
  label?: string;
}) {
  const bounded = Math.max(0, Math.min(100, value));
  return (
    <div
      className={classNames("progress", `progress--${tone}`)}
      role="progressbar"
      aria-valuenow={bounded}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
    >
      <span style={{ width: `${bounded}%` }} />
    </div>
  );
}

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <button className="copy-button" type="button" onClick={() => void copy()} title={value}>
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? "Copied" : label}
    </button>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  icon?: LucideIcon;
}

export function Button({
  children,
  variant = "secondary",
  size = "md",
  icon: Icon,
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={classNames("button", `button--${variant}`, `button--${size}`, className)}
      {...props}
    >
      {Icon ? <Icon size={15} strokeWidth={2} /> : null}
      {children}
    </button>
  );
}

export function Pager({
  page,
  pageSize,
  total,
  onChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span>
        {total === 0
          ? "0 records"
          : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`}
      </span>
      <div className="pager__controls">
        <button
          type="button"
          className="icon-button"
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="pager__page">
          {page} / {pages}
        </span>
        <button
          type="button"
          className="icon-button"
          onClick={() => onChange(page + 1)}
          disabled={page >= pages}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}

export function MetaItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="meta-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export interface MenuItem {
  key: string;
  label: string;
  description?: string;
  href: string;
  icon?: LucideIcon;
}

export function DropdownMenu({
  label,
  buttonLabel,
  icon: Icon,
  items,
  align = "right",
  size = "md",
  variant = "secondary",
  onSelect,
}: {
  label?: ReactNode;
  buttonLabel: string;
  icon?: LucideIcon;
  items: MenuItem[];
  align?: "left" | "right";
  size?: "sm" | "md";
  variant?: "primary" | "secondary" | "ghost";
  onSelect?: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLAnchorElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function focusItem(index: number) {
    const bounded = (index + items.length) % items.length;
    itemRefs.current[bounded]?.focus();
  }

  return (
    <div className="dropdown" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={classNames(
          "button",
          `button--${variant}`,
          `button--${size}`,
          "dropdown__trigger",
          open && "is-open",
        )}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            window.setTimeout(() => focusItem(0), 0);
          }
        }}
      >
        {Icon ? <Icon size={15} strokeWidth={2} /> : null}
        {label ?? buttonLabel}
        <ChevronDown
          size={13}
          className={classNames("dropdown__chevron", open && "is-open")}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div
          className={classNames("dropdown__menu", `dropdown__menu--${align}`)}
          role="menu"
          aria-label={buttonLabel}
        >
          {items.map((item, index) => {
            const ItemIcon = item.icon;
            return (
              <a
                key={item.key}
                ref={(node) => {
                  itemRefs.current[index] = node;
                }}
                className="dropdown__item"
                role="menuitem"
                href={item.href}
                download
                onClick={(event) => {
                  if (onSelect) {
                    event.preventDefault();
                    setOpen(false);
                    onSelect(item.key);
                    return;
                  }
                  setOpen(false);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    focusItem(index + 1);
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    focusItem(index - 1);
                  }
                }}
              >
                {ItemIcon ? <ItemIcon size={14} aria-hidden="true" /> : null}
                <span className="dropdown__item-copy">
                  <strong>{item.label}</strong>
                  {item.description ? <span>{item.description}</span> : null}
                </span>
              </a>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
