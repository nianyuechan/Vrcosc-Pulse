"""System info helpers with graceful fallback.

Priority order by platform:
- Windows 与通用平台：优先使用 `vrchatmsg.core`（若存在），否则回退到 `psutil`、`GPUtil`、`pynvml` 等近似值；
- Linux：从 `/sys/class/hwmon` 读取温度信息（无需 sudo/第三方库）。

注：已移除对 `LibreHardwareMonitorLib.dll` 的依赖与集成。
"""

from typing import Optional, Dict, Any, List, Tuple, Callable
import sys
import os
import glob
import time
import logging
import warnings

# pynvml 包已弃用（官方建议改用 nvidia-ml-py），屏蔽其 FutureWarning，避免每次启动刷屏
warnings.filterwarnings("ignore", message="The pynvml package is deprecated.*", category=FutureWarning)

try:
    from vrchatmsg.core import system as core_system  # type: ignore
    from vrchatmsg.core import window as core_window  # type: ignore
    from vrchatmsg.core import utils as core_utils  # type: ignore
    HAS_VRCHATMSG = True
except Exception:
    core_system = None  # type: ignore
    core_window = None  # type: ignore
    core_utils = None  # type: ignore
    HAS_VRCHATMSG = False


logger = logging.getLogger(__name__)

# 统一健康状态与缓存
_HEALTH: Dict[str, Dict[str, Any]] = {}
_CACHE: Dict[str, Any] = {}

TTL_CPU = 1.0
TTL_RAM = 1.0
TTL_GPU = 2.0
TTL_TEMPS = 5.0
TTL_WINDOW = 0.5
TTL_IDLE = 1.0
TTL_SMTC = 2.0

def _record_health(metric: str, ok: bool, source: Optional[str] = None, err: Optional[BaseException] = None) -> None:
    h = _HEALTH.setdefault(metric, {})
    h["ok"] = ok
    h["last_time"] = time.time()
    if source is not None:
        h["source"] = source
    if err is not None:
        h["last_error"] = f"{type(err).__name__}: {err}"

def _set_source(metric: str, source: str) -> None:
    h = _HEALTH.setdefault(metric, {})
    h["source"] = source

def safe_metric(metric: str, default: Any = None) -> Callable:
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                ok = result is not None
                _record_health(metric, ok)
                return result if ok else default
            except BaseException as e:
                logger.exception("system.%s 调用异常", metric)
                _record_health(metric, False, err=e)
                return default
        return wrapper
    return decorator

def _cached_call(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    now = time.time()
    entry = _CACHE.get(key)
    if isinstance(entry, tuple) and len(entry) == 2:
        ts, val = entry
        if now - ts <= ttl:
            return val
    val = producer()
    _CACHE[key] = (now, val)
    return val

def clear_system_cache() -> None:
    _CACHE.clear()

def health_check() -> Dict[str, Any]:
    summary = {k: dict(v) for k, v in _HEALTH.items()}
    summary["overall_ok"] = all(v.get("ok", False) for v in summary.values()) if summary else True
    return summary

@safe_metric("cpu", default=None)
def get_cpu_usage() -> Optional[float]:
    def _produce():
        if HAS_VRCHATMSG and core_system:
            try:
                _set_source("cpu", "vrchatmsg.core")
                return float(core_system.get_cpu_usage())
            except Exception:
                pass
        try:
            import psutil  # type: ignore
            _set_source("cpu", "psutil")
            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return None
    return _cached_call("cpu", TTL_CPU, _produce)


@safe_metric("ram", default=None)
def get_ram_usage() -> Optional[float]:
    def _produce():
        if HAS_VRCHATMSG and core_system:
            try:
                _set_source("ram", "vrchatmsg.core")
                return float(core_system.get_ram_usage())
            except Exception:
                pass
        try:
            import psutil  # type: ignore
            _set_source("ram", "psutil")
            return float(psutil.virtual_memory().percent)
        except Exception:
            return None
    return _cached_call("ram", TTL_RAM, _produce)


@safe_metric("gpu", default=None)
def get_gpu_usage() -> Optional[float]:
    def _produce():
        if HAS_VRCHATMSG and core_system:
            try:
                _set_source("gpu", "vrchatmsg.core")
                return float(core_system.get_gpu_usage())
            except Exception:
                pass
        # GPUtil 内部用 Popen 启动 nvidia-smi 且不传 CREATE_NO_WINDOW，
        # 在 Windows 上会让控制台窗口反复弹出/关闭，因此 Windows 直接跳过，
        # 改由下面的 pynvml 读取（不产生子进程窗口）。
        if not sys.platform.startswith('win'):
            try:
                import GPUtil  # type: ignore
                gpus = GPUtil.getGPUs()
                if gpus:
                    _set_source("gpu", "GPUtil")
                    return float(gpus[0].load * 100.0)
            except Exception:
                pass
        # NVIDIA via pynvml
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                _set_source("gpu", "pynvml")
                return float(util.gpu)
            finally:
                try:
                    pynvml.nvmlShutdown()
                except Exception:
                    pass
        except Exception:
            pass
        return None
    return _cached_call("gpu", TTL_GPU, _produce)


# ---- Linux hwmon temperatures (optional) ----
def get_hwmon_temperatures() -> Dict[str, float]:
    """Read temperatures from `/sys/class/hwmon` on Linux.

    Returns a mapping like {"cpu": 54.0, "gpu": 65.0, "nvme": 42.0, "motherboard": 38.0}.
    Values are best-effort; keys are heuristically mapped by device name.
    """
    temps: Dict[str, float] = {}
    if sys.platform.startswith('linux'):
        try:
            hwmons = glob.glob('/sys/class/hwmon/hwmon*')
            for d in hwmons:
                try:
                    with open(os.path.join(d, 'name'), 'r') as f:
                        name = f.read().strip().lower()
                except Exception:
                    name = ''
                # Map name to category
                if 'coretemp' in name or 'cpu' in name:
                    key = 'cpu'
                elif 'amdgpu' in name or 'radeon' in name or 'nvidia' in name:
                    key = 'gpu'
                elif 'nvme' in name:
                    key = 'nvme'
                elif 'acpitz' in name or 'pch' in name or 'atk0110' in name or 'it' in name:
                    key = 'motherboard'
                else:
                    key = name or 'unknown'
                # Read temp*_input
                for tfile in glob.glob(os.path.join(d, 'temp*_input')):
                    try:
                        with open(tfile, 'r') as tf:
                            milli = int(tf.read().strip())
                            val = milli / 1000.0
                            # choose max per key to represent hottest
                            temps[key] = max(val, temps.get(key, val))
                    except Exception:
                        continue
        except Exception:
            pass
    return temps


@safe_metric("temps", default={})
def get_temperatures() -> Dict[str, float]:
    def _produce():
        temps: Dict[str, float] = {}
        # Windows fallback: psutil sensors and NVIDIA NVML GPU temperature
        try:
            if sys.platform.startswith('win'):
                # psutil sensors (may be sparse on Windows)
                try:
                    import psutil  # type: ignore
                    sens = getattr(psutil, 'sensors_temperatures', None)
                    if callable(sens):
                        data = sens()
                        # Consolidate known keys
                        for key, entries in (data or {}).items():
                            if not entries:
                                continue
                            # Choose max reading for category
                            max_val = None
                            for e in entries:
                                try:
                                    val = float(getattr(e, 'current', None))
                                except Exception:
                                    val = None
                                if val is None:
                                    continue
                                max_val = val if max_val is None else max(max_val, val)
                            if max_val is None:
                                continue
                            lowkey = key.lower()
                            if 'core' in lowkey or 'cpu' in lowkey:
                                temps['cpu'] = max_val
                            elif 'amdgpu' in lowkey or 'radeon' in lowkey or 'nvidia' in lowkey or 'gpu' in lowkey:
                                temps['gpu'] = max_val
                            elif 'nvme' in lowkey or 'ssd' in lowkey:
                                temps['nvme'] = max_val
                            elif 'acpi' in lowkey or 'pch' in lowkey:
                                temps['motherboard'] = max_val
                    _set_source("temps", "psutil")
                except Exception:
                    pass
                # NVIDIA NVML GPU temperature
                try:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    try:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        from pynvml import NVML_TEMPERATURE_GPU  # type: ignore
                        t = pynvml.nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
                        temps['gpu'] = float(t)
                        _set_source("temps", "pynvml")
                    finally:
                        try:
                            pynvml.nvmlShutdown()
                        except Exception:
                            pass
                except Exception:
                    pass
                return temps
        except Exception:
            pass
        # Linux via hwmon
        try:
            if sys.platform.startswith('linux'):
                _set_source("temps", "linux-hwmon")
                return get_hwmon_temperatures()
        except Exception:
            pass
        return temps
    return _cached_call("temps", TTL_TEMPS, _produce)


@safe_metric("smtc", default=None)
def get_smtc_info() -> Optional[str]:
    def _produce():
        if HAS_VRCHATMSG and core_system:
            try:
                _set_source("smtc", "vrchatmsg.core")
                return str(core_system.get_smtc_info())
            except Exception:
                pass
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as SMTCManager,  # type: ignore
            )
        except Exception:
            return None
        try:
            manager = SMTCManager.RequestAsync().get()
            session = manager.GetCurrentSession()
            if not session:
                return None
            props = session.TryGetMediaPropertiesAsync().get()
            title = props.Title or ""
            artist = ", ".join(list(props.Artist)) if hasattr(props, "Artist") else ""
            _set_source("smtc", "winsdk")
            if title and artist:
                return f"♪ {artist} - {title}"
            if title:
                return f"♪ {title}"
        except Exception:
            return None
        return None
    return _cached_call("smtc", TTL_SMTC, _produce)


@safe_metric("window", default=None)
def get_active_window_title() -> Optional[str]:
    def _produce():
        if HAS_VRCHATMSG and core_window:
            try:
                _set_source("window", "vrchatmsg.core")
                return str(core_window.get_active_window_title())
            except Exception:
                pass
        try:
            import win32gui  # type: ignore
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            title = (title or "").strip()
            _set_source("window", "win32gui")
            return title or None
        except Exception:
            return None
    return _cached_call("window", TTL_WINDOW, _produce)


@safe_metric("idle", default=0)
def get_idle_seconds() -> int:
    def _produce():
        if HAS_VRCHATMSG and core_utils:
            try:
                _set_source("idle", "vrchatmsg.core")
                return int(core_utils.get_idle_seconds())
            except Exception:
                pass
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                tick = ctypes.windll.kernel32.GetTickCount()
                elapsed = tick - lii.dwTime
                _set_source("idle", "win32")
                return int(elapsed / 1000)
        except Exception:
            pass
        return 0
    return _cached_call("idle", TTL_IDLE, _produce)


def format_duration(seconds: int) -> str:
    try:
        if HAS_VRCHATMSG and core_utils:
            return str(core_utils.format_duration(seconds))
    except Exception:
        pass
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m}m{s}s"
    return f"{m}m{s}s"
