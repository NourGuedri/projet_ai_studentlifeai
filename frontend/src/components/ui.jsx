"use client";

export const cx = (...parts) => parts.filter(Boolean).join(" ");

const BUTTONS = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600",
  success: "bg-leaf-600 text-white hover:bg-leaf-700 focus-visible:outline-leaf-600",
  secondary: "bg-white text-brand-700 border border-brand-200 hover:bg-brand-50 focus-visible:outline-brand-600",
  ghost: "text-brand-700 hover:bg-brand-50 focus-visible:outline-brand-600",
  danger: "bg-white text-red-700 border border-red-200 hover:bg-red-50 focus-visible:outline-red-600",
};

/** Class string so <Link> can look like a button. */
export function btnClass(variant = "primary", size = "md", extra) {
  return cx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
    "focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60",
    size === "sm" ? "px-3 py-1.5 text-sm" : "px-4 py-2.5 text-sm",
    BUTTONS[variant],
    extra,
  );
}

export function Button({ variant, size, loading = false, className, disabled, children, ...props }) {
  return (
    <button type="button" disabled={disabled || loading} className={btnClass(variant, size, className)} {...props}>
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className = "h-5 w-5" }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ full = false }) {
  return (
    <div className={cx("flex items-center justify-center text-brand-600", full ? "min-h-dvh" : "py-16")}>
      <Spinner className="h-7 w-7" />
    </div>
  );
}

const INPUT =
  "w-full rounded-lg border border-brand-200 bg-white px-3 py-2 text-sm text-navy-900 placeholder:text-slate-400 " +
  "focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30";

export const Input = ({ className, ...props }) => <input className={cx(INPUT, className)} {...props} />;
export const Textarea = ({ className, ...props }) => <textarea rows={3} className={cx(INPUT, className)} {...props} />;
export const Select = ({ className, children, ...props }) => (
  <select className={cx(INPUT, className)} {...props}>{children}</select>
);

export function Field({ label, hint, children, className }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1 block text-sm font-medium text-navy-900">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Card({ className, children, ...props }) {
  return (
    <div className={cx("rounded-xl border border-brand-100 bg-white p-4 sm:p-5", className)} {...props}>
      {children}
    </div>
  );
}

const BADGES = {
  blue: "bg-brand-50 text-brand-700",
  green: "bg-leaf-50 text-leaf-700",
  slate: "bg-slate-100 text-slate-600",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-700",
};
export function Badge({ tone = "blue", children }) {
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", BADGES[tone])}>{children}</span>;
}

const ALERTS = {
  error: "border-red-200 bg-red-50 text-red-800",
  success: "border-leaf-100 bg-leaf-50 text-leaf-700",
  info: "border-brand-100 bg-brand-50 text-brand-700",
};
export function Alert({ tone = "error", children }) {
  if (!children) return null;
  return <div role={tone === "error" ? "alert" : "status"} className={cx("rounded-lg border px-3 py-2.5 text-sm", ALERTS[tone])}>{children}</div>;
}

export function ProgressBar({ value = 0, tone = "green" }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-brand-50" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all", tone === "green" ? "bg-leaf-500" : "bg-brand-500")} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function ScoreRing({ percent, size = 112 }) {
  const r = 44;
  const c = 2 * Math.PI * r;
  const good = percent >= 70;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="-rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="9" className="stroke-brand-50" />
        <circle cx="50" cy="50" r={r} fill="none" strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * percent) / 100}
          className={good ? "stroke-leaf-500" : "stroke-brand-500"} />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-display text-2xl font-bold">{percent}%</span>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-prose text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function EmptyState({ title, text, action }) {
  return (
    <div className="rounded-xl border border-dashed border-brand-200 bg-white px-6 py-10 text-center">
      <p className="font-display text-lg font-semibold">{title}</p>
      {text && <p className="mx-auto mt-1 max-w-sm text-sm text-slate-600">{text}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

const ICONS = {
  home: ["M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V11z"],
  user: ["M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M20 21a8 8 0 0 0-16 0"],
  file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z", "M14 3v5h5"],
  book: ["M4 5a2 2 0 0 1 2-2h13v15H6a2 2 0 0 0-2 2V5z", "M6 18h13v3H6"],
  quiz: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", "M8 12l3 3 5-6"],
  chart: ["M4 20V10M10 20V4M16 20v-7M22 20H2"],
  cap: ["M2 9l10-5 10 5-10 5L2 9z", "M6 11.5V16c0 1 3 3 6 3s6-2 6-3v-4.5"],
  plus: ["M12 5v14M5 12h14"],
  menu: ["M4 6h16M4 12h16M4 18h16"],
  close: ["M6 6l12 12M18 6L6 18"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5M21 12H9"],
  bell: ["M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9", "M10.3 21a1.94 1.94 0 0 0 3.4 0"],
  users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z", "M22 21v-2a4 4 0 0 0-3-3.9", "M16 3.1a4 4 0 0 1 0 7.8"],
  flag: ["M4 22V4", "M4 4h13l-2 4 2 4H4"],
  megaphone: ["M3 11v2a1 1 0 0 0 1 1h3l8 4V6L7 10H4a1 1 0 0 0-1 1z", "M19 9a4 4 0 0 1 0 6"],
};
export function Icon({ name, className = "h-5 w-5" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      {ICONS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}
