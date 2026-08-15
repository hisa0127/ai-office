"""エージェント名簿の自動生成。

`.claude/agents/*.md` を読んで社員名簿を作る。役職名・見た目は設定で上書きできるが、
何も設定しなくても「それらしい名前」と「他と被らない見た目」が自動で決まるようにしてある。
これが無いと、買った人の環境ではオフィスが空になる。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# 職業ごとの装い。色ではなくシルエットと持ち物で描き分ける（4色でも判別できる作り）
# kits は sprites.js の KITS、prop は PROPS のキーに対応する。
STYLES = [
    {"kits": ["long"],                 "prop": "clipboard"},
    {"kits": ["cap"],                  "prop": "binder"},
    {"kits": ["glasses"],              "prop": "papers"},
    {"kits": ["bun"],                  "prop": "palette"},
    {"kits": ["spiky", "phones"],      "prop": "laptop"},
    {"kits": ["ponytail", "glasses"],  "prop": "loupe"},
    {"kits": [],                       "prop": "bag"},
    {"kits": ["long", "glasses"],      "prop": "binder"},
    {"kits": ["cap", "phones"],        "prop": "laptop"},
    {"kits": ["ponytail"],             "prop": "clipboard"},
    {"kits": ["spiky"],                "prop": "papers"},
    {"kits": ["bun", "glasses"],       "prop": "loupe"},
]
KIT_NAMES = ["long", "cap", "glasses", "bun", "spiky", "ponytail", "phones"]

# バーチャルオフィス系のアバターに合わせ、彩度を上げた明るい配色にする
SHIRTS = ["#3fb08a", "#4a7fe0", "#9061d8", "#e86ba0", "#f0913c", "#3fb8d8", "#e05a5a", "#6cb83f"]
HAIRS = ["#8a5a34", "#3a3244", "#5c3d24", "#e08a3c", "#4a4a68", "#a8683c", "#2e2a34"]
SKINS = ["#ffd9b8", "#f5c79c", "#e8b48a", "#d99e78"]
PANTS = ["#3d4a70", "#37406b", "#4a3f6b", "#6b4a68", "#2f3550", "#5a4038"]
ACCENTS = ["#ffffff", "#eaf2ff", "#f6ecff", "#ffeef6", "#eafff2", "#eaf8ff", "#fff0e6"]
PROP_COLORS = ["#a87a4a", "#4a7fe0", "#d8c8a8", "#3fb8d8", "#3fb08a", "#e0e6f0", "#8a5a3c"]
CAPS = ["#e05a5a", "#4a7fe0", "#f0c03c", "#3fb08a"]


def _hash(s: str) -> int:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0x7FFFFFFF
    return h


@dataclass
class Agent:
    id: str
    label: str
    description: str = ""
    order: int = 999
    look: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "role": self.label, "look": self.look, "order": self.order}


def _front_matter(text: str) -> Dict[str, str]:
    """--- で囲まれた冒頭のメタデータを読む(1行 key: value のみ)"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out: Dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def _label_from(agent_id: str, fm: Dict[str, str]) -> str:
    """役職名を決める。説明文の冒頭が短ければそれを採用する

    多くのエージェント定義は description が「AI秘書。議事録の整理を…」のように
    役割名+句点で始まる。そこを拾えれば、設定なしでも日本語の役職名が出る。
    """
    for key in ("display_name", "label", "role", "title"):
        if fm.get(key):
            return fm[key]
    desc = fm.get("description", "")
    head = re.split(r"[。.:：\n]", desc, maxsplit=1)[0].strip()
    if head and len(head) <= 14 and not head.lower().startswith("use "):
        return head
    return agent_id


def _pick(table: list, agent_id: str, salt: int, used: set):
    """IDから決めつつ、同じオフィス内で先客がいれば次の候補へずらす。

    ハッシュだけだと似たID（ai-coder と ai-designer など）で衝突して
    同じ姿の社員が並ぶ。線形探索で必ず別の見た目になるようにする。
    """
    start = (_hash(agent_id) // salt) % len(table)
    for i in range(len(table)):
        idx = (start + i) % len(table)
        if idx not in used:
            used.add(idx)
            return table[idx]
    return table[start]


def _look_for(agent_id: str, override: dict, used: dict) -> dict:
    """見た目を決める。IDから決めるので、同じ環境では毎回同じ姿になる"""
    h = _hash(agent_id)
    style = _pick(STYLES, agent_id, 1, used.setdefault("style", set()))
    kits = override.get("kits")
    if kits is None:
        kits = [override["variant"]] if override.get("variant") else style["kits"]
    kits = [k for k in kits if k in KIT_NAMES]

    look = {
        "kits": kits,
        "prop": override.get("prop", style["prop"]),
        "shirt": override.get("shirt") or _pick(SHIRTS, agent_id, 7, used.setdefault("shirt", set())),
        "hair": override.get("hair") or _pick(HAIRS, agent_id, 13, used.setdefault("hair", set())),
        "skin": override.get("skin") or SKINS[(h // 17) % len(SKINS)],
        "pants": override.get("pants") or PANTS[(h // 19) % len(PANTS)],
        "accent": override.get("accent") or ACCENTS[(h // 23) % len(ACCENTS)],
        "propColor": override.get("propColor") or PROP_COLORS[(h // 29) % len(PROP_COLORS)],
    }
    if "cap" in kits:
        look["cap"] = override.get("cap") or CAPS[(h // 31) % len(CAPS)]
    return look


def discover(workspace: Path, cfg_agents: dict, hide: List[str],
             extra_ids: Optional[List[str]] = None) -> List[Agent]:
    """`.claude/agents/*.md` + ログに出てきたIDから名簿を作る"""
    found: Dict[str, Dict[str, str]] = {}

    for base in (workspace / ".claude" / "agents", Path.home() / ".claude" / "agents"):
        if not base.is_dir():
            continue
        for md in sorted(base.glob("*.md")):
            agent_id = md.stem
            if agent_id in found:
                continue  # 案件側の定義を優先する
            try:
                fm = _front_matter(md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                fm = {}
            found[fm.get("name") or agent_id] = fm

    # 定義ファイルが無くてもログに出てきたものは実在するので拾う
    for agent_id in (extra_ids or []):
        found.setdefault(agent_id, {})

    agents: List[Agent] = []
    used: Dict[str, set] = {}
    for i, (agent_id, fm) in enumerate(sorted(found.items())):
        ov = dict(cfg_agents.get(agent_id) or {})
        if agent_id in hide or ov.get("hidden"):
            continue
        agents.append(Agent(
            id=agent_id,
            label=ov.get("label") or _label_from(agent_id, fm),
            description=fm.get("description", ""),
            order=int(ov["order"]) if str(ov.get("order", "")).isdigit() else 100 + i,
            look=_look_for(agent_id, ov, used),
        ))

    agents.sort(key=lambda a: (a.order, a.id))
    return agents
