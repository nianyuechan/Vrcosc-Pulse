from __future__ import annotations

from collections import deque
from typing import Deque, Tuple, Optional
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect

# 简易 LRU 缓存：针对同一 QPixmap 内容与半径的重复模糊
_BLUR_CACHE: dict[Tuple[int, int, int, int], QPixmap] = {}
_BLUR_KEYS: Deque[Tuple[int, int, int, int]] = deque()
_BLUR_MAX = 32  # 限制缓存大小，避免占用过多内存

def _cache_key(pixmap: QPixmap, radius: float) -> Tuple[int, int, int, int] | None:
    try:
        ck = int(pixmap.cacheKey())
        if ck != 0:
            sz = pixmap.size()
            return (ck, int(radius), int(sz.width()), int(sz.height()))
    except Exception:
        pass
    return None


def blur_pixmap(pixmap: QPixmap, radius: float) -> QPixmap:
    if radius <= 0:
        return pixmap
    # 命中缓存则直接返回（仅对有 cacheKey 的像素图启用）
    k = _cache_key(pixmap, radius)
    if k is not None and k in _BLUR_CACHE:
        return _BLUR_CACHE[k]
    scale_factor = 1.0
    # 半径越高，缩放比例越低，以换取更快渲染
    if radius >= 24:
        scale_factor = 0.6
    elif radius >= 16:
        scale_factor = 0.75
    src = pixmap
    if scale_factor < 1.0:
        try:
            src = pixmap.scaled(int(pixmap.width() * scale_factor), int(pixmap.height() * scale_factor), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        except Exception:
            src = pixmap
    try:
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(src)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(radius)
        try:
            if radius >= 20:
                blur.setBlurHints(QGraphicsBlurEffect.PerformanceHint)
        except Exception:
            pass
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        result = QImage(src.size(), QImage.Format_ARGB32)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        scene.render(painter, QRectF(result.rect()), QRectF(src.rect()))
        painter.end()
        out = QPixmap.fromImage(result)
        if scale_factor < 1.0:
            try:
                out = out.scaled(pixmap.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pass
        # 写入缓存（仅当存在 cacheKey）
        if k is not None:
            _BLUR_CACHE[k] = out
            _BLUR_KEYS.append(k)
            # LRU 修剪
            while len(_BLUR_KEYS) > _BLUR_MAX:
                try:
                    old = _BLUR_KEYS.popleft()
                    _BLUR_CACHE.pop(old, None)
                except Exception:
                    break
        return out
    finally:
        try:
            if 'scene' in locals():
                scene.clear()
        except Exception:
            pass
