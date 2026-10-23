"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useNotifications } from "@/lib/notifications";
import Logo from "./Logo";
import { Icon, cx } from "./ui";

const ALL = ["student", "teacher", "admin"];
const NAV = [
  { href: "/dashboard", label: "Tableau de bord", icon: "home", roles: ALL },
  { href: "/notifications", label: "Notifications", icon: "bell", roles: ALL, badge: true },
  { href: "/profile", label: "Mon profil", icon: "user", roles: ["student"] },
  { href: "/profile/cv", label: "Importer mon CV", icon: "file", roles: ["student"] },
  { group: "Révision et formations", roles: ALL },
  { href: "/learning/courses", label: "Mes cours", icon: "book", roles: ["student"] },
  { href: "/learning/quizzes", label: "Quiz", icon: "quiz", roles: ["student"] },
  { href: "/learning/results", label: "Résultats", icon: "chart", roles: ["student"] },
  { href: "/learning/formations", label: "Formations", icon: "cap", roles: ALL },
  { href: "/learning/teach", label: "Enseigner", icon: "plus", roles: ["teacher", "admin"] },
];

function Brand() {
  return (
    <Link href="/dashboard" className="block">
      <Logo />
    </Link>
  );
}

function Sidebar({ onNavigate }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const items = NAV.filter((n) => n.group || n.roles.includes(user.role));
  const current = NAV.filter((n) => n.href && (pathname === n.href || pathname.startsWith(n.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];

  return (
    <div className="flex h-full flex-col px-4 py-5">
      <Brand />
      <nav className="mt-8 flex-1 space-y-1 overflow-y-auto">
        {items.map((item) =>
          item.group ? (
            <p key={item.group} className="px-3 pb-1 pt-5 text-xs font-medium text-brand-200/70">{item.group}</p>
          ) : (
            <Link key={item.href} href={item.href} onClick={onNavigate}
              className={cx("flex items-center gap-3 rounded-lg border-l-4 px-3 py-2.5 text-sm font-medium transition-colors",
                current?.href === item.href ? "border-leaf-500 bg-white/10 text-white" : "border-transparent text-brand-100 hover:bg-white/5 hover:text-white")}>
              <Icon name={item.icon} className="h-5 w-5 shrink-0" />
              <span className="min-w-0 flex-1">{item.label}</span>
              {item.badge && unread > 0 && (
                <span className="rounded-full bg-leaf-500 px-2 py-0.5 text-xs font-semibold text-white" aria-label={`${unread} non lue(s)`}>{unread > 99 ? "99+" : unread}</span>
              )}
            </Link>
          ),
        )}
      </nav>
      <div className="border-t border-white/10 pt-4">
        <p className="truncate px-3 text-sm font-medium text-white">{user.first_name || user.email}</p>
        <p className="truncate px-3 pb-2 text-xs text-brand-200/70">{user.email}</p>
        <button onClick={async () => { await logout(); router.replace("/login"); }}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-brand-100 hover:bg-white/5 hover:text-white">
          <Icon name="logout" /> Se déconnecter
        </button>
      </div>
    </div>
  );
}

export default function Shell({ children }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { unread } = useNotifications();
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="min-h-dvh lg:flex">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 bg-navy-900 lg:block"><Sidebar /></aside>

      <header className="sticky top-0 z-30 flex items-center justify-between bg-navy-900 px-4 py-3 lg:hidden">
        <Brand />
        <div className="flex items-center gap-1">
          <Link href="/notifications" aria-label={unread > 0 ? `Notifications, ${unread} non lue(s)` : "Notifications"} className="relative rounded-lg p-2 text-white hover:bg-white/10">
            <Icon name="bell" className="h-6 w-6" />
            {unread > 0 && <span className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-leaf-500 ring-2 ring-navy-900" />}
          </Link>
          <button onClick={() => setOpen(true)} aria-label="Ouvrir le menu" className="rounded-lg p-2 text-white hover:bg-white/10">
            <Icon name="menu" className="h-6 w-6" />
          </button>
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-72 max-w-[85vw] bg-navy-900 shadow-xl">
            <button onClick={() => setOpen(false)} aria-label="Fermer le menu" className="absolute right-3 top-4 rounded-lg p-2 text-white hover:bg-white/10">
              <Icon name="close" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-5xl">{children}</div>
      </main>
    </div>
  );
}
