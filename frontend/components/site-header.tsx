"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Camera, FlaskConical, LayoutDashboard, ListTodo, QrCode, Timer, Wrench } from "lucide-react";
import { ThemeToggle } from "@/components/theme";
import { HazardAlertBar } from "@/components/hazard-alert-bar";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/report", label: "Report", icon: Camera },
  { href: "/tickets", label: "Queue", icon: ListTodo },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/eval", label: "Evaluation", icon: FlaskConical },
  { href: "/baseline", label: "Legacy form", icon: Timer },
  { href: "/admin/qr", label: "QR sheet", icon: QrCode },
];

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label="SnapFix home">
      <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
        <Wrench className="size-4" aria-hidden="true" />
      </span>
      <span className={cn("text-lg", compact && "text-base")}>SnapFix</span>
    </Link>
  );
}

export function SiteHeader() {
  const pathname = usePathname() || "/";
  const reporterView = pathname.startsWith("/r/") || pathname.startsWith("/report");

  if (reporterView) {
    return (
      <header className="no-print sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-xl items-center justify-between px-4">
          <Logo compact />
          <ThemeToggle />
        </div>
      </header>
    );
  }

  return (
    <header className="no-print sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <Logo />
        <nav aria-label="Main" className="-mx-1 flex flex-1 items-center gap-1 overflow-x-auto">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  active && "bg-accent text-accent-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden="true" />
                {label}
              </Link>
            );
          })}
        </nav>
        <ThemeToggle />
      </div>
      <HazardAlertBar />
    </header>
  );
}
