"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { History, Plus, Sparkles } from "lucide-react"

import { AppDialog } from "@/components/ui/app-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  getPresignedUrls,
  listWorkflows,
  startCase,
  uploadFileToS3,
  type ApiWorkflow,
} from "@/lib/api"
import {
  loadRunHistory,
  saveRunHistoryEntry,
  type RunHistoryEntry,
} from "@/lib/run-history"
import { RunLiveView } from "@/components/swarm/run-live-view"
import { RunInputPanel } from "@/components/workflows/run-input-panel"

type View = "input" | "live"

interface ActiveRun {
  workflowId: string
  workflowName: string
  caseId: string
  userPrompt?: string
}

export function WorkflowRunShell() {
  const router = useRouter()
  const search = useSearchParams()
  const triggerWorkflowId = search.get("trigger") || ""

  const [view, setView] = React.useState<View>("input")
  const [workflows, setWorkflows] = React.useState<ApiWorkflow[]>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = React.useState<string>("")
  const [prompt, setPrompt] = React.useState("")
  const [files, setFiles] = React.useState<File[]>([])
  const [starting, setStarting] = React.useState(false)
  const [activeRun, setActiveRun] = React.useState<ActiveRun | null>(null)
  const [history, setHistory] = React.useState<RunHistoryEntry[]>([])

  const [dialogState, setDialogState] = React.useState({
    open: false,
    title: "",
    description: "",
    variant: "info" as "info" | "error" | "success",
  })

  const openError = (title: string, description: string) =>
    setDialogState({ open: true, title, description, variant: "error" })

  React.useEffect(() => {
    setHistory(loadRunHistory())
  }, [])

  React.useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await listWorkflows("default", 50)
        if (cancelled) return
        setWorkflows(res.items)
        if (triggerWorkflowId) {
          const exists = res.items.find(
            (w) => w.workflow_id === triggerWorkflowId
          )
          if (exists) setSelectedWorkflowId(triggerWorkflowId)
        }
      } catch (err) {
        console.error("Failed to load workflows:", err)
        if (!cancelled) {
          openError("Error", "Failed to load workflows from backend.")
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [triggerWorkflowId])

  const addFiles = (fileList: FileList | null) => {
    if (!fileList) return
    setFiles((prev) => [...prev, ...Array.from(fileList)])
  }
  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleRun = async () => {
    if (!selectedWorkflowId) return
    const workflow = workflows.find((w) => w.workflow_id === selectedWorkflowId)
    if (!workflow) {
      openError("Error", "Selected workflow is no longer available.")
      return
    }
    setStarting(true)
    try {
      const started = await startCase(selectedWorkflowId, {
        user_prompt: prompt.trim(),
        case_file_names: files.map((f) => f.name),
      })

      if (files.length > 0) {
        const presigned = await getPresignedUrls({
          "workflow-id": selectedWorkflowId,
          "case-id": started.case_id,
          kind: "case",
          "name-of-files": files.map((f) => f.name),
        })
        await Promise.all(
          presigned.map((p, i) => uploadFileToS3(p, files[i]))
        )
      }

      saveRunHistoryEntry({
        id: `${started.workflow_id}-${started.case_id}`,
        caseId: started.case_id,
        workflowId: started.workflow_id,
        workflowName: workflow.name,
        prompt: prompt.trim(),
        caseFiles: files.map((f) => f.name),
        createdAt: Date.now(),
      })
      setHistory(loadRunHistory())

      setActiveRun({
        workflowId: started.workflow_id,
        workflowName: workflow.name,
        caseId: started.case_id,
        userPrompt: prompt.trim(),
      })
      setView("live")
    } catch (err: unknown) {
      console.error("Failed to start case:", err)
      const msg = err instanceof Error ? err.message : "Failed to start case."
      openError("Error", msg)
    } finally {
      setStarting(false)
    }
  }

  const resetToInput = () => {
    setView("input")
    setActiveRun(null)
    setFiles([])
    setPrompt("")
    router.replace("/workflows/run")
  }

  const isLive = view === "live" && activeRun

  return (
    <div className="min-h-screen text-[#1d1d1f]">
      <div
        className={
          isLive
            ? "mx-auto w-full max-w-[1600px] px-4 py-6"
            : "container mx-auto max-w-[1200px] px-4 py-8"
        }
      >
        {!isLive && (
          <div className="mb-8">
            <h1 className="text-3xl font-semibold text-[#1d1d1f]">
              Run Workflow
            </h1>
            <p className="text-[#86868b]">
              Upload a case, nudge the reviewers with a prompt, and watch each
              category light up as its evaluators reason through the rules in
              real time.
            </p>
          </div>
        )}

        <div
          className={
            isLive
              ? "grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)] h-[calc(100svh-120px)]"
              : "grid gap-6 lg:grid-cols-[1fr_280px]"
          }
        >
          {isLive && (
            <aside className="flex min-h-0 flex-col gap-3 overflow-hidden">
              <LiveSidebar
                history={history}
                onPick={(entry) => {
                  setActiveRun({
                    workflowId: entry.workflowId,
                    workflowName: entry.workflowName || "Workflow",
                    caseId: entry.caseId,
                    userPrompt: entry.prompt,
                  })
                  setView("live")
                }}
                onNew={resetToInput}
                activeCaseId={activeRun?.caseId}
              />
            </aside>
          )}

          <div className={isLive ? "min-h-0 min-w-0" : undefined}>
            {view === "input" && (
              <RunInputPanel
                workflows={workflows}
                selectedWorkflowId={selectedWorkflowId}
                onSelectWorkflow={setSelectedWorkflowId}
                prompt={prompt}
                onChangePrompt={setPrompt}
                files={files}
                onAddFiles={addFiles}
                onRemoveFile={removeFile}
                onRun={handleRun}
                starting={starting}
              />
            )}

            {isLive && activeRun && (
              <RunLiveView
                workflowId={activeRun.workflowId}
                workflowName={activeRun.workflowName}
                caseId={activeRun.caseId}
                userPrompt={activeRun.userPrompt}
                onReset={resetToInput}
              />
            )}
          </div>

          {!isLive && <aside className="space-y-4">
            <Card className="glass-card shadow-depth-2">
              <CardContent className="p-5">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-[#1d1d1f]">
                    <History className="size-4" />
                    <span className="text-sm font-medium">Recent Runs</span>
                  </div>
                  <Link href="/workflows/run" onClick={resetToInput}>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label="Start new"
                      className="text-[#86868b] hover:bg-black/[0.03]"
                    >
                      <Plus className="size-4" />
                    </Button>
                  </Link>
                </div>
                {history.length === 0 ? (
                  <p className="text-sm text-[#86868b]">
                    No runs yet. Start one on the left.
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {history.slice(0, 8).map((entry) => (
                      <li key={entry.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setActiveRun({
                              workflowId: entry.workflowId,
                              workflowName: entry.workflowName || "Workflow",
                              caseId: entry.caseId,
                              userPrompt: entry.prompt,
                            })
                            setView("live")
                          }}
                          className="hover-lift block w-full rounded-lg border border-black/[0.08] bg-white p-3 text-left transition-colors hover:border-[#1d1d1f]/20"
                        >
                          <div className="text-[11px] text-[#86868b]">
                            {new Date(entry.createdAt).toLocaleString()}
                          </div>
                          <div className="mt-0.5 truncate text-sm text-[#1d1d1f] font-medium">
                            {entry.workflowName || entry.workflowId.slice(0, 8)}
                          </div>
                          {entry.prompt && (
                            <div className="mt-1 line-clamp-2 text-xs text-[#86868b]">
                              {entry.prompt}
                            </div>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card className="glass-card shadow-depth-1">
              <CardContent className="p-5">
                <div className="mb-1.5 flex items-center gap-2 text-[#1d1d1f]">
                  <Sparkles className="size-4" />
                  <span className="text-sm font-medium">How this works</span>
                </div>
                <p className="text-xs leading-relaxed text-[#86868b]">
                  Your browser opens a pre-signed WebSocket directly to the
                  AgentCore runtime. Tokens, tool calls, and category summaries
                  stream back in real time.
                </p>
              </CardContent>
            </Card>
          </aside>}
        </div>
      </div>

      <AppDialog
        open={dialogState.open}
        onOpenChange={(open) =>
          setDialogState((prev) => ({ ...prev, open }))
        }
        title={dialogState.title}
        description={dialogState.description}
        variant={dialogState.variant}
      />
    </div>
  )
}

interface LiveSidebarProps {
  history: RunHistoryEntry[]
  onPick: (entry: RunHistoryEntry) => void
  onNew: () => void
  activeCaseId?: string
}

function LiveSidebar({
  history,
  onPick,
  onNew,
  activeCaseId,
}: LiveSidebarProps) {
  return (
    <div className="scrollbar-thin flex h-full min-h-0 flex-col overflow-y-auto rounded-xl bg-white/60 p-3 ring-1 ring-black/[0.05]">
      <div className="mb-3 flex items-center justify-between px-1">
        <div className="flex items-center gap-2 text-[#1d1d1f]">
          <History className="size-4" />
          <span className="text-xs font-semibold uppercase tracking-wide">
            Cases
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          aria-label="New run"
          onClick={onNew}
          className="text-[#86868b] hover:bg-black/[0.03]"
        >
          <Plus className="size-4" />
        </Button>
      </div>
      {history.length === 0 ? (
        <p className="px-1 text-xs text-[#86868b]">No runs yet.</p>
      ) : (
        <ul className="space-y-2">
          {history.slice(0, 20).map((entry) => {
            const active = entry.caseId === activeCaseId
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => onPick(entry)}
                  className={`block w-full rounded-lg border p-2.5 text-left transition-colors ${
                    active
                      ? "border-[#1d1d1f] bg-white shadow-depth-1"
                      : "border-black/[0.08] bg-white hover:border-[#1d1d1f]/20"
                  }`}
                >
                  <div className="font-mono text-[10px] uppercase text-[#86868b]">
                    {entry.caseId.slice(0, 8)}
                  </div>
                  <div className="mt-0.5 truncate text-xs font-medium text-[#1d1d1f]">
                    {entry.workflowName || entry.workflowId.slice(0, 8)}
                  </div>
                  <div className="mt-0.5 text-[10px] text-[#86868b]">
                    {new Date(entry.createdAt).toLocaleString()}
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
