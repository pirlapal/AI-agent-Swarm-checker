import type { Metadata } from "next"
import localFont from "next/font/local"

import "./globals.css"
import { GradientBlobs } from "@/components/site/gradient-blobs"
import { ThemeProvider } from "@/components/theme-provider"
import { TopNav } from "@/components/site/top-nav"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

const inter = localFont({
  src: "./fonts/inter.ttf",
  variable: "--font-sans",
  display: "swap",
})

const jetbrainsMono = localFont({
  src: "./fonts/jetbrains-mono.ttf",
  variable: "--font-mono",
  display: "swap",
})

export const metadata: Metadata = {
  title: "PlanAI · AI Agent Swarm Platform",
  description:
    "Hackathon prototype for configurable document-review workflows and live agent progress.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "antialiased",
        inter.variable,
        jetbrainsMono.variable,
        "font-sans"
      )}
    >
      <body className="min-h-svh bg-white text-[#1d1d1f]">
        <ThemeProvider>
          <TooltipProvider delayDuration={150}>
            <div className="relative min-h-svh">
              <GradientBlobs />
              <div className="relative z-10 flex min-h-svh flex-col">
                <TopNav />
                <p className="px-4 py-2 text-center text-xs text-neutral-600">Hackathon prototype · Live reviews require an AWS backend. Agent findings require human review.</p>
                <main className="flex-1">{children}</main>
              </div>
            </div>
            <Toaster position="bottom-right" />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
