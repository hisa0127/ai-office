"""ローカルHTTPサーバー(標準ライブラリのみ)。

  GET /              画面
  GET /api/state     いまの稼働状況(JSON)
  GET /api/events    Server-Sent Events。変化があったときだけ push する

127.0.0.1 にしかバインドしない。外部へは一切通信しない。
"""

from __future__ import annotations

import errno
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from .state import StateBuilder

WEB_DIR = Path(__file__).parent / "web"

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Hub:
    """状態を保持し、変化したときだけ購読者へ配る"""

    def __init__(self, builder: StateBuilder, poll_seconds: float):
        self.builder = builder
        self.poll_seconds = poll_seconds
        self.clients: set[queue.Queue] = set()
        self.lock = threading.Lock()
        self._last_signature = ""
        self._stop = threading.Event()

    def snapshot(self) -> dict:
        return self.builder.build()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=8)
        with self.lock:
            self.clients.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            self.clients.discard(q)

    def _publish(self, state: dict) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        with self.lock:
            targets = list(self.clients)
        for q in targets:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass  # 詰まっている購読者は次の更新で追いつく

    def run(self) -> None:
        """ログを監視して、変化があれば配信する"""
        while not self._stop.wait(self.poll_seconds):
            try:
                self.builder.scanner.scan()
                state = self.snapshot()
                # 時刻だけの差分では送らない
                sig = json.dumps({**state, "now": 0}, ensure_ascii=False, sort_keys=True)
                if sig != self._last_signature:
                    self._last_signature = sig
                    self._publish(state)
            except Exception as e:  # 監視スレッドは絶対に落とさない
                print(f"⚠ 監視中のエラー: {e!r}")

    def stop(self) -> None:
        self._stop.set()


class Handler(BaseHTTPRequestHandler):
    hub: Hub = None  # type: ignore[assignment]
    server_version = "ai-office"

    def log_message(self, fmt, *args):  # アクセスログは出さない
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/api/state":
            body = json.dumps(self.hub.snapshot(), ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
            return

        if path == "/api/events":
            self._sse()
            return

        self._static(path)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = self.hub.subscribe()
        try:
            first = json.dumps(self.hub.snapshot(), ensure_ascii=False)
            self.wfile.write(f"data: {first}\n\n".encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    payload = q.get(timeout=20)
                    chunk = f"data: {payload}\n\n"
                except queue.Empty:
                    chunk = ": keep-alive\n\n"      # 接続維持
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(q)

    def _static(self, path: str):
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))


def serve(builder: StateBuilder, port: int, poll_seconds: float, tries: int = 10):
    """待ち受けを開始する。戻り値は (httpd, hub, 実際に使ったポート)。

    指定ポートが埋まっていたら次の番号を順に試す。前回のプロセスが残っていたり、
    別の開発サーバーと衝突したときに、エラーで終わらず動くようにするため。
    """
    hub = Hub(builder, poll_seconds)
    handler = type("BoundHandler", (Handler,), {"hub": hub})

    last: Optional[OSError] = None
    for candidate in range(port, port + tries):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            last = e
            continue
        httpd.daemon_threads = True
        threading.Thread(target=hub.run, daemon=True, name="ai-office-watch").start()
        return httpd, hub, candidate

    raise last or OSError("no free port")
