from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_NAME = "URLAutoRefresher"
DIST_DIR = ROOT_DIR / "dist"
PYINSTALLER_WORK_DIR = ROOT_DIR / "build" / "pyinstaller"
SPEC_DIR = ROOT_DIR / "build"
BROWSER_DIR_NAMES = ("chrome-win64", "chrome-win")


def run_command(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.check_call(command, cwd=ROOT_DIR)


def has_browser(path: Path) -> bool:
    if not path.exists():
        return False

    for dirname in BROWSER_DIR_NAMES:
        if (path / dirname / "chrome.exe").is_file():
            return True

    return any(
        child.is_dir()
        and (
            child.name.startswith("chromium-")
            or child.name.startswith("chromium_headless_shell-")
        )
        for child in path.iterdir()
    )


def extract_chrome_zip_if_present() -> None:
    zip_path = ROOT_DIR / "chrome-win64.zip"
    target_root = ROOT_DIR / "browsers"
    if has_browser(target_root):
        return
    if not zip_path.is_file():
        return

    print(f"发现本地浏览器压缩包：{zip_path}")
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    print(f"正在解压到：{target_root}")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target_root)

    if not has_browser(target_root):
        raise RuntimeError("chrome-win64.zip 已解压，但未找到 chrome.exe。")


def browser_source_candidates() -> list[Path]:
    candidates: list[Path] = []

    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(ROOT_DIR / "browsers")

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "ms-playwright")

    candidates.append(Path.home() / ".cache" / "ms-playwright")
    return candidates


def find_or_prepare_browser_source() -> Path:
    extract_chrome_zip_if_present()

    for candidate in browser_source_candidates():
        if has_browser(candidate):
            return candidate

    print("未找到内置 Chromium，正在执行：python -m playwright install chromium")
    run_command([sys.executable, "-m", "playwright", "install", "chromium"])

    for candidate in browser_source_candidates():
        if has_browser(candidate):
            return candidate

    raise RuntimeError(
        "Chromium 安装后仍未找到。请检查 playwright install chromium 是否成功，"
        "或将 chrome-win64.zip 放到项目根目录。"
    )


def copy_browser_to_dist(source_root: Path, app_dist_dir: Path) -> None:
    target_root = app_dist_dir / "browsers"
    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    copied = 0
    for child in source_root.iterdir():
        if not child.is_dir():
            continue
        if (
            child.name in BROWSER_DIR_NAMES
            or child.name.startswith("chromium-")
            or child.name.startswith("chromium_headless_shell-")
        ):
            shutil.copytree(child, target_root / child.name)
            copied += 1

    if copied == 0:
        raise RuntimeError(f"未能从 {source_root} 复制浏览器目录。")

    print(f"已复制 {copied} 个浏览器目录到：{target_root}")


def build_exe() -> None:
    browser_source = find_or_prepare_browser_source()
    print(f"浏览器来源目录：{browser_source}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        str(ROOT_DIR / "app"),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(PYINSTALLER_WORK_DIR),
        "--specpath",
        str(SPEC_DIR),
        "--collect-data",
        "playwright",
        "--collect-submodules",
        "playwright",
        str(ROOT_DIR / "app" / "main.py"),
    ]
    run_command(command)

    app_dist_dir = DIST_DIR / APP_NAME
    (app_dist_dir / "config").mkdir(parents=True, exist_ok=True)
    (app_dist_dir / "logs").mkdir(parents=True, exist_ok=True)
    copy_browser_to_dist(browser_source, app_dist_dir)

    exe_path = app_dist_dir / f"{APP_NAME}.exe"
    print("\n打包完成")
    print(f"EXE：{exe_path}")
    print(f"浏览器目录：{app_dist_dir / 'browsers'}")


if __name__ == "__main__":
    build_exe()
