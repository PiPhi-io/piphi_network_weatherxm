from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from piphi_runtime_kit_python import build_event_ingest_response

from ..state import append_runtime_event, commands, refresh_all_entries, refresh_entry, registry

router = APIRouter(tags=["commands"])


@router.post("/command")
async def command(payload: dict[str, Any]):
    command_name = str(payload.get("command") or payload.get("capability_id") or "").strip()
    if not command_name:
        raise HTTPException(status_code=400, detail="Missing command")
    if command_name not in commands:
        raise HTTPException(status_code=400, detail=f"Unsupported command: {command_name}")

    device_id = str(payload.get("device_id") or "demo-device")
    config_id = str(payload.get("config_id") or device_id)
    entry = registry.get(config_id) or {
        "device_id": device_id,
        "config_id": config_id,
    }
    refreshed_state = None
    if command_name == "sync_cloud":
        refreshed_state = await refresh_all_entries()
    elif command_name == "refresh" and registry.get(config_id):
        refreshed_state = await refresh_entry(entry)
    event = append_runtime_event(
        "runtime.command.received",
        entry,
        {
            "command": command_name,
            "device_id": device_id,
            "entity_id": payload.get("entity_id"),
            "args": payload.get("args") or {},
            "refreshed": refreshed_state is not None,
        },
    )
    response = build_event_ingest_response(event)
    response_payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    return {
        **response_payload,
        "ok": True,
        "command": command_name,
        "device_id": device_id,
        "state": refreshed_state,
    }
