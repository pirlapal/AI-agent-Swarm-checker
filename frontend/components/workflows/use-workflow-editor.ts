"use client"

import * as React from "react"

import {
  createWorkflow,
  getPresignedUrls,
  getWorkflow,
  updateWorkflow,
  uploadFileToS3,
  type ApiWorkflow,
} from "@/lib/api"
import type {
  DialogState,
  DialogVariant,
  EditorCategory,
  RuleInput,
  ValidationRule,
} from "./editor-types"

interface UseWorkflowEditorArgs {
  workflowId?: string
  onSaved: () => void
}

export function useWorkflowEditor({ workflowId, onSaved }: UseWorkflowEditorArgs) {
  const isEditMode = Boolean(workflowId)

  const [workflowName, setWorkflowName] = React.useState("")
  const [categories, setCategories] = React.useState<EditorCategory[]>([])
  const [saving, setSaving] = React.useState(false)
  const [loadingWorkflow, setLoadingWorkflow] = React.useState(false)
  const [workflowVersion, setWorkflowVersion] = React.useState<number>(1)

  const [dialog, setDialog] = React.useState<DialogState>({
    open: false,
    title: "",
    description: "",
    variant: "info",
  })

  const showDialog = React.useCallback(
    (
      title: string,
      description: string,
      variant: DialogVariant = "info",
      onConfirm?: () => void,
    ) => {
      setDialog({ open: true, title, description, variant, onConfirm })
    },
    [],
  )

  const closeDialog = React.useCallback((open: boolean) => {
    setDialog((prev) => ({ ...prev, open }))
  }, [])

  // Load workflow in edit mode
  React.useEffect(() => {
    if (!isEditMode || !workflowId) return
    let cancelled = false
    ;(async () => {
      setLoadingWorkflow(true)
      try {
        const wf: ApiWorkflow = await getWorkflow(workflowId)
        if (cancelled) return
        setWorkflowName(wf.name)
        setWorkflowVersion(wf.version)
        const loaded: EditorCategory[] = (wf.definition?.categories || []).map(
          (cat, index) => ({
            id: `loaded_${Date.now()}_${index}`,
            name: cat.name,
            backendCategoryId: cat.category_id,
            ruleInputs: [],
            savedRules: (cat.rules || []).map((r) => ({
              check_id: r.rule_id,
              check_item: r.name,
            })),
            files: [],
            expanded: true,
          }),
        )
        setCategories(loaded)
      } catch (err) {
        console.error("Failed to load workflow:", err)
        showDialog("Error", "Failed to load workflow", "error", onSaved)
      } finally {
        if (!cancelled) setLoadingWorkflow(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workflowId, isEditMode, showDialog, onSaved])

  // Category + rule editing
  const addCategory = () => {
    setCategories((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        name: "",
        ruleInputs: [],
        savedRules: [],
        files: [],
        expanded: true,
      },
    ])
  }

  const updateCategoryField = <K extends keyof EditorCategory>(
    catId: string,
    field: K,
    value: EditorCategory[K],
  ) => {
    setCategories((prev) =>
      prev.map((cat) => (cat.id === catId ? { ...cat, [field]: value } : cat)),
    )
  }

  const toggleCategoryExpanded = (catId: string) => {
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === catId ? { ...cat, expanded: !cat.expanded } : cat,
      ),
    )
  }

  const removeCategory = (catId: string) => {
    setCategories((prev) => prev.filter((cat) => cat.id !== catId))
  }

  const addRuleInput = (categoryId: string) => {
    setCategories((prev) =>
      prev.map((cat) => {
        if (cat.id !== categoryId) return cat
        const nextCheckId = String(cat.savedRules.length + cat.ruleInputs.length + 1)
        return {
          ...cat,
          ruleInputs: [
            ...cat.ruleInputs,
            { id: Date.now().toString(), check_id: nextCheckId, check_item: "" },
          ],
        }
      }),
    )
  }

  const updateRuleInput = (
    categoryId: string,
    ruleInputId: string,
    field: keyof RuleInput,
    value: string,
  ) => {
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              ruleInputs: cat.ruleInputs.map((r) =>
                r.id === ruleInputId ? { ...r, [field]: value } : r,
              ),
            }
          : cat,
      ),
    )
  }

  const removeRuleInput = (categoryId: string, ruleInputId: string) => {
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              ruleInputs: cat.ruleInputs.filter((r) => r.id !== ruleInputId),
            }
          : cat,
      ),
    )
  }

  const saveValidationRules = (categoryId: string) => {
    const category = categories.find((cat) => cat.id === categoryId)
    if (!category || !category.ruleInputs.length) {
      showDialog(
        "Validation Error",
        "Please add at least one rule before saving.",
        "error",
      )
      return
    }
    const empty = category.ruleInputs.filter(
      (r) => !r.check_id.trim() || !r.check_item.trim(),
    )
    if (empty.length > 0) {
      showDialog(
        "Validation Error",
        "Please fill in both Check ID and Rule for all entries.",
        "error",
      )
      return
    }
    const newRules: ValidationRule[] = category.ruleInputs.map((r) => ({
      check_id: r.check_id.trim(),
      check_item: r.check_item.trim(),
    }))
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              savedRules: [...cat.savedRules, ...newRules],
              ruleInputs: [],
            }
          : cat,
      ),
    )
    showDialog(
      "Saved",
      `Saved ${newRules.length} rule${newRules.length !== 1 ? "s" : ""}.`,
      "success",
    )
  }

  const deleteSavedRule = (categoryId: string, ruleIndex: number) => {
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? {
              ...cat,
              savedRules: cat.savedRules.filter((_, i) => i !== ruleIndex),
            }
          : cat,
      ),
    )
  }

  const editSavedRule = (categoryId: string, ruleIndex: number) => {
    setCategories((prev) =>
      prev.map((cat) => {
        if (cat.id !== categoryId) return cat
        const rule = cat.savedRules[ruleIndex]
        if (!rule) return cat
        return {
          ...cat,
          savedRules: cat.savedRules.filter((_, i) => i !== ruleIndex),
          ruleInputs: [
            ...cat.ruleInputs,
            {
              id: Date.now().toString(),
              check_id: rule.check_id,
              check_item: rule.check_item,
            },
          ],
        }
      }),
    )
  }

  const handleFileUpload = (
    catId: string,
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const files = event.target.files
    if (!files) return
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === catId
          ? { ...cat, files: [...cat.files, ...Array.from(files)] }
          : cat,
      ),
    )
    event.target.value = ""
  }

  const removeFile = (categoryId: string, fileIndex: number) => {
    setCategories((prev) =>
      prev.map((cat) =>
        cat.id === categoryId
          ? { ...cat, files: cat.files.filter((_, i) => i !== fileIndex) }
          : cat,
      ),
    )
  }

  const saveWorkflowToApi = async (categoriesToSave: EditorCategory[]) => {
    setSaving(true)
    try {
      const definition = {
        categories: categoriesToSave.map((cat) => ({
          name: cat.name,
          category_id: cat.backendCategoryId,
          rules: cat.savedRules.map((rule) => ({
            name: rule.check_item,
            config: { check_id: rule.check_id },
          })),
        })),
      }

      let savedWorkflowId: string
      if (isEditMode && workflowId) {
        const res = await updateWorkflow(workflowId, {
          version: workflowVersion,
          name: workflowName,
          definition,
        })
        savedWorkflowId = res.workflow_id
        setWorkflowVersion(res.version)
      } else {
        const res = await createWorkflow({ name: workflowName, definition })
        savedWorkflowId = res.workflow_id
      }

      for (const cat of categoriesToSave) {
        if (cat.files.length === 0) continue
        try {
          const presigned = await getPresignedUrls({
            "workflow-id": savedWorkflowId,
            kind: "ref",
            "name-of-files": cat.files.map((f) => f.name),
          })
          await Promise.all(
            presigned.map((p, i) => uploadFileToS3(p, cat.files[i])),
          )
        } catch (uploadErr) {
          console.error("File upload error:", uploadErr)
        }
      }

      showDialog(
        "Saved",
        `Workflow "${workflowName}" ${isEditMode ? "updated" : "created"}.`,
        "success",
        onSaved,
      )
    } catch (err: any) {
      console.error("Failed to save workflow:", err)
      const msg =
        err?.status === 409
          ? "Version conflict — someone else may have edited this workflow. Please reload and try again."
          : err?.message || "Failed to save workflow"
      showDialog("Error", msg, "error")
    } finally {
      setSaving(false)
    }
  }

  const handleSaveWorkflow = () => {
    const invalidCategories = categories.filter((cat) => !cat.name.trim())
    if (invalidCategories.length > 0) {
      showDialog(
        "Validation Error",
        "Please name every category before saving.",
        "error",
      )
      return
    }
    const noRules = categories.filter(
      (cat) => !cat.savedRules.length && !cat.ruleInputs.length,
    )
    if (noRules.length > 0) {
      showDialog(
        "Validation Error",
        "Please add at least one rule to every category.",
        "error",
      )
      return
    }

    const unsaved = categories.filter((cat) => cat.ruleInputs.length > 0)
    if (unsaved.length > 0) {
      showDialog(
        "Unsaved rules",
        `${unsaved.length} categor${
          unsaved.length !== 1 ? "ies" : "y"
        } still have draft rule inputs. They'll be auto-saved. Continue?`,
        "confirm",
        () => {
          let valid = true
          const updated = categories.map((cat) => {
            if (cat.ruleInputs.length === 0) return cat
            const empty = cat.ruleInputs.filter(
              (r) => !r.check_id.trim() || !r.check_item.trim(),
            )
            if (empty.length > 0) {
              showDialog(
                "Validation Error",
                `Category "${cat.name}" has incomplete rules.`,
                "error",
              )
              valid = false
              return cat
            }
            return {
              ...cat,
              savedRules: [
                ...cat.savedRules,
                ...cat.ruleInputs.map((r) => ({
                  check_id: r.check_id.trim(),
                  check_item: r.check_item.trim(),
                })),
              ],
              ruleInputs: [] as RuleInput[],
            }
          })
          if (!valid) return
          setCategories(updated)
          setTimeout(() => saveWorkflowToApi(updated), 100)
        },
      )
      return
    }

    saveWorkflowToApi(categories)
  }

  return {
    isEditMode,
    workflowName,
    setWorkflowName,
    categories,
    saving,
    loadingWorkflow,
    dialog,
    closeDialog,
    addCategory,
    updateCategoryField,
    toggleCategoryExpanded,
    removeCategory,
    addRuleInput,
    updateRuleInput,
    removeRuleInput,
    saveValidationRules,
    deleteSavedRule,
    editSavedRule,
    handleFileUpload,
    removeFile,
    handleSaveWorkflow,
  }
}
