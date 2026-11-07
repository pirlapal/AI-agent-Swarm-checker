"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Bot,
  Clock,
  FileText,
  Loader2,
  Plus,
  Search,
  Settings,
  Trash2,
  Zap,
} from "lucide-react"

import { AppDialog } from "@/components/ui/app-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  deleteWorkflow as deleteWorkflowApi,
  listWorkflows,
  type ApiWorkflow,
} from "@/lib/api"

export default function WorkflowsPage() {
  const router = useRouter()
  const [workflows, setWorkflows] = React.useState<ApiWorkflow[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [searchQuery, setSearchQuery] = React.useState("")
  const [deleteDialog, setDeleteDialog] = React.useState<{
    open: boolean
    workflowId: string | null
  }>({ open: false, workflowId: null })

  const fetchWorkflows = React.useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await listWorkflows()
      setWorkflows(res.items)
    } catch (err: any) {
      console.error("Failed to load workflows:", err)
      setError(err?.message || "Failed to load workflows")
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    fetchWorkflows()
  }, [fetchWorkflows])

  React.useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") fetchWorkflows()
    }
    document.addEventListener("visibilitychange", onVisible)
    return () => document.removeEventListener("visibilitychange", onVisible)
  }, [fetchWorkflows])

  const filteredWorkflows = workflows.filter((w) =>
    !searchQuery ? true : w.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const confirmDeleteWorkflow = async () => {
    if (!deleteDialog.workflowId) return
    try {
      await deleteWorkflowApi(deleteDialog.workflowId)
      setWorkflows((prev) =>
        prev.filter((w) => w.workflow_id !== deleteDialog.workflowId)
      )
    } catch (err) {
      console.error("Failed to delete workflow:", err)
    }
    setDeleteDialog({ open: false, workflowId: null })
  }

  const getCategoryCount = (w: ApiWorkflow) =>
    w.definition?.categories?.length || 0
  const getRuleCount = (w: ApiWorkflow) =>
    (w.definition?.categories || []).reduce(
      (sum, cat) => sum + (cat.rules?.length || 0),
      0
    )
  const formatDate = (ts: number) => new Date(ts * 1000).toLocaleDateString()

  return (
    <div className="min-h-screen text-[#1d1d1f]">
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-[#1d1d1f]">Workflows</h1>
            <p className="text-[#86868b]">
              Manage and monitor your AI agent workflows
            </p>
          </div>
          <Link href="/workflows/create">
            <Button className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all">
              <Plus className="size-4 mr-2" />
              Create Workflow
            </Button>
          </Link>
        </div>

        <div className="flex items-center gap-4 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-[#86868b]" />
            <Input
              placeholder="Search workflows..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] placeholder:text-[#86868b]"
            />
          </div>
        </div>

        <div className="space-y-4">
          {loading ? (
            <Card className="glass-card shadow-depth-2">
              <CardContent className="p-12 text-center">
                <Loader2 className="size-8 text-[#1d1d1f] animate-spin mx-auto mb-4" />
                <p className="text-[#86868b]">Loading workflows...</p>
              </CardContent>
            </Card>
          ) : error ? (
            <Card className="glass-card shadow-depth-2">
              <CardContent className="p-12 text-center">
                <p className="text-[#ff3b30] mb-4">{error}</p>
                <Button
                  onClick={fetchWorkflows}
                  className="bg-[#1d1d1f] text-white hover:bg-[#424245]"
                >
                  Retry
                </Button>
              </CardContent>
            </Card>
          ) : filteredWorkflows.length === 0 ? (
            <Card className="glass-card shadow-depth-2">
              <CardContent className="p-12 text-center">
                <div className="size-16 rounded-2xl bg-[#1d1d1f]/5 flex items-center justify-center mx-auto mb-4">
                  <FileText className="size-8 text-[#1d1d1f]" />
                </div>
                <h3 className="text-lg font-semibold text-[#1d1d1f] mb-2">
                  No workflows yet
                </h3>
                <p className="text-[#86868b] mb-4">
                  Create your first workflow to get started with AI agent automation
                </p>
                <Link href="/workflows/create">
                  <Button className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all">
                    <Plus className="size-4 mr-2" />
                    Create Workflow
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ) : (
            filteredWorkflows.map((workflow) => (
              <Card
                key={workflow.workflow_id}
                className="glass-card shadow-depth-2 hover:shadow-depth-2 transition-all hover-lift"
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2 flex-wrap">
                        <h3 className="text-lg font-semibold text-[#1d1d1f]">
                          {workflow.name}
                        </h3>
                        <Badge
                          variant="outline"
                          className="border-[#34c759]/20 text-[#34c759] bg-[#34c759]/10"
                        >
                          v{workflow.version}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-6 text-sm text-[#86868b] flex-wrap">
                        <div className="flex items-center gap-2">
                          <Bot className="size-4 text-[#1d1d1f]" />
                          {getRuleCount(workflow)} rules
                        </div>
                        <div className="flex items-center gap-2">
                          <FileText className="size-4 text-[#1d1d1f]" />
                          {getCategoryCount(workflow)} categories
                        </div>
                        <div className="flex items-center gap-2">
                          <Clock className="size-4 text-[#1d1d1f]" />
                          Created {formatDate(workflow.created_at)}
                        </div>
                      </div>
                      {workflow.definition?.categories?.length > 0 && (
                        <div className="flex flex-wrap gap-1.5 mt-3">
                          {workflow.definition.categories.map((cat) => (
                            <span
                              key={cat.category_id}
                              className="text-[10px] bg-[#1d1d1f]/5 text-[#1d1d1f] px-2 py-0.5 rounded-full"
                            >
                              {cat.name} ({cat.rules?.length || 0})
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        onClick={() =>
                          router.push(
                            `/workflows/run?trigger=${workflow.workflow_id}`
                          )
                        }
                        size="sm"
                        className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all"
                      >
                        <Zap className="size-3.5 mr-1.5" />
                        Trigger
                      </Button>
                      <Link href={`/workflows/edit/${workflow.workflow_id}`}>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[#86868b] hover:bg-black/[0.03]"
                          aria-label="Edit workflow"
                        >
                          <Settings className="size-4" />
                        </Button>
                      </Link>
                      <Button
                        onClick={() =>
                          setDeleteDialog({
                            open: true,
                            workflowId: workflow.workflow_id,
                          })
                        }
                        variant="ghost"
                        size="sm"
                        className="text-[#ff3b30] hover:bg-[#ff3b30]/10"
                        aria-label="Delete workflow"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>

      <AppDialog
        open={deleteDialog.open}
        onOpenChange={(open) =>
          setDeleteDialog((prev) => ({ ...prev, open }))
        }
        title="Delete Workflow"
        description="Are you sure you want to delete this workflow? This action cannot be undone."
        variant="confirm"
        confirmLabel="Delete"
        onConfirm={confirmDeleteWorkflow}
      />
    </div>
  )
}
