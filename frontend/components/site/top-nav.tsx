"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Bot, LogOut, Settings } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type NavItem = {
  href: string
  label: string
  disabled?: boolean
}

const navItems: ReadonlyArray<NavItem> = [
  { href: "/dashboard", label: "Dashboard", disabled: true },
  { href: "/workflows", label: "Workflows" },
  { href: "/workflows/run", label: "Run" },
  { href: "/analytics", label: "Analytics", disabled: true },
]

export function TopNav() {
  const pathname = usePathname() ?? "/"
  const onLanding = pathname === "/"

  return (
    <header className="glass-card border-b border-black/[0.08] sticky top-0 z-50">
      <div className="container mx-auto px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2" aria-label="PlanAI home">
            <div className="size-8 rounded-lg bg-[#1d1d1f] flex items-center justify-center shadow-depth-2">
              <Bot className="size-5 text-white" />
            </div>
            <span className="font-semibold text-xl text-[#1d1d1f]">PlanAI</span>
          </Link>
          {!onLanding && (
            <nav className="hidden md:flex items-center gap-6">
              {navItems.map((item) => {
                const active =
                  !item.disabled &&
                  (pathname === item.href ||
                    (item.href !== "/" && pathname.startsWith(item.href)))
                if (item.disabled) {
                  return (
                    <span
                      key={item.href}
                      aria-disabled="true"
                      className="text-sm text-[#86868b]/60 cursor-not-allowed select-none"
                    >
                      {item.label}
                    </span>
                  )
                }
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "text-sm transition-colors",
                      active
                        ? "text-[#1d1d1f] font-medium"
                        : "text-[#86868b] hover:text-[#1d1d1f]"
                    )}
                  >
                    {item.label}
                  </Link>
                )
              })}
            </nav>
          )}
        </div>

        {onLanding ? (
          <div className="flex items-center gap-3">
            <Link href="/workflows">
              <Button variant="ghost" className="text-[#86868b] hover:bg-black/[0.03]">
                Browse workflows
              </Button>
            </Link>
            <Link href="/workflows">
              <Button className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all">
                Get Started
              </Button>
            </Link>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="text-[#86868b] hover:bg-black/[0.03]"
              disabled
            >
              <Settings className="size-4 mr-2" />
              Settings
            </Button>
            <Link href="/">
              <Button
                variant="ghost"
                size="sm"
                className="text-[#86868b] hover:bg-black/[0.03]"
                aria-label="Sign out"
              >
                <LogOut className="size-4" />
              </Button>
            </Link>
          </div>
        )}
      </div>
    </header>
  )
}
