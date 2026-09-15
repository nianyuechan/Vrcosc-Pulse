from typing import Callable, Deque, Optional
from collections import deque
from PySide6.QtCore import QObject, QTimer


class FrameLimiter(QObject):
    """Coalesce frequent updates to a maximum FPS.

    Register a callback via `set_callback`, then call `request()` whenever
    an update is needed. The limiter ensures the callback runs at most
    `max_fps` times per second.
    """

    def __init__(self, max_fps: int = 180, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._interval_ms = max(1, int(1000 / max(1, max_fps)))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self._interval_ms)
        self._callback: Optional[Callable[[], None]] = None

        def _fire():
            if self._callback:
                try:
                    self._callback()
                except Exception:
                    pass

        self._timer.timeout.connect(_fire)

    def set_callback(self, cb: Callable[[], None]) -> None:
        self._callback = cb

    def request(self) -> None:
        # Coalesce: if timer running, let it fire; else start.
        if not self._timer.isActive():
            self._timer.start()


class AnimationQueue(QObject):
    """Simple queue to serialize animations that should not overlap.

    Submit opaque payload (e.g., pixmap) and a runner callable; the queue
    ensures at most one runner is active.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._q: Deque[object] = deque()
        self._running: bool = False

    def submit(self, payload: object, runner: Callable[[object, Callable[[], None]], None]) -> None:
        # Collapse excessive queue length: keep only the newest three, drop oldest
        self._q.append(payload)
        while len(self._q) > 3:
            try:
                self._q.popleft()
            except Exception:
                break
        if not self._running:
            self._dequeue_and_run(runner)

    def _dequeue_and_run(self, runner: Callable[[object, Callable[[], None]], None]) -> None:
        if not self._q:
            self._running = False
            return
        self._running = True
        payload = self._q.popleft()

        def _done():
            self._running = False
            self._dequeue_and_run(runner)

        try:
            runner(payload, _done)
        except Exception:
            # Consider as done on exception to avoid deadlock
            _done()

