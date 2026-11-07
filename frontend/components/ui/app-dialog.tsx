"use client"

import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type Variant = "info" | "confirm" | "error" | "success"

interface AppDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  variant?: Variant
  confirmLabel?: string
  cancelLabel?: string
  onConfirm?: () => void
}

/**
 * Lightweight wrapper that maps the ref `AppDialog` surface onto the
 * project's `Dialog` primitive. Keeps the same API the ported pages use:
 *
 *   <AppDialog open title description variant onConfirm onOpenChange />
 */
export function AppDialog({
  open,
  onOpenChange,
  title,
  description,
  variant = "info",
  confirmLabel = "OK",
  cancelLabel = "Cancel",
  onConfirm,
}: AppDialogProps) {
  const isConfirm = variant === "confirm"
  const isError = variant === "error"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          {isConfirm && (
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              className="font-mono text-[11px] uppercase tracking-label"
            >
              {cancelLabel}
            </Button>
          )}
          <Button
            variant={isError ? "destructive" : "default"}
            onClick={() => {
              onConfirm?.()
              onOpenChange(false)
            }}
            className="font-mono text-[11px] uppercase tracking-label"
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
