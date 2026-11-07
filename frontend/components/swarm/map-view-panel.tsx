"use client"

import * as React from "react"
import { AlertTriangle, Loader2, MapPin } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import type { MapViewState } from "./run-state"

interface MapViewPanelProps {
  mapView: MapViewState
  planId?: string
}

/**
 * Renders the 3D F4Map iframe returned by the orchestrator's
 * `show_property_map` tool. Mirrors the layout of the reference
 * viewer in `ref/code-ref-frontend/.../MapViewerTool.tsx` lines
 * 244-263 -- display-only; no controls, because the address is
 * driven by the agent.
 *
 * States:
 *   - idle:    nothing yet -- the component returns null so the
 *              live view doesn't display empty scaffolding.
 *   - pending: `show_property_map` was invoked; waiting for the
 *              map_view envelope.
 *   - ok:      render the F4Map iframe.
 *   - error:   render an inline error banner with the geocode
 *              failure reason.
 */
export function MapViewPanel({ mapView, planId }: MapViewPanelProps) {
  if (mapView.status === "idle") return null

  return (
    <Card className="glass-card shadow-depth-2 overflow-hidden">
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/[0.06] bg-white/60 px-5 py-3">
          <div className="flex items-center gap-2 text-sm text-[#1d1d1f]">
            <MapPin className="size-4 text-[#86868b]" />
            <span className="font-medium">Site location</span>
            {mapView.address && (
              <span className="text-[#86868b]">· {mapView.address}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {planId && (
              <Badge
                variant="outline"
                className="border-black/[0.08] text-[11px] text-[#1d1d1f] bg-white"
              >
                Plan {planId}
              </Badge>
            )}
            {mapView.status === "pending" && (
              <Badge
                variant="outline"
                className="border-black/[0.08] text-[11px] text-[#86868b] bg-white"
              >
                <Loader2 className="size-3 mr-1 animate-spin" />
                Locating
              </Badge>
            )}
            {mapView.status === "error" && (
              <Badge
                variant="outline"
                className="border-[#ff3b30]/20 bg-[#ff3b30]/10 text-[11px] text-[#ff3b30]"
              >
                <AlertTriangle className="size-3 mr-1" />
                Geocode failed
              </Badge>
            )}
          </div>
        </div>

        <div className="relative h-[420px] w-full">
          {mapView.status === "ok" && mapView.f4mapUrl ? (
            <iframe
              key={mapView.f4mapUrl}
              src={mapView.f4mapUrl}
              title="3D site map"
              className="h-full w-full border-none"
              allowFullScreen
              loading="lazy"
            />
          ) : mapView.status === "error" ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-[#86868b]">
              <AlertTriangle className="size-8 text-[#ff3b30]/80" />
              <p className="max-w-md leading-relaxed">
                Could not locate the property on the map.
                {mapView.address ? (
                  <>
                    {" "}
                    The address extracted from the site plan was{" "}
                    <span className="font-medium text-[#1d1d1f]">
                      {mapView.address}
                    </span>
                    .
                  </>
                ) : (
                  <>
                    {" "}
                    No address was detected on the site plan.
                  </>
                )}
              </p>
              {mapView.error && (
                <p className="max-w-md text-xs text-[#86868b]/80">
                  {mapView.error}
                </p>
              )}
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-[#86868b]">
              <Loader2 className="size-6 animate-spin" />
              <p>Waiting for site plan…</p>
            </div>
          )}
        </div>

        {mapView.status === "ok" && mapView.displayName && (
          <div className="border-t border-black/[0.06] bg-white/60 px-5 py-2 text-xs text-[#86868b]">
            {mapView.displayName}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
