from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QThread, Signal

from app_info import APP_VERSION, GITHUB_REPO, LATEST_RELEASE_API_URL, RELEASES_URL


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    download_url: str | None = None
    release_name: str = ""
    message: str = ""


def normalize_version(version: str) -> str:
    value = version.strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value or "0.0.0"


def is_newer_version(latest_version: str, current_version: str) -> bool:
    latest_parts = _numeric_version_parts(latest_version)
    current_parts = _numeric_version_parts(current_version)
    max_len = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (max_len - len(latest_parts))
    current_parts += (0,) * (max_len - len(current_parts))
    return latest_parts > current_parts


def select_download_asset(assets: Any) -> str | None:
    if not isinstance(assets, list):
        return None

    ranked_urls: list[tuple[int, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue

        name = str(asset.get("name") or "").lower()
        download_url = asset.get("browser_download_url")
        if not isinstance(download_url, str) or not download_url:
            continue

        score = 0
        if name.endswith((".exe", ".msi")):
            score += 60
        elif name.endswith((".zip", ".7z", ".rar")):
            score += 50
        if "windows" in name or "win" in name:
            score += 20
        if "urlautorefresher" in name or "url-auto-refresher" in name:
            score += 10

        if score > 0:
            ranked_urls.append((score, download_url))

    if not ranked_urls:
        return None

    ranked_urls.sort(key=lambda item: item[0], reverse=True)
    return ranked_urls[0][1]


def check_for_update(
    current_version: str = APP_VERSION,
    repo: str = GITHUB_REPO,
    timeout_seconds: int = 8,
) -> UpdateCheckResult:
    api_url = _latest_release_api_url(repo)
    request = Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"URLAutoRefresher/{current_version}",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return UpdateCheckResult(
                current_version=current_version,
                latest_version=current_version,
                update_available=False,
                release_url=_releases_url(repo),
                message="暂未发现可用的发布版本。",
            )
        if exc.code in {403, 429}:
            return check_for_update_from_latest_page(
                current_version=current_version,
                repo=repo,
                timeout_seconds=timeout_seconds,
            )
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(str(reason)) from exc
    except TimeoutError as exc:
        raise RuntimeError("连接超时") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("更新信息解析失败") from exc

    tag_name = str(payload.get("tag_name") or "").strip()
    if not tag_name:
        raise RuntimeError("更新信息缺少版本号")

    latest_version = normalize_version(tag_name)
    release_url = str(payload.get("html_url") or _releases_url(repo))
    release_name = str(payload.get("name") or tag_name)
    download_url = select_download_asset(payload.get("assets"))
    update_available = is_newer_version(latest_version, current_version)

    if update_available:
        message = f"发现新版本 v{latest_version}。"
    else:
        message = "当前已是最新版本。"

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        update_available=update_available,
        release_url=release_url,
        download_url=download_url,
        release_name=release_name,
        message=message,
    )


def check_for_update_from_latest_page(
    current_version: str = APP_VERSION,
    repo: str = GITHUB_REPO,
    timeout_seconds: int = 8,
) -> UpdateCheckResult:
    request = Request(
        f"{_releases_url(repo)}/latest",
        headers={"User-Agent": f"URLAutoRefresher/{current_version}"},
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            latest_url = response.geturl()
    except HTTPError as exc:
        if exc.code == 404:
            return UpdateCheckResult(
                current_version=current_version,
                latest_version=current_version,
                update_available=False,
                release_url=_releases_url(repo),
                message="暂未发现可用的发布版本。",
            )
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(str(reason)) from exc
    except TimeoutError as exc:
        raise RuntimeError("连接超时") from exc

    tag_marker = "/releases/tag/"
    if tag_marker not in latest_url:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=current_version,
            update_available=False,
            release_url=_releases_url(repo),
            message="暂未发现可用的发布版本。",
        )

    tag_name = latest_url.split(tag_marker, maxsplit=1)[1].strip("/")
    latest_version = normalize_version(tag_name)
    update_available = is_newer_version(latest_version, current_version)
    message = (
        f"发现新版本 v{latest_version}。"
        if update_available
        else "当前已是最新版本。"
    )

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        update_available=update_available,
        release_url=latest_url,
        message=message,
    )


class UpdateCheckerWorker(QThread):
    result_signal = Signal(object)
    error_signal = Signal(str)

    def __init__(
        self,
        current_version: str = APP_VERSION,
        repo: str = GITHUB_REPO,
        timeout_seconds: int = 8,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.repo = repo
        self.timeout_seconds = timeout_seconds

    def run(self) -> None:
        try:
            result = check_for_update(
                current_version=self.current_version,
                repo=self.repo,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception as exc:
            self.error_signal.emit(str(exc) or exc.__class__.__name__)
            return

        self.result_signal.emit(result)


def _numeric_version_parts(version: str) -> tuple[int, ...]:
    normalized = normalize_version(version)
    main_version = re.split(r"[-+]", normalized, maxsplit=1)[0]
    parts: list[int] = []
    for token in main_version.split("."):
        match = re.match(r"\d+", token)
        parts.append(int(match.group(0)) if match else 0)
    return tuple(parts) or (0,)


def _latest_release_api_url(repo: str) -> str:
    if repo == GITHUB_REPO:
        return LATEST_RELEASE_API_URL
    return f"https://api.github.com/repos/{repo}/releases/latest"


def _releases_url(repo: str) -> str:
    if repo == GITHUB_REPO:
        return RELEASES_URL
    return f"https://github.com/{repo}/releases"
