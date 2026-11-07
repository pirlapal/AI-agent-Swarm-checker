"use client"

import { CheckCircle2, Sparkles, XCircle } from "lucide-react"

import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message"
import { Badge } from "@/components/ui/badge"

interface Props {
  text?: string
  raw: Record<string, unknown>
}

function statusPalette(status: string | undefined) {
  const s = (status || "").toUpperCase()
  if (s === "PASS" || s === "COMPLETE" || s === "OK")
    return {
      className: "border-[#34c759]/20 bg-[#34c759]/10 text-[#34c759]",
      icon: <CheckCircle2 className="mr-1 size-3" />,
    }
  if (s === "FAIL" || s === "ERROR")
    return {
      className: "border-[#ff3b30]/20 bg-[#ff3b30]/10 text-[#ff3b30]",
      icon: <XCircle className="mr-1 size-3" />,
    }
  return {
    className: "border-[#ff9f0a]/20 bg-[#ff9f0a]/10 text-[#ff9f0a]",
    icon: <Sparkles className="mr-1 size-3" />,
  }
}

export function CaseSummaryCard({ text, raw }: Props) {
  const markdown =
    text ||
    (typeof (raw as { summary?: unknown }).summary === "string"
      ? (raw as { summary: string }).summary
      : undefined)
  const overallStatus =
    typeof (raw as { overall_status?: unknown }).overall_status === "string"
      ? (raw as { overall_status: string }).overall_status
      : undefined
  const palette = statusPalette(overallStatus)

  return (
    <Message from="assistant" className="max-w-full">
      <MessageContent className="gap-5">
        <div className="flex items-center gap-3">
          <span className="inline-flex size-10 items-center justify-center rounded-full border border-[#34c759]/20 bg-[#34c759]/10">
            <CheckCircle2 className="size-5 text-[#34c759]" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
              Case Summary
              {overallStatus && (
                <Badge
                  variant="outline"
                  className={`text-[10px] ${palette.className}`}
                >
                  {palette.icon}
                  {overallStatus}
                </Badge>
              )}
            </div>
            <h2 className="text-2xl font-semibold text-[#1d1d1f]">
              The swarm has concluded.
            </h2>
          </div>
        </div>

        <div className="border-t border-black/[0.08] pt-5">
          {markdown ? (
            <div className="prose prose-neutral max-w-none text-sm leading-relaxed text-[#1d1d1f]">
              <MessageResponse parseIncompleteMarkdown={false}>
                {String(markdown)}
              </MessageResponse>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-[#86868b]">
              <Sparkles className="size-4" />
              Final report received. Raw payload attached below.
            </div>
          )}
        </div>

        <details className="rounded-lg border border-black/[0.08] bg-white/60 p-4">
          <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
            Raw envelope
          </summary>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-[#86868b]">
            {JSON.stringify(raw, null, 2)}
          </pre>
        </details>
      </MessageContent>
    </Message>
  )
}
