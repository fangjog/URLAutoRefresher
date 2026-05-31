from __future__ import annotations

import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8765
VALID_PATHS = {f"/test{index}" for index in range(1, 6)}


class LocalTestHandler(BaseHTTPRequestHandler):
    server_version = "URLAutoRefresherLocalTest/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in VALID_PATHS:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Not found. Use /test1 to /test5.".encode("utf-8"))
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>URL Auto Refresher Local Test</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      background: #f5f7fb;
      color: #172033;
    }}
    main {{
      width: min(680px, calc(100vw - 40px));
      padding: 32px;
      background: #fff;
      border: 1px solid #dbe3ef;
      border-radius: 8px;
      box-shadow: 0 14px 40px rgba(30, 44, 72, 0.08);
    }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p {{ margin: 8px 0; font-size: 18px; }}
    code {{
      display: inline-block;
      padding: 4px 8px;
      background: #edf2f8;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>本地刷新测试页面</h1>
    <p>当前路径：<code>{path}</code></p>
    <p>当前时间：<code>{now}</code></p>
  </main>
</body>
</html>"""
        payload = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="URL Auto Refresher local test server")
    parser.add_argument("--host", default=HOST, help="Bind host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port, default: 8765")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), LocalTestHandler)
    print(f"Local test server started: http://{args.host}:{args.port}/test1")
    print("Available paths:")
    for index in range(1, 6):
        print(f"  http://{args.host}:{args.port}/test{index}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local test server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
