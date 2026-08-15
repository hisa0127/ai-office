"""Claude Code のセッションログ(JSONL)を差分で追いかける。

ログにはサブエージェントの起動が Agent ツールの呼び出しとして残る:

    {"type":"tool_use","name":"Agent","input":{
       "description":"...", "subagent_type":"ai-secretary", "run_in_background":false}}

完了すると同じ tool_use_id を持つ tool_result が現れる。この **起動と完了の対** を追跡して
「いま誰が動いているか」を出す。ファイルは数百MBになるので、
  - ファイルごとにバイト位置を覚えて追記分だけ読む
  - 関係ない行は json.loads せず、部分文字列で捨てる
の2点で軽くしている。
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

AGENT_TOOLS = ("Agent", "Task")
MAX_HISTORY = 60

_PROJECT_RE = re.compile(r"projects/([^/\s`'\")]+)")


def _extract_project(text: str) -> Optional[str]:
    if not text:
        return None
    m = _PROJECT_RE.search(text)
    if not m or m.group(1).startswith("_"):
        return None
    return m.group(1)


# 表示してはいけない結果テキスト。
# バックグラウンド起動の tool_result は「起動しました」という内部メタデータが返るだけで、
# 仕事の成果ではない。そのまま画面に出すと内部文言が漏れる。
_INTERNAL_MARKERS = (
    "internal metadata",
    "Async agent launched successfully",
    "launched successfully",
)


def _result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        text = c
    elif isinstance(c, list):
        text = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    else:
        return ""
    if any(m in text for m in _INTERNAL_MARKERS):
        return ""      # 成果ではないので出さない（画面は description にフォールバックする）
    return text


@dataclass
class Run:
    tool_use_id: str
    agent_id: str
    description: str
    project: Optional[str]
    background: bool
    started_at: float
    session_id: str


@dataclass
class Done:
    agent_id: str
    description: str
    project: Optional[str]
    started_at: float
    finished_at: float
    duration_ms: float
    ok: bool
    summary: str


@dataclass
class Session:
    id: str
    title: Optional[str] = None
    last_prompt: Optional[str] = None
    last_activity: float = 0.0
    mtime: float = 0.0


@dataclass
class Scanner:
    directory: Optional[Path]
    open_runs: Dict[str, Run] = field(default_factory=dict)
    history: List[Done] = field(default_factory=list)
    sessions: Dict[str, Session] = field(default_factory=dict)
    stats: Dict[str, dict] = field(default_factory=dict)
    seen_agent_ids: set = field(default_factory=set)
    _cursors: Dict[Path, dict] = field(default_factory=dict)

    # ------------------------------------------------------------ 走査

    def files(self) -> List[Path]:
        if not self.directory or not self.directory.is_dir():
            return []
        try:
            return sorted(self.directory.glob("*.jsonl"))
        except OSError:
            return []

    def scan(self) -> bool:
        """新しく書かれた分だけ読む。何か読めたら True"""
        changed = False
        for path in self.files():
            changed |= self._read_tail(path)
        return changed

    def _read_tail(self, path: Path) -> bool:
        try:
            size = path.stat().st_size
        except OSError:
            return False

        cur = self._cursors.setdefault(path, {"offset": 0, "remainder": b""})
        if size < cur["offset"]:            # 切り詰められたら読み直す
            cur["offset"], cur["remainder"] = 0, b""
        if size == cur["offset"]:
            return False

        session_id = path.stem
        sess = self.sessions.setdefault(session_id, Session(id=session_id))
        sess.mtime = path.stat().st_mtime * 1000

        # バイト位置で管理するのでバイナリで読む。
        # テキストモードの seek は tell() が返した値しか受け付けず、
        # 日本語のように1文字が複数バイトになる場合に壊れる。
        buf: bytes = cur["remainder"]
        try:
            with path.open("rb") as f:
                f.seek(cur["offset"])
                chunk = f.read(size - cur["offset"])
        except OSError:
            return False

        buf += chunk
        parts = buf.split(b"\n")
        cur["remainder"] = parts.pop()          # 最終行は書きかけかもしれないので持ち越す
        # 読んだ分はすべて消費済み。持ち越し分は次回 buf の先頭に足すので、
        # ここで size から引くと同じバイトを二度読むことになる。
        cur["offset"] = size

        for raw in parts:
            if raw:
                self._handle(raw.decode("utf-8", errors="replace"), sess)
        return True

    def _handle(self, line: str, sess: Session) -> None:
        # 高速フィルタ: 関係ない行はパースしない
        has_call = '"subagent_type"' in line
        has_result = '"tool_use_id"' in line
        has_prompt = '"last-prompt"' in line
        has_title = '"ai-title"' in line
        if not (has_call or has_result or has_prompt or has_title):
            return

        try:
            o = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return

        kind = o.get("type")
        if kind == "last-prompt" and o.get("lastPrompt"):
            sess.last_prompt = str(o["lastPrompt"])[:400]
            return
        if kind == "ai-title" and o.get("aiTitle"):
            sess.title = str(o["aiTitle"])
            return

        content = (o.get("message") or {}).get("content")
        if not isinstance(content, list):
            return

        ts = _parse_ts(o.get("timestamp")) or sess.mtime

        for b in content:
            if not isinstance(b, dict):
                continue

            if b.get("type") == "tool_use" and b.get("name") in AGENT_TOOLS:
                inp = b.get("input") or {}
                agent_id = inp.get("subagent_type")
                if not agent_id:
                    continue
                prompt = str(inp.get("prompt") or "")
                self.seen_agent_ids.add(agent_id)
                self.open_runs[b.get("id", "")] = Run(
                    tool_use_id=b.get("id", ""),
                    agent_id=agent_id,
                    description=inp.get("description") or "(説明なし)",
                    project=_extract_project(prompt) or _extract_project(inp.get("description") or ""),
                    background=bool(inp.get("run_in_background")),
                    started_at=ts,
                    session_id=sess.id,
                )
                sess.last_activity = max(sess.last_activity, ts)
                continue

            if b.get("type") == "tool_result":
                run = self.open_runs.pop(b.get("tool_use_id", ""), None)
                if not run:
                    continue
                done = Done(
                    agent_id=run.agent_id,
                    description=run.description,
                    project=run.project,
                    started_at=run.started_at,
                    finished_at=ts,
                    duration_ms=max(0.0, ts - run.started_at),
                    ok=not b.get("is_error"),
                    summary=" ".join(_result_text(b).split())[:160],
                )
                self.history.insert(0, done)
                del self.history[MAX_HISTORY:]
                st = self.stats.setdefault(run.agent_id, {"runs": 0, "total_ms": 0.0, "last": None})
                st["runs"] += 1
                st["total_ms"] += done.duration_ms
                st["last"] = done
                sess.last_activity = max(sess.last_activity, ts)

    # ------------------------------------------------------------ 参照

    def latest_session(self) -> Optional[Session]:
        if not self.sessions:
            return None
        return max(self.sessions.values(), key=lambda s: max(s.mtime, s.last_activity))

    def runs_for(self, agent_id: str) -> List[Run]:
        return sorted((r for r in self.open_runs.values() if r.agent_id == agent_id),
                      key=lambda r: r.started_at)


def _parse_ts(value) -> Optional[float]:
    """ISO8601 をミリ秒エポックに"""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return None


def now_ms() -> float:
    return time.time() * 1000
