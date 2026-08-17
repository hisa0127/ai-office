"""Claude Code のセッションログ(JSONL)を差分で追いかける。

ログにはサブエージェントの起動が Agent ツールの呼び出しとして残る:

    {"type":"tool_use","name":"Agent","input":{
       "description":"...", "subagent_type":"ai-secretary", "run_in_background":false}}

完了すると同じ tool_use_id を持つ tool_result が現れる。この **起動と完了の対** を追跡して
「いま誰が動いているか」を出す。

ただし **非同期起動** は別扱いにする。非同期では tool_result が「起動しました」という通知として
即座に返るため、これを完了とみなすと、実際には何十分も働いているエージェントが
起動1秒後に退勤したことになってしまう。本当の完了は、あとから届く <task-notification> が
起動時と同じ tool_use_id を持って知らせる。

非同期かどうかを起動時の入力 run_in_background で判定してはいけない。このキーは
**省略されることがあり、省略時は非同期が既定**であるため、入力を見ると既定の起動が
すべて同期と誤判定される。結果側の toolUseResult.isAsync / status="async_launched" を正とする。

ファイルは数百MBになるので、
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

# 非同期起動の判定に使う唯一のマーカー。表示抑止(_INTERNAL_MARKERS)より厳しくする。
_ASYNC_MARK = "Async agent launched successfully"

# バックグラウンド起動の本当の完了通知。起動時と同じ tool_use_id を持って届く。
# タグ名がハイフン区切り(<tool-use-id>)で、tool_result のキー("tool_use_id")とは綴りが違う。
_NOTE_MARK = "<task-notification>"
_NOTE_ID_RE = re.compile(r"<tool-use-id>\s*(.*?)\s*</tool-use-id>", re.S)
_NOTE_STATUS_RE = re.compile(r"<status>\s*(.*?)\s*</status>", re.S)
_NOTE_RESULT_RE = re.compile(r"<result>\s*(.*?)\s*</result>", re.S)
_NOTE_SUMMARY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.S)


def _as_text(content) -> str:
    """文字列のこともブロック配列のこともある本文を、文字列にして返す"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


# 完了通知の status。実ログで観測できたのは completed / failed / killed の3種類。
# 「failed 以外は成功」にすると killed(途中停止)が成功として集計され、
# 統計上は正常に見えるのに実際は中断している、という一番気づけない壊れ方をする。
# 知らない値は成功にしない = 間違っていても画面に出るので気づける、という方に倒す。
_OK_STATUSES = ("completed",)


def _status_is_ok(status: Optional[str]) -> bool:
    if status is None:
        return True          # status が無い形式は判定材料が無いので成功扱い
    return status.strip().lower() in _OK_STATUSES


def _is_async_result(record: dict, block: dict) -> bool:
    """その tool_result が「起動しました」の通知か（＝仕事の完了ではない）を判定する。

    起動時の run_in_background は省略されることがあり、**省略時は非同期が既定**。
    入力フラグだけを見ると既定の起動がすべて同期扱いになり、0秒で退勤してしまう。
    結果側には isAsync / status="async_launched" として明示されるので、そちらを正とする。
    """
    r = record.get("toolUseResult")
    if isinstance(r, dict) and (r.get("isAsync") or r.get("status") == "async_launched"):
        return True
    # toolUseResult を持たない古いログ向けの保険。表示抑止用の _INTERNAL_MARKERS は
    # "launched successfully" のような緩い断片を含むので流用しない。
    # 通常の報告文に紛れ込むと、その実行が永久に「稼働中」のまま残ってしまう。
    return _ASYNC_MARK in _as_text(block.get("content"))


def _notification_text(o: dict) -> str:
    """完了通知の本文を取り出す。無ければ空文字。

    同じ通知がログに3通りの形で現れる(Claude Code 2.1系で確認):
      失敗時  type=user            message.content
      成功時  type=queue-operation 直下の content
      成功時  type=attachment      attachment.prompt
    どれか1つだけ読んでいると、片方の結末で永久に退勤しなくなる。
    なお自分の発言が通知を引用している場合があるので assistant は除外する。
    """
    if o.get("type") == "assistant":
        return ""
    for cand in (
        (o.get("message") or {}).get("content"),
        o.get("content"),
        (o.get("attachment") or {}).get("prompt"),
    ):
        text = _as_text(cand)
        if text.lstrip().startswith(_NOTE_MARK):
            return text
    return ""


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
        has_note = _NOTE_MARK in line          # ハイフン綴りなので has_result では拾えない
        if not (has_call or has_result or has_prompt or has_title or has_note):
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

        ts = _parse_ts(o.get("timestamp")) or sess.mtime

        # バックグラウンド起動の完了通知。tool_result より後に届く。
        # 同じ通知が複数行に分かれて来るので、2度目以降は pop が空振りして何も起きない
        note = _notification_text(o)
        if note:
            m = _NOTE_ID_RE.search(note)
            run = self.open_runs.pop(m.group(1), None) if m else None
            if run:
                st = _NOTE_STATUS_RE.search(note)
                body = _NOTE_RESULT_RE.search(note) or _NOTE_SUMMARY_RE.search(note)
                self._finish(
                    run, ts, sess,
                    ok=_status_is_ok(st.group(1) if st else None),
                    summary=body.group(1) if body else "",
                )
            return

        content = (o.get("message") or {}).get("content")
        if not isinstance(content, list):
            return

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
                tid = b.get("tool_use_id", "")
                run = self.open_runs.get(tid)
                if not run:
                    continue

                # 起動そのものに失敗した場合(エージェント名の打ち間違いなど)。
                # 実体が動いていないので完了通知は永久に来ない。ここで閉じないと在席したままになる。
                if b.get("is_error"):
                    self.open_runs.pop(tid, None)
                    self._finish(run, ts, sess, ok=False, summary=_result_text(b))
                    continue

                # 非同期起動かどうかは、起動時の入力ではなく **結果側の申告** で判定する。
                # run_in_background は省略されることがあり(省略時は非同期が既定)、
                # 入力フラグを見ると既定の起動が全部「同期」と誤判定される。
                if run.background or _is_async_result(o, b):
                    # 「起動しました」の通知であって仕事の完了ではない。
                    # 本当の完了は <task-notification> で届くので、ここでは席を立たせない。
                    run.background = True
                    sess.last_activity = max(sess.last_activity, ts)
                    continue

                self.open_runs.pop(tid, None)
                self._finish(
                    run, ts, sess,
                    ok=not b.get("is_error"),
                    summary=_result_text(b),
                )

    def _finish(self, run: Run, ts: float, sess: Session, ok: bool, summary: str) -> None:
        """1件の稼働を終了として記録する。通常起動とバックグラウンド起動で共通"""
        done = Done(
            agent_id=run.agent_id,
            description=run.description,
            project=run.project,
            started_at=run.started_at,
            finished_at=ts,
            duration_ms=max(0.0, ts - run.started_at),
            ok=ok,
            summary=" ".join(summary.split())[:160],
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
