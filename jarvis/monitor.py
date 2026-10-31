"""Olhos do Jarvis sobre o computador onde ele roda."""
import platform
from datetime import datetime

import psutil

DISK_ALERT = 90
MEM_ALERT = 90
CPU_ALERT = 95
BATTERY_ALERT = 15


def snapshot() -> dict:
    disk = psutil.disk_usage("/")
    mem = psutil.virtual_memory()
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    procs = sorted(
        psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
        key=lambda p: p.info.get("memory_percent") or 0,
        reverse=True,
    )[:5]
    return {
        "host": platform.node(),
        "time": datetime.now().isoformat(timespec="minutes"),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "mem_percent": mem.percent,
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / 1e9, 1),
        "battery_percent": battery.percent if battery else None,
        "plugged": battery.power_plugged if battery else None,
        "uptime_hours": round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1),
        "top_processes": [
            {"name": p.info["name"], "mem_percent": round(p.info.get("memory_percent") or 0, 1)} for p in procs
        ],
    }


def alerts(snap: dict) -> list[str]:
    out = []
    if snap["disk_percent"] >= DISK_ALERT:
        out.append(f"Disco quase cheio: {snap['disk_percent']}% ({snap['disk_free_gb']} GB livres)")
    if snap["mem_percent"] >= MEM_ALERT:
        out.append(f"Memória RAM em {snap['mem_percent']}%")
    if snap["cpu_percent"] >= CPU_ALERT:
        out.append(f"CPU em {snap['cpu_percent']}%")
    if snap["battery_percent"] is not None and snap["battery_percent"] <= BATTERY_ALERT and not snap["plugged"]:
        out.append(f"Bateria em {snap['battery_percent']}% e fora da tomada")
    return out
