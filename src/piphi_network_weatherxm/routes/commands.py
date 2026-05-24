from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from piphi_runtime_kit_python import build_event_ingest_response

from ..state import append_runtime_event, commands, refresh_all_entries, refresh_entry, registry

router = APIRouter(tags=["commands"])

COMMAND_ALIASES = {
    "refresh_readings": "refresh",
    "device.refresh": "refresh",
}
SUPPORTED_CAPABILITIES = {
    "action.refresh",
    "action.sync_cloud",
    "device.refresh",
    "weather.refresh",
    "weather.current",
    "weather.forecast",
}


def _payload_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _structured_error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"ok": False, "error": code, "message": message},
    )


def _target_value(payload: dict[str, Any], key: str) -> str:
    target = _payload_dict(payload.get("target"))
    return str(target.get(key) or "").strip()


def _resolve_command_name(payload: dict[str, Any]) -> str:
    raw_command = str(payload.get("command") or payload.get("capability_id") or "").strip()
    return COMMAND_ALIASES.get(raw_command, raw_command)


def _validate_capabilities(payload: dict[str, Any]) -> None:
    requirements = payload.get("capability_requirements")
    requested = [
        str(item).strip()
        for item in ([payload.get("capability")] + (requirements if isinstance(requirements, list) else []))
        if str(item or "").strip()
    ]
    unsupported = [capability for capability in requested if capability not in SUPPORTED_CAPABILITIES]
    if unsupported:
        _structured_error(
            400,
            "unsupported_capability",
            f"WeatherXM does not support capability '{unsupported[0]}'",
        )


@router.post("/command")
async def command(payload: dict[str, Any]):
    command_name = _resolve_command_name(payload)
    if not command_name:
        _structured_error(400, "missing_command", "Missing command")
    if command_name not in commands:
        _structured_error(400, "unsupported_command", f"Unsupported command: {command_name}")
    _validate_capabilities(payload)

    device_id = str(payload.get("device_id") or _target_value(payload, "device_id") or "demo-device")
    config_id = str(payload.get("config_id") or _target_value(payload, "config_id") or device_id)
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
            "args": payload.get("params") or payload.get("args") or {},
            "target": _payload_dict(payload.get("target")),
            "refreshed": refreshed_state is not None,
        },
    )
    response = build_event_ingest_response(event)
    response_payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    return {
        **response_payload,
        "ok": True,
        "command": command_name,
        "contract_version": payload.get("contract_version"),
        "device_id": device_id,
        "config_id": config_id,
        "target": _payload_dict(payload.get("target")),
        "params": payload.get("params") or payload.get("args") or {},
        "state": refreshed_state,
    }
