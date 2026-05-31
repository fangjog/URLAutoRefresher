# URL Auto Refresher

Windows 桌面软件：授权网址自动刷新测试器。仅限自有或已授权网址测试使用，请勿用于刷访问量、干扰第三方网站、绕过风控或规避访问限制。

## 功能

- 输入 `http` / `https` 网址并在开始前校验格式。
- 设置刷新秒数、同时运行网页数量、刷新次数。
- 使用 Playwright 控制随软件携带的 Chromium/Chrome-for-testing，不依赖用户电脑已安装 Chrome。
- 使用 PySide6 GUI + QThread + asyncio 并发刷新，界面运行时不卡死。
- 默认保持固定数量页面同时运行：例如 10 个页面、刷新 100 次，会保持 10 个页面分别刷新 100 次。
- 单个页面刷新失败不会停止全局任务；连续失败达到上限才标记该页面失败。
- 页面异常关闭时会自动重建页面，并从当前刷新进度继续。
- 支持手动停止，停止后关闭所有页面和浏览器进程。
- 显示总进度、状态和运行日志，并写入 `logs/runtime.log`。
- GUI 日志最多保留最近 1000 行，文件日志完整保留并轮转。
- 可选“后台运行”，勾选后使用 `headless=True`。

## 项目结构

```text
url_auto_refresher/
├─ app/
│  ├─ main.py
│  ├─ ui_main.py
│  ├─ refresh_worker.py
│  ├─ browser_runner.py
│  ├─ logger.py
│  └─ utils.py
├─ tests/
│  ├─ local_test_server.py
│  └─ stress_test_runner.py
├─ build/
│  └─ build_exe.py
├─ requirements.txt
├─ README.md
├─ SELF_TEST_REPORT.md
└─ run_dev.bat
```

## 开发环境安装

建议使用 Python 3.11 或更高版本。

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

浏览器有两种准备方式。

方式一：使用 Playwright 下载 Chromium。

```bat
set PLAYWRIGHT_BROWSERS_PATH=%CD%\browsers
playwright install chromium
```

方式二：将已下载好的 `chrome-win64.zip` 放到项目根目录。打包脚本会在 `browsers` 目录缺少浏览器时自动解压该文件，程序运行时会优先识别：

```text
browsers\chrome-win64\chrome.exe
```

开发运行：

```bat
python app\main.py
```

或执行：

```bat
run_dev.bat
```

## 本地测试服务

启动测试 HTTP 服务：

```bat
python tests\local_test_server.py
```

默认端口为 `8765`。如果本机该端口已被其他程序占用，可临时指定其他端口：

```bat
python tests\local_test_server.py --port 18765
```

可用测试地址：

```text
http://127.0.0.1:8765/test1
http://127.0.0.1:8765/test2
http://127.0.0.1:8765/test3
http://127.0.0.1:8765/test4
http://127.0.0.1:8765/test5
```

推荐软件测试参数：

```text
网址：http://127.0.0.1:8765/test1
刷新秒数：5
同时运行网页数量：5
刷新次数：2
```

验收结果应为：同时打开 5 个页面，每个页面刷新 2 次，总进度显示 `10 / 10`，结束后浏览器自动关闭，软件状态显示“已完成”。

## 压力测试

自动压力测试会启动本地测试服务，并依次验证：

- 5 个网页，刷新 2 次，间隔 1 秒，预期 `10 / 10`。
- 10 个网页，刷新 20 次，间隔 1 秒，预期 `200 / 200`。
- 10 个网页，刷新 100 次，间隔 1 秒，预期 `1000 / 1000`。
- 20 个网页，刷新 50 次，间隔 1 秒，预期 `1000 / 1000`。

运行：

```bat
python tests\stress_test_runner.py
```

只跑最短场景：

```bat
python tests\stress_test_runner.py --quick
```

## 打包 EXE

```bat
python build\build_exe.py
```

打包脚本会：

- 使用 PyInstaller 生成 onedir 模式 EXE。
- 查找 `browsers\chrome-win64\chrome.exe`、Playwright Chromium，或自动解压项目根目录下的 `chrome-win64.zip`。
- 复制浏览器到 `dist\URLAutoRefresher\browsers`。
- 创建 `config` 和 `logs` 目录。

打包后目录示例：

```text
dist/
└─ URLAutoRefresher/
   ├─ URLAutoRefresher.exe
   ├─ browsers/
   │  └─ chrome-win64/
   ├─ config/
   └─ logs/
```

程序在 EXE 模式运行时会设置：

```text
PLAYWRIGHT_BROWSERS_PATH = EXE 同级目录\browsers
```

因此在新电脑上只要保持 `URLAutoRefresher.exe` 与 `browsers` 目录同级，即可使用内置浏览器。

## 日志

界面日志显示每个页面的打开、刷新、重建、关闭和错误信息。文件日志写入：

```text
logs\runtime.log
```

日志文件会自动轮转，单个文件最大约 2 MB，最多保留 3 个备份。

## 合规使用说明

本软件只用于自有或已授权网址的可用性、刷新、并发页面打开等测试。请勿用于刷访问量、干扰第三方网站、绕过检测、代理池访问、验证码识别、账号登录自动化或任何未授权用途。软件不会提供代理、stealth、随机 UA、绕风控、登录或验证码识别功能。

## 自动更新

软件启动时默认检查 GitHub Releases 是否存在新版本，也可以在界面点击“检查更新”手动检查。
如果发现高于当前版本的发布版本，软件会提示打开对应的下载页面；如果发布版本包含 Windows 安装包或压缩包，会优先打开该资源。
