"""ログの生データを、画面が必要とする「稼働状況」に組み立てる。"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .roster import Agent
from .scanner import Scanner


def now_ms() -> float:
    return time.time() * 1000


# ---------------------------------------------------------------- 案件情報


def _head(path: Path, lines: int) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return "".join(next(f, "") for _ in range(lines))
    except OSError:
        return ""


def _pick(pattern: str, text: str, strip_comment: bool = False) -> Optional[str]:
    m = re.search(pattern, text)
    if not m:
        return None
    v = m.group(1)
    if strip_comment:
        v = v.split("#")[0]
    return v.strip() or None


def read_projects(cfg: Config) -> List[dict]:
    """案件フォルダを読む。規約に合わない環境では素直に空を返す(カードごと隠れる)"""
    root = cfg.projects_dir
    if not root:
        return []
    pc = cfg["projects"]
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        meta = _head(d / pc["projectFile"], 30)
        status = _head(d / pc["statusFile"], 12)

        directives = []
        ddir = d / pc["directivesDir"]
        if ddir.is_dir():
            for f in sorted(ddir.glob("*.md")):
                try:
                    directives.append({"name": f.name, "mtime": f.stat().st_mtime * 1000})
                except OSError:
                    pass

        try:
            mtime = (d / pc["statusFile"]).stat().st_mtime * 1000
        except OSError:
            mtime = d.stat().st_mtime * 1000

        out.append({
            "name": d.name,
            "client": _pick(r"client\s*[:：]\s*(.+)", meta, True),
            "phase": _pick(r"phase\s*[:：]\s*(.+)", meta, True),
            "lastUpdated": _pick(r"(?:最終更新|updated)[^:：]*[:：]\s*(.+)", status),
            "nextAction": (_pick(r"(?:次のアクション|next)[^:：]*[:：]\s*(.+)", status)
                           or _pick(r"(?:現在の工程|phase)[^:：]*[:：]\s*(.+)", status)),
            "directives": len(directives),
            "_directives": directives,
            "_mtime": mtime,
        })
    out.sort(key=lambda p: p["_mtime"], reverse=True)
    return out


# ---------------------------------------------------------------- 稼働状況


# デモ表示で使う架空の仕事。最後の1件はわざと古くして「滞留」を見せる
DEMO_TASKS = {
    "ja": [
        ("トップページのFV実装", 90_000),
        ("要件定義をまとめ中", 25_000),
        ("配色トークンの調整", 40_000),
        ("フォーム送信のQA", 22 * 60_000),
    ],
    "en": [
        ("Implementing the hero section", 90_000),
        ("Drafting the requirements", 25_000),
        ("Tuning the color tokens", 40_000),
        ("QA on the contact form", 22 * 60_000),
    ],
}


class StateBuilder:
    def __init__(self, cfg: Config, scanner: Scanner, agents: List[Agent], demo: bool = False):
        self.cfg = cfg
        self.scanner = scanner
        self.agents = agents
        self.demo = demo
        self._projects: List[dict] = []
        self._projects_at = 0.0

    def projects(self) -> List[dict]:
        if now_ms() - self._projects_at > 10_000:
            self._projects = read_projects(self.cfg)
            self._projects_at = now_ms()
        return self._projects

    def visible_agents(self) -> List[Agent]:
        return self.agents

    def _build(self) -> Dict[str, Any]:
        now = now_ms()
        sc = self.scanner
        stall_ms = self.cfg.stall_ms

        shown = self.visible_agents()
        agents_out = []
        for a in shown:
            running = sc.runs_for(a.id)
            cur = running[0] if running else None
            status = "idle"
            if cur:
                status = "stalled" if now - cur.started_at > stall_ms else "working"
            st = sc.stats.get(a.id, {"runs": 0, "total_ms": 0.0, "last": None})
            last = st["last"]

            agents_out.append({
                "id": a.id,
                "role": a.label,
                "look": a.look,
                "status": status,
                "task": cur.description if cur else None,
                "project": cur.project if cur else None,
                "background": bool(cur.background) if cur else False,
                "since": cur.started_at if cur else None,
                "queued": max(0, len(running) - 1),
                "runs": st["runs"],
                "avgMs": round(st["total_ms"] / st["runs"]) if st["runs"] else 0,
                "lastDone": None if not last else {
                    "description": last.description,
                    "at": last.finished_at,
                    "durationMs": last.duration_ms,
                    "summary": last.summary,
                    "project": last.project,
                },
            })

        latest = sc.latest_session()
        boss_activity = max(latest.mtime, latest.last_activity) if latest else 0

        stalled = []
        shown_ids = {a.id for a in shown}
        for r in sc.open_runs.values():
            if r.agent_id not in shown_ids:
                continue
            age = now - r.started_at
            if age > stall_ms:
                label = next((a.label for a in shown if a.id == r.agent_id), r.agent_id)
                stalled.append({"kind": "run", "agentId": r.agent_id,
                                "label": label, "detail": r.description, "ageMs": age})
        for p in self.projects():
            for d in p["_directives"]:
                stalled.append({"kind": "directive", "agentId": None, "label": p["name"],
                                "detail": d["name"], "ageMs": now - d["mtime"]})
        stalled.sort(key=lambda s: s["ageMs"], reverse=True)

        return {
            "now": now,
            "title": self.cfg.title,
            "lang": self.cfg.lang,
            "workspace": str(self.cfg.workspace),
            "workspaceName": self.cfg.workspace.name,
            "transcriptDir": str(self.cfg.transcript_dir) if self.cfg.transcript_dir else None,
            "boss": {
                "status": "active" if now - boss_activity < self.cfg.away_ms else "away",
                "lastActivity": boss_activity or None,
                "lastPrompt": latest.last_prompt if latest else None,
                "sessionTitle": latest.title if latest else None,
            },
            "agents": agents_out,
            "summary": {
                "working": sum(1 for a in agents_out if a["status"] == "working"),
                "idle": sum(1 for a in agents_out if a["status"] == "idle"),
                "stalled": sum(1 for a in agents_out if a["status"] == "stalled"),
                "totalRuns": sum(a["runs"] for a in agents_out),
                "sessions": len(sc.sessions),
            },
            "stalled": stalled[:12],
            "timeline": [
                {
                    "agentId": h.agent_id,
                    "role": next((a.label for a in shown if a.id == h.agent_id), h.agent_id),
                    "description": h.description,
                    "project": h.project,
                    "at": h.finished_at,
                    "durationMs": h.duration_ms,
                    "ok": h.ok,
                    "summary": h.summary,
                }
                for h in sc.history[:20] if h.agent_id in shown_ids
            ],
            "projects": [{k: v for k, v in p.items() if not k.startswith("_")}
                         for p in self.projects()[:6]],
        }

    def build(self) -> Dict[str, Any]:  # type: ignore[no-redef]
        state = self._build()
        return self._apply_demo(state) if self.demo else state

    def _apply_demo(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """実ログが静かなときに、架空の稼働を重ねて見せる（スクリーンショット用）。

        実データは書き換えず、表示だけを差し替える。20秒ごとに担当が入れ替わるので、
        休憩室から出社して着席し、また戻る一連の動きを確認できる。
        """
        now = state["now"]
        agents = state["agents"]
        if not agents:
            return state

        tasks = DEMO_TASKS.get(self.cfg.lang, DEMO_TASKS["en"])
        rot = int(now / 20_000)
        stall_ms = self.cfg.stall_ms
        state["stalled"] = [s for s in state["stalled"] if s["kind"] != "run"]

        for i, (desc, ago) in enumerate(tasks):
            a = agents[(i * 2 + rot) % len(agents)]
            if a["status"] != "idle":
                continue
            a["status"] = "stalled" if ago > stall_ms else "working"
            a["task"] = desc
            a["since"] = now - ago
            a["project"] = None
            if a["status"] == "stalled":
                state["stalled"].insert(0, {
                    "kind": "run", "agentId": a["id"], "label": a["role"],
                    "detail": desc, "ageMs": ago,
                })

        state["summary"].update(
            working=sum(1 for a in agents if a["status"] == "working"),
            idle=sum(1 for a in agents if a["status"] == "idle"),
            stalled=sum(1 for a in agents if a["status"] == "stalled"),
        )
        state["demo"] = True
        return state
