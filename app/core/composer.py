"""Message composer shared across UI components.

Provide a flexible API to compose final message combining raw text
with optional additions (time, window title, SMTC info, idle, hardware)."""

from typing import Optional
from datetime import datetime

from .system import (
    get_cpu_usage,
    get_ram_usage,
    get_gpu_usage,
    get_temperatures,
    get_smtc_info,
    get_idle_seconds,
    format_duration,
    get_active_window_title,
)
from ..hr import get_current_hr  # type: ignore


def compose_full_message(
    raw_text: str,
    wrap_newlines: bool = True,
    include_time: bool = True,
    include_window_title: bool = True,
    include_music: bool = True,
    include_idle: bool = True,
    idle_threshold: int = 60,
    include_cpu: bool = True,
    include_ram: bool = True,
    include_gpu: bool = False,
    include_temp: bool = False,
    include_hr: bool = False,
    max_len: Optional[int] = None,
) -> Optional[str]:
    raw = (raw_text or "").strip()
    if not raw:
        return None
    additions: list[str] = []
    wrap = "\n" if wrap_newlines else " "

    if include_idle:
        idle_sec = get_idle_seconds()
        if idle_sec >= idle_threshold:
            additions.append(f"[已挂机: {format_duration(idle_sec)}]")

    if include_time:
        additions.append(datetime.now().strftime("%H:%M:%S"))

    if include_window_title:
        title = get_active_window_title()
        if title:
            additions.append(title)

    if include_music:
        music = get_smtc_info()
        if music:
            additions.append(music)

    hw_parts: list[str] = []
    if include_cpu:
        cpu = get_cpu_usage()
        if cpu is not None:
            hw_parts.append(f"CPU: {cpu:.0f}%")
    if include_ram:
        ram = get_ram_usage()
        if ram is not None:
            hw_parts.append(f"RAM: {ram:.0f}%")
    if include_gpu:
        gpu = get_gpu_usage()
        if gpu is not None:
            hw_parts.append(f"GPU: {gpu:.0f}%")
    if include_temp:
        temps = {}
        try:
            temps = get_temperatures()
        except Exception:
            temps = {}
        if temps:
            order = ['cpu', 'gpu', 'nvme', 'motherboard']
            name_map = {
                "cpu": "CPU",
                "gpu": "GPU",
                "nvme": "SSD",
                "motherboard": "主板",
            }
            parts: list[str] = []
            for k in order:
                if k in temps:
                    parts.append(
                        f"{name_map.get(k, k.upper())} {temps[k]:.0f}°C"
                    )
            for k, v in temps.items():
                if k not in order:
                    parts.append(f"{name_map.get(k, k.upper())} {v:.0f}°C")
            if parts:
                hw_parts.append(f"温度: {', '.join(parts)}")
    if hw_parts:
        additions.append(f"[{', '.join(hw_parts)}]")

    if include_hr:
        hr = get_current_hr()
        if hr is not None:
            additions.append(f"[HR: {int(hr)}bpm]")

    final = raw
    if additions:
        final = raw + wrap + wrap.join(additions)

    if max_len is not None and len(final) > max_len:
        final = final[: max_len]
    return final

