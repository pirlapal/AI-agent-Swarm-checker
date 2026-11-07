"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft, Loader2, Plus } from "lucide-react"

import { AppDialog } from "@/components/ui/app-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CategoryCard } from "./category-card"
import { useWorkflowEditor } from "./use-workflow-editor"

interface WorkflowEditorProps {
  workflowId?: string
}

export function WorkflowEditor({ workflowId }: WorkflowEditorProps) {
  const router = useRouter()
  const editor = useWorkflowEditor({
    workflowId,
    onSaved: () => router.push("/workflows"),
  })

  if (editor.loadingWorkflow) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-[1100px] items-center justify-center px-6">
        <Loader2 className="size-6 animate-spin text-[#1d1d1f]" />
      </div>
    )
  }

  return (
    <div className="min-h-screen text-[#1d1d1f]">
      <div className="container mx-auto px-4 py-8 max-w-[1100px]">
        {/* Title + back */}
        <div className="flex items-center gap-4 mb-2">
          <Link href="/workflows" aria-label="Back to workflows">
            <Button
              variant="ghost"
              size="sm"
              className="text-[#86868b] hover:bg-black/[0.03]"
            >
              <ArrowLeft className="size-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-semibold text-[#1d1d1f]">
              {editor.isEditMode ? "Edit Workflow" : "Create Workflow"}
            </h1>
            <p className="text-[#86868b]">
              {editor.isEditMode
                ? "Update categories, rules, and reference documents"
                : "Define categories and validation rules for your AI agents"}
            </p>
          </div>
        </div>

        {/* Workflow name */}
        <Card className="glass-card shadow-depth-2 mt-8">
          <CardContent className="p-6">
            <Label
              htmlFor="workflowName"
              className="mb-2 block text-[#1d1d1f] font-medium"
            >
              Workflow Name
            </Label>
            <Input
              id="workflowName"
              placeholder="e.g., Building Permit Review, Site Plan, Zoning Pass 01"
              value={editor.workflowName}
              onChange={(e) => editor.setWorkflowName(e.target.value)}
              className="h-11 bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] placeholder:text-[#86868b]"
            />
          </CardContent>
        </Card>

        {/* Categories */}
        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-[#1d1d1f]">Categories</h2>
              <p className="text-sm text-[#86868b]">
                Group related rules. The swarm spawns one evaluator per category and one sub-evaluator per rule.
              </p>
            </div>
            <Button
              onClick={editor.addCategory}
              size="sm"
              className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all"
            >
              <Plus className="size-4 mr-2" />
              Add Category
            </Button>
          </div>

          {editor.categories.length === 0 ? (
            <Card className="glass-card shadow-depth-2">
              <CardHeader>
                <div className="p-12 text-center">
                  <div className="size-16 rounded-2xl bg-[#1d1d1f]/5 flex items-center justify-center mx-auto mb-4">
                    <Plus className="size-8 text-[#1d1d1f]" />
                  </div>
                  <h3 className="text-lg font-semibold text-[#1d1d1f] mb-2">
                    No categories yet
                  </h3>
                  <p className="text-[#86868b] mb-4 max-w-md mx-auto">
                    Categories group related rules. The swarm spawns one evaluator per category and one sub-evaluator per rule.
                  </p>
                  <Button
                    onClick={editor.addCategory}
                    className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all"
                  >
                    <Plus className="size-4 mr-2" />
                    Add First Category
                  </Button>
                </div>
              </CardHeader>
            </Card>
          ) : (
            <div className="space-y-4">
              {editor.categories.map((category, index) => (
                <CategoryCard
                  key={category.id}
                  category={category}
                  index={index}
                  onChangeName={(name) =>
                    editor.updateCategoryField(category.id, "name", name)
                  }
                  onToggleExpanded={() =>
                    editor.toggleCategoryExpanded(category.id)
                  }
                  onRemove={() => editor.removeCategory(category.id)}
                  onAddRuleInput={() => editor.addRuleInput(category.id)}
                  onUpdateRuleInput={(ruleInputId, field, value) =>
                    editor.updateRuleInput(
                      category.id,
                      ruleInputId,
                      field,
                      value
                    )
                  }
                  onRemoveRuleInput={(ruleInputId) =>
                    editor.removeRuleInput(category.id, ruleInputId)
                  }
                  onSaveRules={() => editor.saveValidationRules(category.id)}
                  onEditSavedRule={(i) => editor.editSavedRule(category.id, i)}
                  onDeleteSavedRule={(i) =>
                    editor.deleteSavedRule(category.id, i)
                  }
                  onFileUpload={(e) => editor.handleFileUpload(category.id, e)}
                  onRemoveFile={(i) => editor.removeFile(category.id, i)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="mt-10 flex items-center justify-between pb-6">
          <Link href="/workflows">
            <Button
              variant="outline"
              className="border-black/[0.08] text-[#1d1d1f] bg-white hover:bg-black/[0.03]"
            >
              Cancel
            </Button>
          </Link>
          <Button
            onClick={editor.handleSaveWorkflow}
            disabled={
              !editor.workflowName.trim() ||
              editor.categories.length === 0 ||
              editor.saving
            }
            size="lg"
            className="bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all disabled:opacity-50"
          >
            {editor.saving && <Loader2 className="size-4 mr-2 animate-spin" />}
            {editor.isEditMode ? "Update Workflow" : "Create Workflow"}
          </Button>
        </div>
      </div>

      <AppDialog
        open={editor.dialog.open}
        onOpenChange={editor.closeDialog}
        title={editor.dialog.title}
        description={editor.dialog.description}
        variant={editor.dialog.variant}
        onConfirm={editor.dialog.onConfirm}
      />
    </div>
  )
}
