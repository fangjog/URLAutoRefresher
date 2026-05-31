from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
TESTS_DIR = ROOT_DIR / "tests"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(TESTS_DIR))

from browser_runner import BrowserRunner, RefreshConfig  # noqa: E402
from local_test_server import LocalTestHandler  # noqa: E402


def install_asyncio_pipe_noise_filter() -> None:
    default_hook = sys.unraisablehook

    def hook(unraisable: sys.UnraisableHookArgs) -> None:
        exc = unraisable.exc_value
        if isinstance(exc, ValueError) and "I/O operation on closed pipe" in str(exc):
            return
        default_hook(unraisable)

    sys.unraisablehook = hook


@dataclass(frozen=True)
class StressScenario:
    page_count: int
    refresh_count: int
    interval_seconds: int

    @property
    def expected_total(self) -> int:
        return self.page_count * self.refresh_count


class QuietLocalTestHandler(LocalTestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="URL Auto Refresher stress test")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Local test server port. Use 0 to choose a free port.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only the shortest scenario.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-refresh BrowserRunner logs.",
    )
    return parser.parse_args()


def start_server(port: int) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", port), QuietLocalTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    actual_port = server.server_address[1]
    return server, thread, f"http://127.0.0.1:{actual_port}/test1"


def scenario_list(quick: bool) -> list[StressScenario]:
    scenarios = [
        StressScenario(page_count=5, refresh_count=2, interval_seconds=1),
        StressScenario(page_count=10, refresh_count=20, interval_seconds=1),
        StressScenario(page_count=10, refresh_count=100, interval_seconds=1),
        StressScenario(page_count=20, refresh_count=50, interval_seconds=1),
    ]
    return scenarios[:1] if quick else scenarios


async def run_scenario(
    scenario: StressScenario,
    url: str,
    verbose: bool,
) -> dict[str, Any]:
    progress_history: list[tuple[int, int]] = []
    important_logs: list[str] = []

    def log(message: str) -> None:
        if verbose:
            print(message)
        if any(token in message for token in ("失败", "异常", "最终结果", "已停止")):
            important_logs.append(message)

    def progress(current: int, total: int) -> None:
        progress_history.append((current, total))

    def status(status_text: str) -> None:
        if verbose:
            print(f"STATUS: {status_text}")

    config = RefreshConfig(
        url=url,
        interval_seconds=scenario.interval_seconds,
        page_count=scenario.page_count,
        refresh_count=scenario.refresh_count,
        headless=True,
    )
    runner = BrowserRunner(
        config=config,
        stop_event=threading.Event(),
        log=log,
        progress=progress,
        status=status,
    )
    result = await runner.run()
    await asyncio.sleep(0.1)

    page_results = result.get("page_results", [])
    final_counts = {
        item["page_index"]: item["completed_refresh_count"]
        for item in page_results
    }
    early_closed = [
        item["page_index"]
        for item in page_results
        if item["closed_early"]
    ]

    print("")
    print("=" * 72)
    print(
        f"Scenario: pages={scenario.page_count}, "
        f"refresh_count={scenario.refresh_count}, "
        f"interval={scenario.interval_seconds}s"
    )
    print(f"Expected total refresh attempts: {scenario.expected_total}")
    print(f"Actual total refresh attempts:   {result['completed']}")
    print(f"Final progress:                  {progress_history[-1] if progress_history else None}")
    print(f"Max active pages observed:       {result['max_active_pages']}")
    print(f"Stopped triggered:               {result['stopped']}")
    print(f"Browser closed:                  {result['browser_closed']}")
    print(f"Per-page final success counts:   {final_counts}")
    print(f"Pages closed early:              {early_closed}")

    if important_logs:
        print("Important logs:")
        for line in important_logs[-30:]:
            print(f"  {line}")

    assert result["completed"] == scenario.expected_total, result
    assert not result["stopped"], result
    assert result["browser_closed"], result
    assert result["max_active_pages"] == scenario.page_count, result
    assert len(page_results) == scenario.page_count, page_results

    for item in page_results:
        assert item["completed_refresh_count"] == scenario.refresh_count, item
        assert item["failed_count"] == 0, item
        assert item["closed_early"] is False, item
        assert item["status"] == "completed", item

    print("Result: PASS")
    return result


async def run_all(args: argparse.Namespace) -> None:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT_DIR / "browsers"))
    server, thread, url = start_server(args.port)
    print(f"Local stress test server: {url}")
    try:
        for scenario in scenario_list(args.quick):
            await run_scenario(scenario, url, args.verbose)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    install_asyncio_pipe_noise_filter()
    args = parse_args()
    asyncio.run(run_all(args))
    print("")
    print("All stress scenarios passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
