"""
心率模块（BLE）— 可作为服务集成到 Qt 应用。

改造要点：
- 保留原始扫描/订阅逻辑，但封装为可在后台线程运行的服务。
- 提供 `HeartRateMonitor` 类：start/stop、最新 BPM、状态文本。
- 在 bleak 不可用或非 Windows 环境下优雅失效。
"""

import asyncio
import threading
from typing import Optional

try:
    from bleak import BleakScanner, BleakClient, BleakError  # type: ignore
    _BLEAK_AVAILABLE = True
except Exception:
    BleakScanner = None  # type: ignore
    BleakClient = None  # type: ignore
    BleakError = Exception  # type: ignore
    _BLEAK_AVAILABLE = False


# 标准 BLE UUID（16-bit 转换为 128-bit UUID 形式）
HRS_UUID = "0000180d-0000-1000-8000-00805f9b34fb"  # Heart Rate Service
HRM_UUID = "00002a37-0000-1000-8000-00805f9b34fb"  # Heart Rate Measurement characteristic


def parse_heart_rate_measurement(data: bytes) -> int:
    if not data:
        raise ValueError("空的心率数据")
    flag = data[0]
    offset = 1
    if flag & 0x01:  # uint16
        if len(data) < offset + 2:
            raise ValueError("心率 uint16 数据长度不足")
        heart_rate = int(data[offset] | (data[offset + 1] << 8))
    else:  # uint8
        if len(data) < offset + 1:
            raise ValueError("心率 uint8 数据长度不足")
        heart_rate = int(data[offset])
    return heart_rate


async def _find_heart_rate_device():
    devices = await BleakScanner.discover()  # type: ignore
    mi_band_candidates = [d for d in devices if (getattr(d, "name", "") or "").startswith("Xiaomi Smart Band 9")]
    if not mi_band_candidates:
        return None

    def has_adv_hrs(dev) -> bool:
        md = getattr(dev, "metadata", {}) or {}
        uuids = md.get("uuids", []) or md.get("ServiceUUIDs", []) or []
        return bool(uuids) and (HRS_UUID.lower() in [str(u).lower() for u in uuids])

    with_hrs = [d for d in mi_band_candidates if has_adv_hrs(d)]
    if with_hrs:
        return with_hrs[0]
    return sorted(mi_band_candidates, key=lambda d: getattr(d, "rssi", -999), reverse=True)[0]


async def _scan_devices_async(timeout: float) -> list[dict]:
    """扫描附近所有可发现的蓝牙设备（async 内部实现）。"""
    devices = await BleakScanner.discover(timeout=timeout)  # type: ignore
    result: list[dict] = []
    for d in devices:
        result.append({
            "address": getattr(d, "address", "") or "",
            "name": getattr(d, "name", "") or "(未命名)",
            "rssi": getattr(d, "rssi", None),
        })
    return result


def scan_devices(timeout: float = 8.0) -> list[dict]:
    """扫描附近蓝牙设备（阻塞调用，应在后台线程执行）。

    返回 [{"address", "name", "rssi"}]；bleak 不可用或扫描失败时返回空列表。
    """
    if not _BLEAK_AVAILABLE:
        return []
    try:
        import asyncio as _asyncio
        try:
            _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass
        return _asyncio.run(_scan_devices_async(timeout))
    except Exception:
        return []


class HeartRateMonitor:
    """后台心率服务（BLE），在独立线程运行 asyncio 循环。"""
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        # 使用事件替代易出竞态的布尔标志
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_bpm: Optional[int] = None
        self._status: str = "未启用"
        # 会话内记住最近一次连接成功的设备地址；不写入磁盘，
        # 因此下次打开应用时仍会重新扫描选择设备
        self._last_device_address: Optional[str] = None
        # 记录最近一次 BPM 更新时间（单调时间），便于一致性读取
        self._last_bpm_ts: float = 0.0

    def start(self) -> None:
        if not _BLEAK_AVAILABLE:
            with self._lock:
                self._status = "bleak 不可用"
            return
        t = self._thread
        if t is not None and t.is_alive():
            if not self._stop_event.is_set():
                # 已在正常运行
                return
            # 停止中：等旧线程退出，避免 clear() 之后同时存在两条 BLE 循环线程
            try:
                t.join(timeout=2.0)
            except Exception:
                pass
            if t.is_alive():
                # 旧线程卡在 connect 等阻塞调用中：不启动新线程，保持可观测状态
                with self._lock:
                    self._status = "正在停止…"
                return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="HeartRateMonitor", daemon=True)
        self._thread.start()

    def stop(self, join_timeout: float = 1.0) -> None:
        """请求停止后台 BLE 循环。

        `join_timeout` 限制等待时间：调用方通常在 Qt 主线程（取消勾选心率、
        关闭窗口），过长会冻住界面。即使线程没能在超时内退出，也保留 `_thread`
        引用，这样后续 `start()` 会先等它结束，不会起第二条线程去抢同一个设备。
        """
        self._stop_event.set()
        t = self._thread
        if t is not None and t.is_alive():
            try:
                t.join(timeout=max(0.0, float(join_timeout)))
            except Exception:
                pass
        if t is not None and t.is_alive():
            self._thread = t
        else:
            self._thread = None
        with self._lock:
            self._status = "未启用"

    def connect_to(self, address: str) -> None:
        """连接指定蓝牙设备地址。

        设置优先重连地址并启动后台循环；循环会立即尝试连接该设备，
        成功后通过标准通知流程持续接收心率数据。
        """
        address = str(address or "").strip()
        if not address:
            return
        with self._lock:
            self._last_device_address = address
            self._status = f"连接 {address} …"
        self.start()

    def get_last_bpm(self) -> Optional[int]:
        with self._lock:
            return self._last_bpm

    def get_status_text(self) -> str:
        with self._lock:
            return self._status

    def get_snapshot(self) -> tuple[Optional[int], str, float]:
        """一次性读取最新 BPM、状态文本与数据年龄（秒），避免跨次读取不一致。

        返回 (bpm, status, age_seconds)，其中 age_seconds 为自最后一次 BPM 更新以来的秒数。
        """
        with self._lock:
            bpm = self._last_bpm
            status = self._status
            # 计算年龄：如果未更新过则返回正无穷以表示“未知”
            try:
                import time as _t
                now = _t.monotonic()
                age = (now - self._last_bpm_ts) if self._last_bpm_ts > 0.0 else float("inf")
            except Exception:
                age = float("inf")
            return bpm, status, age

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main(loop))
        except Exception:
            pass
        finally:
            try:
                loop.stop()
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass

    async def _main(self, loop: asyncio.AbstractEventLoop) -> None:
        last_device = None
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    remembered = self._last_device_address
                if remembered:
                    with self._lock:
                        self._status = f"重连上次设备 {remembered}…"
                    session_ok = await self._handle_device(remembered, loop)
                    if session_ok:
                        continue
                with self._lock:
                    self._status = "扫描设备…"
                device = await _find_heart_rate_device()
                if device:
                    last_device = device
                target = device or last_device
                if not target:
                    await asyncio.sleep(2.0)
                    continue
                await self._handle_device(target, loop)
            except Exception:
                await asyncio.sleep(2.0)

    async def _handle_device(self, device, loop: asyncio.AbstractEventLoop) -> bool:
        client = BleakClient(device)  # type: ignore
        connected = False
        for attempt in range(3):
            if self._stop_event.is_set():
                return False
            try:
                with self._lock:
                    self._status = f"连接中…(尝试 {attempt + 1}/3)"
                await client.connect(timeout=15.0)
                if client.is_connected:
                    connected = True
                    break
            except Exception:
                await asyncio.sleep(0.5 * (attempt + 1))
        if not connected:
            with self._lock:
                self._status = "连接失败"
            return False

        # 连接成功后记住设备地址，停止后重启用同一地址优先重连
        with self._lock:
            addr = getattr(client, "address", None) or getattr(device, "address", None)
            if addr:
                self._last_device_address = str(addr)

        with self._lock:
            self._status = "已连接"

        last_notify_ts = loop.time()

        def notification_handler(_uuid: str, data: bytearray):
            nonlocal last_notify_ts
            try:
                bpm = parse_heart_rate_measurement(data)
                with self._lock:
                    self._last_bpm = bpm
                    # 使用单调时间戳记录更新时刻，供快照年龄计算
                    try:
                        import time as _t
                        self._last_bpm_ts = _t.monotonic()
                    except Exception:
                        self._last_bpm_ts = 0.0
                last_notify_ts = loop.time()
            except Exception:
                pass

        await asyncio.sleep(0.5)
        try:
            await client.start_notify(HRM_UUID, notification_handler)
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            with self._lock:
                self._status = "订阅失败"
            return False

        try:
            inactivity_threshold = 10.0
            while (not self._stop_event.is_set()) and client.is_connected:
                await asyncio.sleep(1.0)
                now = loop.time()
                if now - last_notify_ts > inactivity_threshold:
                    try:
                        await client.stop_notify(HRM_UUID)
                    except Exception:
                        pass
                    try:
                        await asyncio.sleep(0.2)
                        await client.start_notify(HRM_UUID, notification_handler)
                        last_notify_ts = now
                    except Exception:
                        break
        finally:
            try:
                await client.stop_notify(HRM_UUID)
            except Exception:
                pass
            await client.disconnect()
            with self._lock:
                self._status = "已断开"
        return True


# 简便访问 API（供其它模块使用）
_GLOBAL_MONITOR: Optional[HeartRateMonitor] = None


def ensure_monitor_started() -> HeartRateMonitor:
    global _GLOBAL_MONITOR
    if _GLOBAL_MONITOR is None:
        _GLOBAL_MONITOR = HeartRateMonitor()
    # start() 内部幂等：线程存活时直接返回，停止后可重新启动
    _GLOBAL_MONITOR.start()
    return _GLOBAL_MONITOR


def get_current_hr() -> Optional[int]:
    mon = _GLOBAL_MONITOR
    return mon.get_last_bpm() if mon else None


def get_status_text() -> str:
    mon = _GLOBAL_MONITOR
    return mon.get_status_text() if mon else "未启用"


if __name__ == "__main__":
    # 独立运行模式：打印最新 BPM（每秒），便于调试
    #
    # 这里用 time.sleep 而不是 asyncio.get_event_loop().run_until_complete(...)：
    # 主线程并没有事件循环，get_event_loop() 在 CPython 3.12+ 已发出
    # DeprecationWarning（"There is no current event loop"），并在 3.14 直接抛
    # RuntimeError。本块只是节流打印，同步 sleep 语义相同且无废弃依赖。
    import time as _time

    monitor = ensure_monitor_started()
    try:
        while True:
            bpm = monitor.get_last_bpm()
            st = monitor.get_status_text()
            if bpm is not None:
                print(f"{bpm} bpm / {st}")
            else:
                print(f"-- / {st}")
            _time.sleep(1.0)
    except KeyboardInterrupt:
        monitor.stop()
