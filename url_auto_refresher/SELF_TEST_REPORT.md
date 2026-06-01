# 自测报告

测试日期：2026-05-31

## 本次 Bug 修复

Bug 描述：

- 当设置较多网页和较多刷新次数时，例如 10 个网页刷新 100 次、20 个网页刷新 50 次，运行一段时间后页面数量会逐渐减少。
- 页面未完成指定刷新次数前就被关闭，最终状态可能误显示“已停止”，而不是“已完成”。

原因定位：

- 旧逻辑中，单个 page 的 `goto/reload` 一旦超时或异常，就会进入 `finally` 并关闭该 page。
- 单个页面异常没有重建机制，长时间运行时临时网络/页面异常会让同时运行的页面数不断下降。
- 最终状态直接依赖 `stop_event`，缺少“用户主动停止”和“内部异常”的明确区分。
- GUI 日志未限制行数，大量日志可能拖慢界面。

修复方案：

- 新增独立 `user_stop_event`，只有用户点击停止或关闭窗口时才标记“已停止”。
- 每个页面使用 `PageState` 维护状态：成功次数、失败次数、重建次数、最终状态。
- 单次刷新失败只记录错误并推进一次进度，不关闭整个页面，也不会因为连续失败而提前关闭页面。
- 页面异常关闭时自动重建，最多重建 3 次，并从当前刷新进度继续。
- `asyncio.gather(..., return_exceptions=True)` 等待所有页面任务完成后再关闭 browser/context。
- 浏览器启动参数增加稳定性选项：`--disable-dev-shm-usage`、`--disable-gpu`、`--no-first-run`、`--no-default-browser-check`、`--disable-background-timer-throttling`、`--disable-backgrounding-occluded-windows`、`--disable-renderer-backgrounding`。
- GUI 日志最多保留最近 1000 行，文件日志继续完整写入。

## 测试环境

- Python：3.13.13 虚拟环境 `.venv`
- GUI：PySide6 6.11.1
- 浏览器控制：Playwright 1.60.0
- 打包工具：PyInstaller 6.20.0
- 内置浏览器：项目根目录 `chrome-win64.zip` 已解压为 `browsers\chrome-win64\chrome.exe`

## 测试命令

```bat
.venv\Scripts\python -m compileall .\app .\tests .\build
.venv\Scripts\python tests\stress_test_runner.py
.venv\Scripts\python tests\stress_test_runner.py --quick
.venv\Scripts\python build\build_exe.py
```

说明：当前机器的 `8765` 端口已被其他无关本地服务占用，因此压力测试脚本自动选择空闲本地端口。测试服务默认端口仍为需求指定的 `8765`。

## 压力测试结果

场景 1：

```text
设置网页数量：5
设置刷新次数：2
应完成总刷新数：10
实际完成总刷新数：10
最终进度：10 / 10
最大同时页面数：5
是否误触发 stopped：否
browser 是否正常关闭：是
结果：通过
```

场景 2：

```text
设置网页数量：10
设置刷新次数：20
应完成总刷新数：200
实际完成总刷新数：200
最终进度：200 / 200
最大同时页面数：10
是否误触发 stopped：否
browser 是否正常关闭：是
结果：通过
```

场景 3：

```text
设置网页数量：10
设置刷新次数：100
应完成总刷新数：1000
实际完成总刷新数：1000
最终进度：1000 / 1000
最大同时页面数：10
每个 page 最终结果：成功 100 次，失败 0 次，重建 0 次
是否误触发 stopped：否
browser 是否正常关闭：是
结果：通过
```

场景 4：

```text
设置网页数量：20
设置刷新次数：50
应完成总刷新数：1000
实际完成总刷新数：1000
最终进度：1000 / 1000
最大同时页面数：20
每个 page 最终结果：成功 50 次，失败 0 次，重建 0 次
是否误触发 stopped：否
browser 是否正常关闭：是
结果：通过
```

## 打包验证

- 打包命令：`.venv\Scripts\python build\build_exe.py`
- 打包结果：通过。
- EXE 路径：`dist\URLAutoRefresher\URLAutoRefresher.exe`
- 内置浏览器路径：`dist\URLAutoRefresher\browsers\chrome-win64\chrome.exe`
- 打包后 EXE 启动检查：通过，EXE 启动后保持运行，没有闪退。

## 是否通过

通过。本次修复后，压力测试中未出现页面数量逐渐减少、未点击停止却显示“已停止”、进度不到 total、单页异常影响全局 browser 的问题。
