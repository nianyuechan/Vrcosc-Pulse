"""OSC client wrapper for sending messages to VRChat ChatBox.

Also provides a lightweight probe that sends a test `/chatbox/input` to
VRChat (default `127.0.0.1:9000`) and listens on UDP `9001` for a
`/chatbox/typing` response within a timeout, to determine whether OSC is enabled.
"""

import logging
import socket
import threading
import time
from typing import Optional

try:
    from pythonosc.udp_client import SimpleUDPClient
except Exception:  # pragma: no cover - optional dependency
    SimpleUDPClient = None  # type: ignore


# 探测需要独占绑定 127.0.0.1:9001（VRChat 的 OSC 回包端口）。
# 并发探测会让后一次 bind() 直接失败并被误判成“OSC 未启用”，
# 因此这里串行化整段“绑定 + 监听”窗口。
_PROBE_LOCK = threading.Lock()


class OSCClient:
    def __init__(self, address: str = "127.0.0.1", port: int = 9000) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._client: Optional[SimpleUDPClient] = None
        if SimpleUDPClient is not None:
            try:
                self._client = SimpleUDPClient(address, port)
            except Exception as e:
                self._logger.exception("Failed to init OSC client: %s", e)

    def send_message(self, text: str, visible: bool = True) -> bool:
        if not self._client:
            self._logger.warning("OSC client unavailable; message not sent: %s", text)
            return False
        try:
            self._client.send_message("/chatbox/input", [text, visible])
            return True
        except Exception as e:
            self._logger.exception("OSC send failed: %s", e)
            return False

    def probe_enabled(self, timeout: float = 1.0) -> bool:
        """Probe whether VRChat OSC is enabled.

        Behavior:
        - Sends a minimal `/chatbox/input` message (invisible) to VRChat.
        - Opens a temporary UDP socket bound to `127.0.0.1:9001`.
        - Waits up to `timeout` seconds for any packet containing `/chatbox/typing`.
        - Returns True if received; otherwise False.

        Notes:
        - Requires `python-osc` to be available for the send step.
        - 并发探测会串行执行（9001 只能被一个 socket 绑定）。若等待锁或绑定失败，
          说明无法判定状态，此时返回 True —— 探测只用于决定要不要弹“OSC 未启用”
          提示，拿不到证据时不应打扰用户。
        - This is a best-effort check and should not block the UI thread.
        """
        # 先串行化“绑定 + 监听”窗口，避免两次并发探测抢 9001 造成误判
        acquired = _PROBE_LOCK.acquire(timeout=max(0.5, float(timeout) + 2.0))
        try:
            return self._probe_enabled_locked(timeout)
        finally:
            if acquired:
                _PROBE_LOCK.release()
            else:
                self._logger.warning(
                    "OSC probe skipped: another probe is still holding UDP 9001"
                )

    def _probe_enabled_locked(self, timeout: float) -> bool:
        # Send a minimal message to trigger typing echo (best-effort)
        try:
            if self._client is None:
                self._logger.warning("OSC probe send skipped: client unavailable")
            else:
                # Send with visible=False to avoid popping chatbox in-game
                self._client.send_message("/chatbox/input", ["", False])
        except Exception as e:
            # Continue to listen anyway; maybe other messages will trigger typing
            self._logger.exception("OSC probe send failed: %s", e)

        # Listen on UDP 9001 for typing echo (ensure socket always closes)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.bind(("127.0.0.1", 9001))
            except Exception as e:
                # 端口被别的进程占用：无法判定 OSC 状态，按“未确认”处理而不是
                # 直接报“未启用”，否则会给用户一个假警告。
                self._logger.warning("OSC probe bind 9001 failed (indeterminate): %s", e)
                return True

            try:
                sock.settimeout(timeout)
            except Exception as e:
                self._logger.warning("OSC probe settimeout failed (indeterminate): %s", e)
                return True

            end = time.time() + max(0.0, timeout)
            while time.time() < end:
                try:
                    data, _addr = sock.recvfrom(4096)
                    if b"/chatbox/typing" in data:
                        return True
                except socket.timeout:
                    break
                except Exception:
                    break
            return False
