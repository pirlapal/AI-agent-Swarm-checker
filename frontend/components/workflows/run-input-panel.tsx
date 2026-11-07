"use client"

import * as React from "react"
import { FileText, Loader2, Play, Trash2, Upload } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { ApiWorkflow } from "@/lib/api"

interface Props {
  workflows: ApiWorkflow[]
  selectedWorkflowId: string
  onSelectWorkflow: (id: string) => void
  prompt: string
  onChangePrompt: (value: string) => void
  files: File[]
  onAddFiles: (files: FileList | null) => void
  onRemoveFile: (index: number) => void
  onRun: () => void
  starting: boolean
}

export function RunInputPanel({
  workflows,
  selectedWorkflowId,
  onSelectWorkflow,
  prompt,
  onChangePrompt,
  files,
  onAddFiles,
  onRemoveFile,
  onRun,
  starting,
}: Props) {
  const canRun = Boolean(selectedWorkflowId) && !starting

  return (
    <Card className="glass-card shadow-depth-2">
      <CardContent className="space-y-6 p-6">
        <div>
          <Label className="mb-2 block text-[#1d1d1f] font-medium">
            Workflow
          </Label>
          <Select value={selectedWorkflowId} onValueChange={onSelectWorkflow}>
            <SelectTrigger className="w-full bg-black/[0.03] border-black/[0.08] text-[#1d1d1f]">
              <SelectValue placeholder="Pick a workflow to run" />
            </SelectTrigger>
            <SelectContent>
              {workflows.map((wf) => (
                <SelectItem key={wf.workflow_id} value={wf.workflow_id}>
                  {wf.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label
            htmlFor="prompt"
            className="mb-2 block text-[#1d1d1f] font-medium"
          >
            Prompt
          </Label>
          <Textarea
            id="prompt"
            placeholder="Describe what the swarm should review. Leave blank for default instructions."
            value={prompt}
            onChange={(e) => onChangePrompt(e.target.value)}
            className="min-h-[120px] bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] text-sm placeholder:text-[#86868b]"
          />
        </div>

        <div>
          <Label className="mb-2 block text-[#1d1d1f] font-medium">
            Case Documents
          </Label>
          <div className="rounded-lg border border-dashed border-black/[0.12] bg-white/60 p-6 text-center transition-colors hover:border-[#1d1d1f]/30">
            <input
              type="file"
              multiple
              accept="application/pdf,.pdf,image/*,.doc,.docx"
              onChange={(e) => {
                onAddFiles(e.target.files)
                e.target.value = ""
              }}
              className="hidden"
              id="case-file-upload"
            />
            <label
              htmlFor="case-file-upload"
              className="flex cursor-pointer flex-col items-center"
            >
              <Upload className="mb-2 size-6 text-[#1d1d1f]" />
              <span className="text-sm text-[#1d1d1f]">
                Upload case documents
              </span>
              <span className="text-xs text-[#86868b] mt-1">
                PDF · DOC · Images
              </span>
            </label>
          </div>
          {files.length > 0 && (
            <div className="mt-3 space-y-2">
              {files.map((file, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-black/[0.08] bg-white p-3"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="size-4 text-[#1d1d1f] shrink-0" />
                    <span className="text-sm text-[#1d1d1f] truncate">
                      {file.name}
                    </span>
                    <span className="text-xs text-[#86868b] shrink-0">
                      {(file.size / 1024).toFixed(1)} KB
                    </span>
                  </div>
                  <Button
                    onClick={() => onRemoveFile(i)}
                    variant="ghost"
                    size="sm"
                    aria-label="Remove file"
                    className="text-[#ff3b30] hover:bg-[#ff3b30]/10 shrink-0"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end">
          <Button
            onClick={onRun}
            disabled={!canRun}
            size="lg"
            className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all disabled:opacity-50"
          >
            {starting ? (
              <Loader2 className="size-4 mr-2 animate-spin" />
            ) : (
              <Play className="size-4 mr-2" />
            )}
            {starting ? "Starting..." : "Run Swarm"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
