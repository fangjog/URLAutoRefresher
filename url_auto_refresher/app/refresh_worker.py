from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import QThread, Signal

from browser_runner import BrowserRunner, RefreshConfig
from logger import get_runtime_logger
from utils import format_exception


class RefreshWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, int)
    status_signal = Signal(str)
    completed_signal = Signal(str)

    def __init__(self, config: RefreshConfig) -> None:
        super().__init__()
        self.config = config
        self._stop_event = threading.Event()
        self._user_stop_event = threading.Event()
        self._runner: BrowserRunner | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._logger = get_runtime_logger()

    def stop(self) -> None:
        self._user_stop_event.set()
        self._stop_event.set()
        if self._runner is not None:
            self._runner.request_stop()

    def run(self) -> None:
        final_status = "发生错误"
        self._emit_status("准备中")
        self._emit_log("任务准备中")

        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._runner = BrowserRunner(
                config=self.config,
                stop_event=self._stop_event,
                user_stop_event=self._user_stop_event,
                log=self._emit_log,
                progress=self.progress_signal.emit,
                status=self._emit_status,
            )
            result = self._loop.run_until_complete(self._runner.run())
            if result.get("user_requested_stop"):
                final_status = "已停止"
                self._emit_log("任务已停止")
            elif result.get("fatal_error"):
                final_status = "发生错误"
                self._emit_log("任务发生致命错误，请查看日志。")
            elif result.get("has_errors"):
                final_status = "已完成"
                self._emit_log("任务已完成，但存在部分页面失败，请查看日志。")
            else:
                final_status = "已完成"
                self._emit_log("全部任务已完成")
        except Exception as exc:
            self._emit_log(f"工作线程错误：{format_exception(exc)}")
            final_status = "发生错误"
        finally:
            if self._loop is not None:
                try:
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        self._loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    self._loop.run_until_complete(asyncio.sleep(0))
                except Exception:
                    pass
                finally:
                    self._loop.close()
                    self._loop = None

            self._emit_status(final_status)
            self.completed_signal.emit(final_status)

    def _emit_log(self, message: str) -> None:
        self._logger.info(message)
        self.log_signal.emit(message)

    def _emit_status(self, status: str) -> None:
        self._logger.info("状态：%s", status)
        self.status_signal.emit(status)
