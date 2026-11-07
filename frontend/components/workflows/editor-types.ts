export interface ValidationRule {
  check_id: string
  check_item: string
}

export interface RuleInput {
  id: string
  check_id: string
  check_item: string
}

export interface EditorCategory {
  id: string
  name: string
  ruleInputs: RuleInput[]
  savedRules: ValidationRule[]
  files: File[]
  expanded: boolean
  backendCategoryId?: string
}

export type DialogVariant = "info" | "confirm" | "error" | "success"

export interface DialogState {
  open: boolean
  title: string
  description: string
  variant: DialogVariant
  onConfirm?: () => void
}
