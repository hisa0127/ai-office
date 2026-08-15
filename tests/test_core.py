"""ai-office の中核部分のテスト。

    cd products/ai-office && python3 -m unittest discover -s tests -v
"""

import json
import unittest.mock
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ai_office import roster  # noqa: E402
from ai_office.scanner import Scanner  # noqa: E402


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def agent_call(tool_id: str, agent: str, desc: str, prompt: str = "", ts: str = "2026-08-14T00:00:00.000Z"):
    return _line(type="assistant", timestamp=ts, message={
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tool_id, "name": "Agent",
                     "input": {"subagent_type": agent, "description": desc, "prompt": prompt}}],
    })


def agent_result(tool_id: str, text: str, ts: str = "2026-08-14T00:05:00.000Z"):
    return _line(type="user", timestamp=ts, message={
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_id,
                     "content": [{"type": "text", "text": text}]}],
    })


class TestScanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "session-1.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_running_agent(self):
        self.log.write_text(agent_call("t1", "ai-coder", "トップページを実装"), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1)
        run = sc.runs_for("ai-coder")[0]
        self.assertEqual(run.description, "トップページを実装")
        self.assertIn("ai-coder", sc.seen_agent_ids)

    def test_pairs_result_and_closes_run(self):
        self.log.write_text(agent_call("t1", "ai-coder", "実装"), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "できました"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0, "結果が来たら実行中から外れる")
        self.assertEqual(len(sc.history), 1)
        self.assertEqual(sc.history[0].duration_ms, 5 * 60 * 1000)
        self.assertEqual(sc.stats["ai-coder"]["runs"], 1)

    def test_incremental_read_with_japanese(self):
        """日本語(マルチバイト)を挟んで追記しても、読み位置がずれないこと"""
        self.log.write_text(agent_call("t1", "ai-secretary", "議事録を整理する"), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(list(sc._cursors.values())[0]["offset"], self.log.stat().st_size)

        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_call("t2", "ai-designer", "デザイン案を作る（日本語の説明つき）"))
        sc.scan()
        self.assertEqual({r.agent_id for r in sc.open_runs.values()}, {"ai-secretary", "ai-designer"})

    def test_partial_line_is_not_lost(self):
        """書きかけの行は次の走査まで持ち越す"""
        payload = agent_call("t1", "ai-pm", "WBSを切る")
        head, tail = payload[:40], payload[40:]
        self.log.write_text(head, encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(tail)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1)

        # さらに追記しても、持ち越し分を二重に読まないこと
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_call("t2", "ai-tester", "テストする"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 2)
        self.assertEqual(len(sc.runs_for("ai-pm")), 1, "持ち越した行を二度読んでいる")
        self.assertEqual(len(sc.runs_for("ai-tester")), 1)

    def test_ignores_unrelated_lines(self):
        self.log.write_text(
            _line(type="assistant", message={"role": "assistant", "content": [
                {"type": "tool_use", "id": "x", "name": "Read", "input": {"file_path": "/a"}}]}),
            encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0)

    def test_internal_metadata_is_not_shown(self):
        """バックグラウンド起動の内部メタデータを成果として表示しない"""
        self.log.write_text(agent_call("t1", "ai-coder", "実装"), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result(
                "t1",
                "Async agent launched successfully. (This tool result is internal metadata "
                "— never quote or paste any part of it into a user-facing message.)"))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(sc.history[0].summary, "", "内部メタデータが成果として残っている")

    def test_normal_result_is_kept(self):
        self.log.write_text(agent_call("t1", "ai-coder", "実装"), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "05_src/index.html を作成しました"))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertIn("index.html", sc.history[0].summary)

    def test_extracts_project_name(self):
        self.log.write_text(
            agent_call("t1", "ai-coder", "実装", prompt="`projects/2026-07_sample_コーポレートサイト/` を見て"),
            encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(sc.runs_for("ai-coder")[0].project, "2026-07_sample_コーポレートサイト")


class TestServerPort(unittest.TestCase):
    def test_falls_back_to_next_free_port(self):
        """ポートが埋まっていてもエラーで終わらず、次の番号で起動すること"""
        import socket
        from ai_office.server import serve

        blocker = socket.socket()
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        taken = blocker.getsockname()[1]

        httpd = None
        try:
            httpd, hub, used = serve(_dummy_builder(), taken, 60.0)
            self.assertNotEqual(used, taken, "埋まっているポートを掴んでいる")
            self.assertGreater(used, taken)
        finally:
            blocker.close()
            if httpd:
                httpd.server_close()


def _dummy_builder():
    class B:
        scanner = Scanner(directory=None)

        def build(self):
            return {"now": 0}
    return B()


class TestRoster(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        (self.ws / ".claude" / "agents").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _agent(self, name, description="", extra=""):
        (self.ws / ".claude" / "agents" / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n本文\n", encoding="utf-8")

    def test_label_from_japanese_description(self):
        """説明文の冒頭が役職名になっている定義が多いので、そこを拾う"""
        self._agent("ai-secretary", "AI秘書。議事録・ヒアリングメモの構造化を行う。")
        got = roster.discover(self.ws, {}, [])
        self.assertEqual(got[0].label, "AI秘書")

    def test_label_falls_back_to_id(self):
        self._agent("weird-agent", "Use this agent when you need to do a very long thing indeed.")
        got = roster.discover(self.ws, {}, [])
        self.assertEqual(got[0].label, "weird-agent")

    def test_config_overrides_label_and_look(self):
        self._agent("ai-pm", "AI PM。進行管理。")
        got = roster.discover(self.ws, {"ai-pm": {"label": "進行役", "shirt": "#123456",
                                                  "kits": ["cap"], "prop": "binder"}}, [])
        self.assertEqual(got[0].label, "進行役")
        self.assertEqual(got[0].look["shirt"], "#123456")
        self.assertEqual(got[0].look["kits"], ["cap"])
        self.assertEqual(got[0].look["prop"], "binder")
        self.assertIn("cap", got[0].look, "capキットには帽子色が付くこと")

    def test_unknown_kit_is_dropped(self):
        """設定に知らないキット名が書かれても描画側で落ちないこと"""
        self._agent("x", "X。")
        got = roster.discover(self.ws, {"x": {"kits": ["long", "nonexistent"]}}, [])
        self.assertEqual(got[0].look["kits"], ["long"])

    def test_hidden_agents_excluded(self):
        self._agent("a", "A。")
        self._agent("b", "B。")
        self.assertEqual([x.id for x in roster.discover(self.ws, {}, ["b"])], ["a"])

    def test_look_is_stable(self):
        self._agent("ai-coder", "AIコーダー。実装する。")
        a = roster.discover(self.ws, {}, [])[0]
        b = roster.discover(self.ws, {}, [])[0]
        self.assertEqual(a.look, b.look, "同じIDなら毎回同じ見た目になること")
        for kit in a.look["kits"]:
            self.assertIn(kit, roster.KIT_NAMES)
        self.assertTrue(a.look["prop"] is None or isinstance(a.look["prop"], str))

    def test_everyone_looks_different(self):
        """同じオフィスに同じ姿の社員が並ばないこと"""
        for i in range(10):
            self._agent(f"ai-agent-{i}", f"エージェント{i}。")
        got = roster.discover(self.ws, {}, [])
        combos = [(tuple(a.look["kits"]), a.look["prop"]) for a in got]
        self.assertEqual(len(set(combos)), len(combos), f"シルエットが重複: {combos}")
        # 服の色は色数が上限。用意した数までは重複しないこと
        shirts = [a.look["shirt"] for a in got]
        self.assertEqual(len(set(shirts)), min(len(got), len(roster.SHIRTS)), "服の色が無駄に重複")

    def test_agents_seen_only_in_logs_are_included(self):
        """定義ファイルが無くてもログに出てきたエージェントは実在する"""
        got = roster.discover(self.ws, {}, [], extra_ids=["general-purpose"])
        self.assertEqual([x.id for x in got], ["general-purpose"])


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
