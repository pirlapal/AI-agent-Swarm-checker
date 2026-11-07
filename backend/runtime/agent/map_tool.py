"""Property-map tool for the case orchestrator.

Exposes ``show_property_map(address, zoom)`` as an orchestrator-side
tool. The agent is expected to call it EXACTLY ONCE per case, after
extracting the property address from the site-plan PDF (see the
orchestrator system prompt). The tool:

1. Geocodes the address via Nominatim
   (`https://nominatim.openstreetmap.org/search`).
2. Builds an F4Map URL matching the reference frontend
   (`MapViewerTool.tsx`):
   ``https://demo.f4map.com/#camera.theta=0.9&camera.phi=0.9&lat=..&lon=..&zoom=..``.
3. Returns a JSON envelope of the form::

       {
         "type": "map_view",
         "workflow_id": "...",
         "case_id": "...",
         "plan_id": "138-24_1",
         "address": "<input>",
         "resolved": {"lat": ..., "lon": ..., "display_name": "..."},
         "zoom": 18,
         "f4map_url": "https://demo.f4map.com/#..."
       }

   which the streaming layer surfaces to the WebSocket client as a
   ``map_view`` event. The frontend renders an F4Map iframe from
   ``f4map_url``.

The tool NEVER raises -- any failure (network error, empty geocode
result, rate-limit response) produces a ``{"type": "map_view",
"status": "error", ...}`` envelope so the orchestrator can keep going
without the whole run collapsing.

Nominatim usage policy
----------------------
Nominatim requires a descriptive ``User-Agent`` and caps unauthenticated
usage at ~1 request/second. This tool is invoked once per case so we
stay well within the limits; the ``User-Agent`` can be customised via
the ``SWARM_NOMINATIM_USER_AGENT`` env var.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("swarm-agentcore-map-tool")
logger.setLevel(logging.INFO)


_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_F4MAP_URL_TEMPLATE = (
    "https://demo.f4map.com/#camera.theta=0.9&camera.phi=0.9"
    "&lat={lat}&lon={lon}&zoom={zoom}"
)
_DEFAULT_UA = "swarm-agentcore/1.0 (compliance-review; contact: ops@example.com)"


def _user_agent() -> str:
    return os.environ.get("SWARM_NOMINATIM_USER_AGENT", _DEFAULT_UA)


def _geocode(address: str, timeout_s: float = 10.0) -> Optional[Dict[str, Any]]:
    """Call Nominatim and return ``{lat, lon, display_name}`` or ``None``.

    Raises only if ``httpx`` itself blows up in a way we can't classify;
    the caller still wraps the call so even that surfaces as a
    structured error envelope.
    """
    params = {"format": "json", "q": address, "limit": 1}
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    resp = httpx.get(
        _NOMINATIM_URL, params=params, headers=headers, timeout=timeout_s
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    try:
        lat = float(first["lat"])
        lon = float(first["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "lat": lat,
        "lon": lon,
        "display_name": str(first.get("display_name") or ""),
    }


def _clamp_zoom(raw: Any) -> float:
    try:
        z = float(raw)
    except (TypeError, ValueError):
        return 18.0
    if z < 1.0:
        return 1.0
    if z > 20.0:
        return 20.0
    return z


def build_show_property_map_tool(
    *,
    workflow_id: str,
    case_id: str,
    plan_id: str,
):
    """Build the orchestrator-side ``show_property_map`` tool.

    ``workflow_id`` / ``case_id`` / ``plan_id`` are baked into the
    returned envelope so the streaming layer and frontend can associate
    the event with the correct run without re-parsing.
    """

    _wf = workflow_id
    _case = case_id
    _plan = plan_id

    @tool
    def show_property_map(address: str, zoom: float = 18) -> str:
        """Geocode an address and return a 3D map URL for the frontend.

        Call this EXACTLY ONCE per case, AFTER you have extracted the
        property's street address from the site-plan PDF via
        ``analyze_pdf``. The tool geocodes the address using the free
        OpenStreetMap Nominatim service and returns an F4Map URL the
        frontend will render in an iframe.

        Args:
            address: Street address as a single line, e.g.
                ``"123 Main St, Scottsdale, AZ"``. Pass the extracted
                text verbatim; do NOT invent or edit the address.
            zoom: Optional F4Map zoom level (1-20, default 18 -- tight
                zoom that shows the building footprint).

        Returns a JSON envelope the streaming layer forwards to the
        WebSocket client as a ``map_view`` event. The envelope ALWAYS
        has ``type = "map_view"``. On success it includes ``resolved``
        (lat/lon/display_name) and ``f4map_url``; on failure it includes
        ``status = "error"`` and an ``error`` message -- the orchestrator
        should note the failure and continue with the case review.
        """
        clean = (address or "").strip()
        z = _clamp_zoom(zoom)

        base: Dict[str, Any] = {
            "type": "map_view",
            "workflow_id": _wf,
            "case_id": _case,
            "plan_id": _plan,
            "address": clean,
            "zoom": z,
        }

        if not clean:
            base["status"] = "error"
            base["error"] = "Empty address provided."
            return json.dumps(base)

        try:
            resolved = _geocode(clean)
        except httpx.HTTPError as exc:
            logger.warning(
                f"[show_property_map] geocode http error address={clean!r}: {exc}"
            )
            base["status"] = "error"
            base["error"] = f"Geocoding HTTP error: {exc}"
            return json.dumps(base)
        except Exception as exc:  # noqa: BLE001 - surface anything else
            logger.warning(
                f"[show_property_map] geocode failed address={clean!r}: {exc}"
            )
            base["status"] = "error"
            base["error"] = f"Geocoding failed: {exc}"
            return json.dumps(base)

        if not resolved:
            base["status"] = "error"
            base["error"] = (
                "No geocoding result for this address. "
                "Nominatim returned an empty match list."
            )
            return json.dumps(base)

        f4_url = _F4MAP_URL_TEMPLATE.format(
            lat=resolved["lat"], lon=resolved["lon"], zoom=z
        )
        base["status"] = "ok"
        base["resolved"] = resolved
        base["f4map_url"] = f4_url
        logger.info(
            f"[show_property_map] ok plan={_plan} lat={resolved['lat']} "
            f"lon={resolved['lon']} zoom={z}"
        )
        return json.dumps(base)

    return show_property_map


__all__ = ["build_show_property_map_tool"]
