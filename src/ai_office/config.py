"""設定の読み込みとパス解決。

設定は 2 か所を重ねて読む(後ろが優先):
    1. ~/.config/ai-office/config.json      … そのマシン共通
    2. <ワークスペース>/.ai-office.json      … その案件だけ

いずれも無くて構わない。無ければ全部自動判定で動く。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


def config_dir() -> Path:
    """OSごとの設定ディレクトリ"""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai-office"


DEFAULTS: Dict[str, Any] = {
    "lang": None,               # None なら OS のロケールから推定
    "title": None,              # None ならワークスペース名
    "port": 4321,
    "pollSeconds": 2,
    "stallMinutes": 15,         # 応答が返らないまま滞留とみなす時間
    "awayMinutes": 5,           # 社長(メイン会話)が離席とみなす時間
    "agents": {},               # id -> {label, variant, shirt, hair, order, hidden}
    "hide": [],                 # 表示しないエージェントID
    "projects": {
        "enabled": True,
        "dir": "projects",
        "projectFile": "_project.md",
        "statusFile": "_status.md",
        "directivesDir": "_directives",
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠ 設定ファイルを読めませんでした ({path}): {e}")
        return {}


def slug_for_path(p: Path) -> str:
    """Claude Code がセッションログの置き場に使うディレクトリ名(英数字以外は - )"""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(p))


def find_transcript_dir(workspace: Path, explicit: Optional[str] = None) -> Optional[Path]:
    """ワークスペースに対応するセッションログのディレクトリを探す"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        return p if p.exists() else None

    base = Path.home() / ".claude" / "projects"
    guess = base / slug_for_path(workspace)
    if guess.exists():
        return guess
    if not base.exists():
        return None

    # 末尾一致(ワークスペースを移動した場合など)。複数あれば最終更新が新しいもの
    tail = slug_for_path(Path(workspace.name))
    cands = [d for d in base.iterdir() if d.is_dir() and d.name.endswith(tail)]
    if cands:
        return max(cands, key=lambda d: d.stat().st_mtime)
    return None


@dataclass
class Config:
    workspace: Path
    transcript_dir: Optional[Path]
    data: Dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    @property
    def lang(self) -> str:
        if self.data.get("lang") in ("ja", "en"):
            return self.data["lang"]
        loc = (os.environ.get("LANG") or os.environ.get("LC_ALL") or "").lower()
        return "ja" if loc.startswith("ja") else "en"

    @property
    def title(self) -> str:
        return self.data.get("title") or self.workspace.name

    @property
    def stall_ms(self) -> int:
        return int(float(self.data["stallMinutes"]) * 60_000)

    @property
    def away_ms(self) -> int:
        return int(float(self.data["awayMinutes"]) * 60_000)

    @property
    def projects_dir(self) -> Optional[Path]:
        pc = self.data.get("projects") or {}
        if not pc.get("enabled", True):
            return None
        d = self.workspace / pc.get("dir", "projects")
        return d if d.is_dir() else None


def load(workspace: Optional[str] = None, transcript_dir: Optional[str] = None,
         overrides: Optional[dict] = None) -> Config:
    ws = Path(workspace).expanduser().resolve() if workspace else Path.cwd().resolve()
    data = _deep_merge(DEFAULTS, _read_json(config_dir() / "config.json"))
    data = _deep_merge(data, _read_json(ws / ".ai-office.json"))
    data = _deep_merge(data, {k: v for k, v in (overrides or {}).items() if v is not None})
    return Config(workspace=ws, transcript_dir=find_transcript_dir(ws, transcript_dir), data=data)
