from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def ensure_app_dirs() -> None:
    for dirname in ("config", "logs"):
        (app_base_dir() / dirname).mkdir(parents=True, exist_ok=True)


def logs_dir() -> Path:
    path = app_base_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    path = app_base_dir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_browsers_dir() -> Path:
    return app_base_dir() / "browsers"


def find_bundled_chromium_executable() -> Path | None:
    """Find an executable Chromium/Chrome-for-testing bundled with the app."""
    browser_roots = [
        local_browsers_dir(),
        app_base_dir(),
    ]
    candidates: list[Path] = []
    for root in browser_roots:
        candidates.extend(
            [
                root / "chrome-win64" / "chrome.exe",
                root / "chrome-win" / "chrome.exe",
            ]
        )

        if root.exists():
            candidates.extend(root.glob("chromium-*/chrome-win/chrome.exe"))
            candidates.extend(root.glob("chromium-*/chrome.exe"))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def configure_playwright_browsers_path() -> Path | None:
    """Configure Playwright browser lookup for packaged builds."""
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        return Path(env_path)

    browsers_path = local_browsers_dir()
    if is_frozen() or browsers_path.exists():
        browsers_path.mkdir(parents=True, exist_ok=True)
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
        return browsers_path

    return None


def validate_url(raw_url: str) -> tuple[bool, str]:
    url = raw_url.strip()
    if not url:
        return False, "请输入网址。"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "网址必须以 http:// 或 https:// 开头。"
    if not parsed.netloc:
        return False, "网址格式不正确，请检查域名或 IP。"
    if any(ch.isspace() for ch in url):
        return False, "网址中不能包含空格。"

    return True, url


def format_exception(exc: BaseException) -> str:
    message = str(exc).strip()
    return message if message else exc.__class__.__name__
