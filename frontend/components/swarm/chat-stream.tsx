"use client"

import * as React from "react"
import { AlertTriangle, Loader2, Sparkles } from "lucide-react"

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation"
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message"
import { Card, CardContent } from "@/components/ui/card"

import { CategorySwarmPanel, StatusPill } from "./category-swarm-panel"
import { OrchestratorBlock } from "./orchestrator-block"
import { CaseSummaryCard } from "./case-summary-card"
import type { RunState } from "./run-state"

interface Props {
  state: RunState
  /**
   * Id of the category whose streaming update should be shown inline in
   * the chat. When null, only the orchestrator+summary are shown.
   */
  activeCategoryId: string | null
  className?: string
}

/**
 * The auto-scrolling center chat panel. Built on top of Conversation +
 * StickToBottom so new tokens pin to the bottom; users who scroll up
 * get a jump-to-bottom button surfaced by ConversationScrollButton.
 */
export function ChatStream({ state, activeCategoryId, className }: Props) {
  const activeCategory = React.useMemo(
    () =>
      activeCategoryId
        ? state.categories.find((c) => c.category_id === activeCategoryId)
        : null,
    [state.categories, activeCategoryId],
  )

  const waitingForManifest =
    state.categories.length === 0 && state.streamStatus !== "error"

  return (
    <Conversation
      className={`flex h-full flex-col overflow-hidden rounded-xl bg-white/60 ring-1 ring-black/[0.05] ${
        className ?? ""
      }`}
    >
      <ConversationContent className="gap-6 px-5 py-6">
        <OrchestratorBlock
          orchestrator={state.orchestrator}
          streamStatus={state.streamStatus}
        />

        {state.errorMessage && (
          <Card className="border-[#ff3b30]/40 bg-[#ff3b30]/5">
            <CardContent className="flex items-start gap-3 p-5">
              <AlertTriangle className="mt-0.5 size-4 text-[#ff3b30]" />
              <div className="text-sm text-[#ff3b30]">{state.errorMessage}</div>
            </CardContent>
          </Card>
        )}

        {waitingForManifest && (
          <Message from="assistant" className="max-w-full">
            <MessageContent>
              <div className="flex items-center gap-3 text-sm text-[#86868b]">
                <Loader2 className="size-4 animate-spin" />
                Waiting for the manifest from AgentCore…
              </div>
            </MessageContent>
          </Message>
        )}

        {activeCategory && (
          <Message from="assistant" className="max-w-full">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
              <Sparkles className="size-3 text-[#1d1d1f]" />
              {activeCategory.name}
              <StatusPill status={activeCategory.status} />
            </div>
            <MessageContent className="gap-3">
              {activeCategory.tokens ? (
                <div className="prose prose-neutral max-w-none text-sm leading-relaxed text-[#1d1d1f]">
                  <MessageResponse
                    parseIncompleteMarkdown={activeCategory.status === "running"}
                  >
                    {activeCategory.tokens}
                  </MessageResponse>
                  {activeCategory.status === "running" && (
                    <span className="caret text-[#1d1d1f]" aria-hidden />
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2 text-sm text-[#86868b]">
                  <Loader2 className="size-3.5 animate-spin" />
                  Evaluator warming up…
                </div>
              )}

              {activeCategory.summary?.summary && (
                <div className="mt-1 rounded-lg border border-black/[0.08] bg-white/60 p-4">
                  <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#86868b]">
                    Category Summary
                  </div>
                  <div className="prose prose-neutral max-w-none text-sm leading-relaxed text-[#1d1d1f]">
                    <MessageResponse parseIncompleteMarkdown={false}>
                      {activeCategory.summary.summary}
                    </MessageResponse>
                  </div>
                </div>
              )}
            </MessageContent>
          </Message>
        )}

        {state.caseSummary && (
          <CaseSummaryCard
            text={state.caseSummary.text}
            raw={state.caseSummary.raw}
          />
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  )
}

/**
 * Re-exported so callers that want the full CategorySwarmPanel inline
 * (e.g. a fallback view) don't have to reach into ./category-swarm-panel
 * directly.
 */
export { CategorySwarmPanel }
