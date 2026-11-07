"use client"

import { Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { RuleInput } from "./editor-types"

interface RuleInputRowProps {
  ruleInput: RuleInput
  onChange: (field: keyof RuleInput, value: string) => void
  onRemove: () => void
}

export function RuleInputRow({
  ruleInput,
  onChange,
  onRemove,
}: RuleInputRowProps) {
  return (
    <div className="rounded-lg border border-black/[0.08] bg-white p-4">
      <div className="grid grid-cols-12 items-start gap-3">
        <div className="col-span-12 sm:col-span-2">
          <Label className="mb-1 block text-xs font-medium text-[#86868b] uppercase tracking-wide">
            Check ID
          </Label>
          <Input
            placeholder="1"
            value={ruleInput.check_id}
            onChange={(e) => onChange("check_id", e.target.value)}
            className="h-9 bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] font-mono text-sm placeholder:text-[#86868b]"
          />
        </div>
        <div className="col-span-12 sm:col-span-9">
          <Label className="mb-1 block text-xs font-medium text-[#86868b] uppercase tracking-wide">
            Rule
          </Label>
          <Textarea
            placeholder="Site plan must depict the entire lot."
            value={ruleInput.check_item}
            onChange={(e) => onChange("check_item", e.target.value)}
            className="min-h-[60px] bg-black/[0.03] border-black/[0.08] text-[#1d1d1f] text-sm placeholder:text-[#86868b]"
          />
        </div>
        <div className="col-span-12 sm:col-span-1 flex h-full items-end justify-end">
          <Button
            onClick={onRemove}
            variant="ghost"
            size="sm"
            aria-label="Remove rule"
            className="text-[#ff3b30] hover:bg-[#ff3b30]/10"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
