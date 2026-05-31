from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict, dataclass
from typing import Callable

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from utils import (
    configure_playwright_browsers_path,
    find_bundled_chromium_executable,
    format_exception,
)


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]


@dataclass(frozen=True)
class RefreshConfig:
    url: str
    interval_seconds: int
    page_count: int
    refresh_count: int
    headless: bool = False

    @property
    def total_tasks(self) -> int:
        return self.page_count * self.refresh_count


@dataclass
class PageState:
    page_index: int
    completed_refresh_count: int = 0
    failed_count: int = 0
    open_failed_count: int = 0
    consecutive_failed_count: int = 0
    recreated_count: int = 0
    status: str = "running"
    last_error: str = ""
    closed_early: bool = False

    @property
    def attempted_refresh_count(self) -> int:
        return self.completed_refresh_count + self.failed_count


class BrowserRunner:
    max_consecutive_failures = 5
    max_recreates = 3

    def __init__(
        self,
        config: RefreshConfig,
        stop_event: threading.Event,
        log: LogCallback,
        progress: ProgressCallback,
        status: StatusCallback,
        user_stop_event: threading.Event | None = None,
    ) -> None:
        self.config = config
        self.stop_event = stop_event
        self.user_stop_event = user_stop_event or stop_event
        self.log = log
        self.progress = progress
        self.status = status

        self.completed = 0
        self.errors: list[str] = []
        self.page_states: dict[int, PageState] = {}
        self.fatal_error = False

        self._loop: asyncio.AbstractEventLoop | None = None
        self._playwright_manager = None
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pages: set[Page] = set()
        self._active_page_samples: list[int] = []
        self._max_active_pages = 0
        self._close_lock: asyncio.Lock | None = None
        self._closed = False

    async def run(self) -> dict[str, object]:
        self._loop = asyncio.get_running_loop()
        self._close_lock = asyncio.Lock()
        self.progress(0, self.config.total_tasks)
        self.status("准备中")

        browsers_path = configure_playwright_browsers_path()
        if browsers_path:
            self.log(f"Chromium 浏览器目录：{browsers_path}")

        try:
            self.log("正在启动内置 Chromium 浏览器...")
            self._playwright_manager = async_playwright()
            self._playwright = await self._playwright_manager.start()

            executable_path = find_bundled_chromium_executable()
            launch_options: dict[str, object] = {
                "headless": self.config.headless,
                "args": [
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                ],
            }
            if executable_path is not None:
                launch_options["executable_path"] = str(executable_path)
                self.log(f"使用内置浏览器：{executable_path}")

            self._browser = await self._playwright.chromium.launch(**launch_options)
            self._context = await self._browser.new_context()
            self.status("运行中")
            self.log(
                f"已启动任务：同时保持 {self.config.page_count} 个网页，"
                f"每页刷新 {self.config.refresh_count} 次，"
                f"间隔 {self.config.interval_seconds} 秒"
            )

            tasks = [
                asyncio.create_task(self._run_page(page_index))
                for page_index in range(1, self.config.page_count + 1)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not self._is_user_stop():
                    self._record_error(f"页面任务异常：{format_exception(result)}")
        except Exception as exc:
            self.fatal_error = True
            self._record_error(self._browser_error_message(exc))
        finally:
            await self._shutdown_browser()

        return {
            "stopped": self._is_user_stop(),
            "user_requested_stop": self._is_user_stop(),
            "fatal_error": self.fatal_error,
            "has_errors": bool(self.errors),
            "completed": self.completed,
            "total": self.config.total_tasks,
            "page_results": [
                asdict(self.page_states[index])
                for index in sorted(self.page_states)
            ],
            "max_active_pages": self._max_active_pages,
            "active_page_samples": list(self._active_page_samples),
            "browser_closed": self._closed,
        }

    def request_stop(self) -> None:
        self.user_stop_event.set()
        self.stop_event.set()
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown_browser(), loop)

    async def _run_page(self, page_index: int) -> PageState:
        state = PageState(page_index=page_index)
        self.page_states[page_index] = state
        page_label = f"[Page {page_index}]"
        page: Page | None = None

        try:
            page = await self._open_initial_page(page_index, state)
            if page is None:
                state.status = "failed"
                state.closed_early = True
                return state

            while state.attempted_refresh_count < self.config.refresh_count:
                if self._is_user_stop():
                    state.status = "stopped"
                    state.closed_early = True
                    self.log(f"{page_label} 用户停止，准备关闭")
                    break

                if page.is_closed():
                    page = await self._recreate_page(
                        page_index,
                        state,
                        page,
                        state.attempted_refresh_count + 1,
                    )
                    if page is None:
                        break

                should_continue = await self._wait_interval()
                if not should_continue:
                    state.status = "stopped"
                    state.closed_early = True
                    self.log(f"{page_label} 用户停止，准备关闭")
                    break

                if page.is_closed():
                    page = await self._recreate_page(
                        page_index,
                        state,
                        page,
                        state.attempted_refresh_count + 1,
                    )
                    if page is None:
                        break

                await self._attempt_refresh(page_index, state, page)

                if (
                    state.status == "running"
                    and state.consecutive_failed_count >= self.max_consecutive_failures
                ):
                    state.status = "failed"
                    state.closed_early = True
                    self._record_error(
                        f"{page_label} 连续失败 {self.max_consecutive_failures} 次，标记该页面失败"
                    )
                    break

                if (
                    state.status == "running"
                    and page.is_closed()
                    and not self._is_user_stop()
                ):
                    self.log(f"{page_label} 页面异常关闭，正在重建")
                    page = await self._recreate_page(
                        page_index,
                        state,
                        page,
                        state.attempted_refresh_count + 1,
                    )
                    if page is None:
                        break

            if state.status == "running":
                if state.attempted_refresh_count >= self.config.refresh_count:
                    state.status = (
                        "completed"
                        if state.failed_count == 0
                        else "completed_with_errors"
                    )
                    self.log(f"{page_label} 已完成全部刷新")
                else:
                    state.status = "failed"
                    state.closed_early = True
        finally:
            await self._close_page(page)
            self.log(
                f"{page_label} 最终结果：成功 {state.completed_refresh_count} 次，"
                f"失败 {state.failed_count} 次，重建 {state.recreated_count} 次"
            )
            self.log(f"{page_label} 已关闭")

        return state

    async def _attempt_refresh(
        self,
        page_index: int,
        state: PageState,
        page: Page,
    ) -> None:
        page_label = f"[Page {page_index}]"
        refresh_index = state.attempted_refresh_count + 1

        try:
            await page.reload(wait_until="domcontentloaded", timeout=30_000)
            state.completed_refresh_count += 1
            state.consecutive_failed_count = 0
            self._emit_progress_step()
            self.log(f"{page_label} 第 {refresh_index} 次刷新完成")
        except Exception as exc:
            if self._is_user_stop():
                state.status = "stopped"
                state.closed_early = True
                self.log(f"{page_label} 用户停止，刷新中断")
                return

            state.failed_count += 1
            state.consecutive_failed_count += 1
            state.last_error = format_exception(exc)
            self._emit_progress_step()
            self._record_error(
                f"{page_label} 第 {refresh_index} 次刷新失败：{state.last_error}"
            )

    async def _open_initial_page(
        self,
        page_index: int,
        state: PageState,
    ) -> Page | None:
        page_label = f"[Page {page_index}]"
        for attempt in range(1, self.max_recreates + 1):
            if self._is_user_stop():
                state.status = "stopped"
                state.closed_early = True
                return None

            page = await self._new_page_and_goto(page_index, state, None)
            if page is not None:
                self.log(f"{page_label} 打开成功")
                return page

            state.open_failed_count += 1
            self._record_error(
                f"{page_label} 打开失败，第 {attempt} / {self.max_recreates} 次尝试"
            )

        state.status = "failed"
        state.closed_early = True
        self._record_error(f"{page_label} 打开失败次数过多，标记该页面失败")
        return None

    async def _recreate_page(
        self,
        page_index: int,
        state: PageState,
        old_page: Page | None,
        refresh_index: int,
    ) -> Page | None:
        page_label = f"[Page {page_index}]"
        await self._close_page(old_page)

        while state.recreated_count < self.max_recreates:
            if self._is_user_stop():
                state.status = "stopped"
                state.closed_early = True
                return None

            state.recreated_count += 1
            self.log(f"{page_label} 页面异常关闭，正在重建")
            page = await self._new_page_and_goto(page_index, state, refresh_index)
            if page is not None:
                state.consecutive_failed_count = 0
                self.log(f"{page_label} 已重建，继续第 {refresh_index} 次刷新")
                return page

            self._record_error(
                f"{page_label} 第 {state.recreated_count} 次重建失败：{state.last_error}"
            )

        state.status = "failed"
        state.closed_early = True
        self._record_error(
            f"{page_label} 重建次数达到 {self.max_recreates} 次，标记该页面失败"
        )
        return None

    async def _new_page_and_goto(
        self,
        page_index: int,
        state: PageState,
        refresh_index: int | None,
    ) -> Page | None:
        if self._context is None:
            state.last_error = "浏览器上下文未初始化。"
            return None

        page: Page | None = None
        try:
            page = await self._context.new_page()
            self._pages.add(page)
            self._record_active_page_count()
            await page.goto(self.config.url, wait_until="domcontentloaded", timeout=30_000)
            return page
        except Exception as exc:
            state.last_error = format_exception(exc)
            await self._close_page(page)
            return None

    async def _wait_interval(self) -> bool:
        deadline = asyncio.get_running_loop().time() + self.config.interval_seconds
        while not self._is_user_stop():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return True
            await asyncio.sleep(min(0.2, remaining))
        return False

    async def _close_page(self, page: Page | None) -> None:
        if page is None:
            return
        try:
            if not page.is_closed():
                await page.close()
        except Exception:
            pass
        finally:
            self._pages.discard(page)
            self._record_active_page_count()

    async def _shutdown_browser(self) -> None:
        if self._close_lock is None:
            return

        async with self._close_lock:
            if self._closed:
                return
            self._closed = True

            for page in list(self._pages):
                await self._close_page(page)
            self._pages.clear()
            self._record_active_page_count()

            if self._context is not None:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright_manager is not None:
                try:
                    await self._playwright_manager.stop()
                except Exception:
                    pass
                self._playwright_manager = None
                self._playwright = None

            self.log("浏览器已关闭")

    def _emit_progress_step(self) -> None:
        self.completed += 1
        self.progress(self.completed, self.config.total_tasks)

    def _record_active_page_count(self) -> None:
        active_count = len(self._pages)
        self._active_page_samples.append(active_count)
        self._max_active_pages = max(self._max_active_pages, active_count)

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        self.log(message)

    def _is_user_stop(self) -> bool:
        return self.user_stop_event.is_set()

    @staticmethod
    def _browser_error_message(exc: BaseException) -> str:
        message = format_exception(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            return (
                "浏览器启动失败：未找到内置 Chromium。"
                "请先运行 playwright install chromium，或重新执行打包脚本。"
            )
        return f"浏览器启动或运行失败：{message}"
