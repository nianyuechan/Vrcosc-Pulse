"""OSC 实时预览与输入字数管理。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextBlockFormat, QTextCursor, QTextOption


class HistoryMixin:
    """输入状态及 OSC 最终文本实时预览。"""

    def on_text_changed(self):
        text = self.input_edit.toPlainText()

        if len(text) > self.max_message_length:
            self.input_edit.blockSignals(True)
            self.input_edit.setPlainText(
                text[:self.max_message_length]
            )
            self.input_edit.moveCursor(QTextCursor.End)
            self.input_edit.blockSignals(False)

            length = self.max_message_length
        else:
            length = len(text)

        self.char_count.setText(f"{length} 字")

        # 空输入时禁用发送按钮
        try:
            sending = bool(getattr(self, "is_sending", False))
            self.start_btn.setEnabled(
                bool(text.strip()) or sending
            )
        except Exception:
            pass

        # 输入变化时立即刷新 OSC 预览
        self.update_osc_preview()

    def update_osc_preview(self, final_text=None):
        """
        刷新左下 OSC 实时效果。

        final_text:
            - 有值：显示实际已经合成/发送的最终文本
            - None：实时重新计算当前准备发送的文本
        """
        try:
            if final_text is None:
                try:
                    final_text = self.compose_message()
                except Exception:
                    final_text = self.input_edit.toPlainText()

            final_text = final_text or ""

            stack = getattr(self, "history_stack", None)
            edit = getattr(self, "history_edit", None)

            if stack is None or edit is None:
                return

            # 没有内容 -> 显示空状态
            if not final_text.strip():
                edit.clear()
                stack.setCurrentIndex(0)
                return

            # 显示预览
            stack.setCurrentIndex(1)

            # 永远只显示当前一份文本，不累计历史
            preview_text = final_text.strip()
            edit.setPlainText(preview_text)

            # 强制整个文档使用水平居中（含自动折行后的续行）
            option = edit.document().defaultTextOption()
            option.setAlignment(Qt.AlignHCenter)
            option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            edit.document().setDefaultTextOption(option)

            # 所有段落水平居中，略拉开行距
            cursor = edit.textCursor()
            cursor.select(QTextCursor.Document)

            block_format = QTextBlockFormat()
            block_format.setAlignment(Qt.AlignHCenter)
            block_format.setTopMargin(0)
            block_format.setBottomMargin(4)
            block_format.setLineHeight(
                125,
                QTextBlockFormat.ProportionalHeight
            )

            cursor.mergeBlockFormat(block_format)
            cursor.clearSelection()

            # 光标回到最顶部
            cursor.movePosition(QTextCursor.Start)
            edit.setTextCursor(cursor)

            try:
                edit.verticalScrollBar().setValue(0)
            except Exception:
                pass

        except Exception:
            pass

    def append_message(self, text: str):
        """
        兼容原有 send_message() 调用。

        原来这里是“追加历史记录”；
        现在改为“显示实际发送给 OSC 的最终效果”。
        """
        self.update_osc_preview(text)
