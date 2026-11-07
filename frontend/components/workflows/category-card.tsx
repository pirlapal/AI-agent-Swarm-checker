"use client"

import {
  ChevronDown,
  ChevronUp,
  Code,
  FileText,
  Plus,
  Settings,
  Trash2,
  Upload,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RuleInputRow } from "./rule-input-row"
import type { EditorCategory, RuleInput } from "./editor-types"

interface CategoryCardProps {
  category: EditorCategory
  index: number
  onChangeName: (name: string) => void
  onToggleExpanded: () => void
  onRemove: () => void
  onAddRuleInput: () => void
  onUpdateRuleInput: (
    ruleInputId: string,
    field: keyof RuleInput,
    value: string,
  ) => void
  onRemoveRuleInput: (ruleInputId: string) => void
  onSaveRules: () => void
  onEditSavedRule: (index: number) => void
  onDeleteSavedRule: (index: number) => void
  onFileUpload: (event: React.ChangeEvent<HTMLInputElement>) => void
  onRemoveFile: (index: number) => void
}

export function CategoryCard({
  category,
  index,
  onChangeName,
  onToggleExpanded,
  onRemove,
  onAddRuleInput,
  onUpdateRuleInput,
  onRemoveRuleInput,
  onSaveRules,
  onEditSavedRule,
  onDeleteSavedRule,
  onFileUpload,
  onRemoveFile,
}: CategoryCardProps) {
  return (
    <Card className="glass-card shadow-depth-2">
      <CardHeader className="border-b border-black/[0.08] pb-4">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-[#86868b] bg-[#1d1d1f]/5 px-2 py-1 rounded">
            {String(index + 1).padStart(2, "0")}
          </span>
          <Input
            placeholder="Category name (e.g., Zoning Compliance)"
            value={category.name}
            onChange={(e) => onChangeName(e.target.value)}
            className="h-9 flex-1 bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] placeholder:text-[#86868b]"
          />
          <Button
            onClick={onToggleExpanded}
            variant="ghost"
            size="sm"
            aria-label={category.expanded ? "Collapse" : "Expand"}
            className="text-[#86868b] hover:bg-black/[0.03]"
          >
            {category.expanded ? (
              <ChevronUp className="size-4" />
            ) : (
              <ChevronDown className="size-4" />
            )}
          </Button>
          <Button
            onClick={onRemove}
            variant="ghost"
            size="sm"
            aria-label="Remove category"
            className="text-[#ff3b30] hover:bg-[#ff3b30]/10"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </CardHeader>

      {category.expanded && (
        <CardContent className="space-y-6 p-6">
          {/* Rule drafting */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <Label className="text-[#1d1d1f] font-medium">
                Validation Rules
              </Label>
              <Button
                onClick={onAddRuleInput}
                variant="outline"
                size="sm"
                className="border-black/[0.08] text-[#1d1d1f] bg-white hover:bg-black/[0.03]"
              >
                <Plus className="size-4 mr-2" />
                Add Rule
              </Button>
            </div>

            {!category.ruleInputs.length ? (
              <div className="rounded-lg border border-dashed border-black/[0.12] bg-white/60 p-10 text-center">
                <Code className="mx-auto mb-2 size-6 text-[#86868b]" />
                <p className="mb-3 text-sm text-[#86868b]">
                  No rules being drafted. Add one to begin.
                </p>
                <Button
                  onClick={onAddRuleInput}
                  size="sm"
                  className="bg-[#1d1d1f] text-white hover:bg-[#424245] transition-all"
                >
                  <Plus className="size-4 mr-2" />
                  Add First Rule
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {category.ruleInputs.map((ruleInput) => (
                  <RuleInputRow
                    key={ruleInput.id}
                    ruleInput={ruleInput}
                    onChange={(field, value) =>
                      onUpdateRuleInput(ruleInput.id, field, value)
                    }
                    onRemove={() => onRemoveRuleInput(ruleInput.id)}
                  />
                ))}
              </div>
            )}

            {category.ruleInputs.length > 0 && (
              <Button
                onClick={onSaveRules}
                size="sm"
                className="mt-3 w-full bg-[#1d1d1f] text-white hover:bg-[#424245] hover:shadow-depth-2 transition-all"
              >
                Save {category.ruleInputs.length} Rule
                {category.ruleInputs.length !== 1 ? "s" : ""}
              </Button>
            )}
          </div>

          {/* Saved rules table */}
          {category.savedRules.length > 0 && (
            <div>
              <Label className="mb-3 block text-[#1d1d1f] font-medium">
                Saved Rules · {category.savedRules.length}
              </Label>
              <div className="overflow-hidden rounded-lg border border-black/[0.08] bg-white">
                <table className="w-full">
                  <thead className="bg-[#1d1d1f]/5">
                    <tr>
                      <th className="w-28 px-4 py-2 text-left text-xs font-medium text-[#86868b] uppercase tracking-wide">
                        Check ID
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-[#86868b] uppercase tracking-wide">
                        Rule
                      </th>
                      <th className="w-24 px-4 py-2 text-right text-xs font-medium text-[#86868b] uppercase tracking-wide">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/[0.06]">
                    {category.savedRules.map((rule, i) => (
                      <tr key={i} className="hover:bg-[#1d1d1f]/[0.02]">
                        <td className="px-4 py-3 font-mono text-xs text-[#1d1d1f]">
                          {rule.check_id}
                        </td>
                        <td className="px-4 py-3 text-sm text-[#86868b]">
                          {rule.check_item}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              onClick={() => onEditSavedRule(i)}
                              variant="ghost"
                              size="sm"
                              aria-label="Edit rule"
                              className="text-[#86868b] hover:bg-black/[0.03]"
                            >
                              <Settings className="size-4" />
                            </Button>
                            <Button
                              onClick={() => onDeleteSavedRule(i)}
                              variant="ghost"
                              size="sm"
                              aria-label="Delete rule"
                              className="text-[#ff3b30] hover:bg-[#ff3b30]/10"
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* File upload */}
          <div>
            <Label className="mb-2 block text-[#1d1d1f] font-medium">
              Reference Documents
            </Label>
            <div className="rounded-lg border border-dashed border-black/[0.12] bg-white/60 p-6 text-center transition-colors hover:border-[#1d1d1f]/30">
              <input
                type="file"
                multiple
                onChange={onFileUpload}
                className="hidden"
                id={`file-upload-${category.id}`}
              />
              <label
                htmlFor={`file-upload-${category.id}`}
                className="flex cursor-pointer flex-col items-center"
              >
                <Upload className="mb-2 size-6 text-[#1d1d1f]" />
                <span className="text-sm text-[#1d1d1f]">
                  Click to upload files
                </span>
                <span className="text-xs text-[#86868b] mt-1">
                  PDF · DOC · Images
                </span>
              </label>
            </div>
            {category.files.length > 0 && (
              <div className="mt-3 space-y-2">
                {category.files.map((file, i) => (
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
        </CardContent>
      )}
    </Card>
  )
}
