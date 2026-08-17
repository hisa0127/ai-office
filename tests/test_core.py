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

from ai_office import config, roster  # noqa: E402
from ai_office.scanner import Scanner  # noqa: E402


def _line(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def agent_call(tool_id: str, agent: str, desc: str, prompt: str = "", ts: str = "2026-08-14T00:00:00.000Z",
               background: bool = False):
    return _line(type="assistant", timestamp=ts, message={
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tool_id, "name": "Agent",
                     "input": {"subagent_type": agent, "description": desc, "prompt": prompt,
                               "run_in_background": background}}],
    })


def _note_body(tool_id: str, status: str, result: str) -> str:
    return (
        "<task-notification>\n"
        f"<task-id>bg-1</task-id>\n"
        f"<tool-use-id>{tool_id}</tool-use-id>\n"
        f"<status>{status}</status>\n"
        f"<summary>Agent finished</summary>\n"
        f"<result>{result}</result>\n"
        "</task-notification>"
    )


def task_note(tool_id: str, status: str = "completed", result: str = "終わりました",
              ts: str = "2026-08-14T00:30:00.000Z", shape: str = "user"):
    """バックグラウンド起動の本当の完了通知。tool_result より後に届く。

    同じ通知が3つの形でログに現れる(実ログで確認済み)。shape で切り替える。
    """
    body = _note_body(tool_id, status, result)
    if shape == "user":            # 失敗時に観測された形
        return _line(type="user", timestamp=ts, message={"role": "user", "content": body})
    if shape == "queue":           # 成功時に観測された形
        return _line(type="queue-operation", operation="enqueue", timestamp=ts, content=body)
    if shape == "attachment":      # 成功時に観測された形
        return _line(type="attachment", timestamp=ts,
                     attachment={"type": "queued_command", "commandMode": "task-notification",
                                 "prompt": body})
    raise ValueError(shape)


def agent_call_no_flag(tool_id: str, agent: str, desc: str, ts: str = "2026-08-14T00:00:00.000Z"):
    """run_in_background を省略した起動。**現行Agentツールの既定であり、省略時は非同期**"""
    return _line(type="assistant", timestamp=ts, message={
        "role": "assistant",
        "content": [{"type": "tool_use", "id": tool_id, "name": "Agent",
                     "input": {"subagent_type": agent, "description": desc}}],
    })


def agent_result(tool_id: str, text: str, ts: str = "2026-08-14T00:05:00.000Z",
                 is_error: bool = False, is_async: bool = False):
    body = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error,
                     "content": [{"type": "text", "text": text}]}],
    }
    extra = {"toolUseResult": {"isAsync": True, "status": "async_launched"}} if is_async else {}
    return _line(type="user", timestamp=ts, message=body, **extra)


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

    def test_background_result_does_not_close_run(self):
        """バックグラウンド起動の tool_result は「起動しました」の通知。まだ働いている"""
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "Async agent launched successfully.", ts="2026-08-14T00:00:01.000Z"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1, "起動直後の通知で退勤させない")
        self.assertEqual(len(sc.history), 0)

    def test_background_closes_on_task_notification(self):
        """本当の完了は <task-notification> で届く。tool_use_id で対応づける"""
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "Async agent launched successfully.", ts="2026-08-14T00:00:01.000Z"))
            f.write(task_note("t1", result="要件定義を書きました"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0, "完了通知で退勤する")
        self.assertEqual(len(sc.history), 1)
        self.assertTrue(sc.history[0].ok)
        self.assertEqual(sc.history[0].summary, "要件定義を書きました")
        self.assertEqual(sc.history[0].duration_ms, 30 * 60 * 1000, "起動から完了通知までを稼働時間とする")

    def test_background_failure_is_recorded_as_failure(self):
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("t1", status="failed", result="停止しました"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0)
        self.assertFalse(sc.history[0].ok)

    def test_background_closes_on_every_notification_shape(self):
        """通知は3つの形でログに来る。どれか1つでも取りこぼすと永久に退勤しなくなる"""
        for shape in ("user", "queue", "attachment"):
            with self.subTest(shape=shape):
                log = self.dir / f"session-{shape}.jsonl"
                log.write_text(agent_call("t1", "ai-director", "要件定義", background=True),
                               encoding="utf-8")
                sc = Scanner(directory=self.dir)
                sc.scan()
                with log.open("a", encoding="utf-8") as f:
                    f.write(task_note("t1", shape=shape))
                sc.scan()
                self.assertEqual(len(sc.open_runs), 0, f"{shape} 形式の通知で退勤すること")
                log.unlink()

    def test_duplicate_notification_counted_once(self):
        """同じ通知が queue と attachment の2行で来ても、稼働は1回だけ数える"""
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("t1", shape="queue"))
            f.write(task_note("t1", shape="attachment"))
        sc.scan()
        self.assertEqual(len(sc.history), 1, "二重計上しない")
        self.assertEqual(sc.stats["ai-director"]["runs"], 1)

    def test_quoted_notification_in_own_reply_is_ignored(self):
        """自分の発言が通知を引用していても、それで退勤させない"""
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(_line(type="assistant", timestamp="2026-08-14T00:20:00.000Z", message={
                "role": "assistant",
                "content": [{"type": "text",
                             "text": "通知の形はこうです:\n" + _note_body("t1", "completed", "説明用")}],
            }))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1, "引用で退勤させない")

    def test_internal_metadata_is_not_shown_as_result(self):
        """内部メタデータを成果として表示しない。

        旧テストが握っていた性質。非同期判定の変更で入力形状が変わったので、
        いまも通る経路(起動失敗)に付け替えて残す。消すとマーカー除去を壊しても誰も気づかない。
        """
        self.log.write_text(agent_call("t1", "ai-coder", "実装", background=True), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result(
                "t1",
                "Agent launched successfully. (This tool result is internal metadata "
                "— never quote or paste any part of it into a user-facing message.)",
                ts="2026-08-14T00:00:01.000Z", is_error=True))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(sc.history[0].summary, "", "内部メタデータが成果として残っている")

    def test_notification_inside_command_output_is_ignored(self):
        """コマンド出力に本物の通知が混ざっていても、それで退勤させない。

        実ログに存在する形(tool_result の中に本物の tool-use-id と status が入る)。
        message.content が list か str かで弁別している。ここを外すと稼働中が誤退勤する。
        """
        self.log.write_text(agent_call("t1", "ai-coder", "実装", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(_line(type="user", timestamp="2026-08-14T00:10:00.000Z", message={
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "別のID",
                             "content": [{"type": "text",
                                          "text": "grepの結果:\n" + _note_body("t1", "failed", "x")}]}],
            }))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1, "コマンド出力に含まれる通知で退勤させない")
        self.assertEqual(len(sc.history), 0)

    def test_killed_is_not_counted_as_success(self):
        """途中停止(killed)を成功として集計しない。値は実ログで確認したもの"""
        self.log.write_text(agent_call("t1", "ai-director", "実験", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("t1", status="killed", result="停止されました", shape="queue"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0, "停止でも退勤はする")
        self.assertFalse(sc.history[0].ok, "killed を成功にしない")

    def test_unknown_status_is_not_counted_as_success(self):
        """将来 status が増えたとき、黙って成功に混ぜない(気づける方へ倒す)"""
        self.log.write_text(agent_call("t1", "ai-director", "実験", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("t1", status="timed_out", shape="queue"))
        sc.scan()
        self.assertFalse(sc.history[0].ok)

    def test_completed_is_success(self):
        self.log.write_text(agent_call("t1", "ai-director", "実験", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("t1", status="completed", shape="queue"))
        sc.scan()
        self.assertTrue(sc.history[0].ok)

    def test_notification_for_unknown_id_is_ignored(self):
        """別セッションの通知が混ざっても、知らない tool_use_id なら無視する"""
        self.log.write_text(agent_call("t1", "ai-coder", "実装", background=True), encoding="utf-8")
        sc = Scanner(directory=self.dir)
        sc.scan()
        with self.log.open("a", encoding="utf-8") as f:
            f.write(task_note("よその-id"))
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1, "他人の通知で退勤させない")
        self.assertEqual(len(sc.history), 0)

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

    def test_omitted_flag_is_treated_as_async(self):
        """run_in_background の省略は「同期」ではない。**省略時が非同期の既定**

        入力フラグを根拠にすると、既定の起動がすべて0秒で退勤扱いになる。
        非同期かどうかは結果側の isAsync / status=async_launched を正とする。
        """
        self.log.write_text(agent_call_no_flag("t1", "ai-coder", "実装"), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result(
                "t1",
                "Async agent launched successfully. (This tool result is internal metadata "
                "— never quote or paste any part of it into a user-facing message.)",
                ts="2026-08-14T00:00:01.000Z", is_async=True))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 1, "既定(省略)の起動を0秒で退勤させない")
        self.assertEqual(len(sc.history), 0)

    def test_omitted_flag_closes_on_notification(self):
        """省略起動でも、完了通知が来れば正しく実働時間で退勤する"""
        self.log.write_text(agent_call_no_flag("t1", "ai-coder", "実装"), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "Async agent launched successfully.",
                                 ts="2026-08-14T00:00:01.000Z", is_async=True))
            f.write(task_note("t1", shape="queue"))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0)
        self.assertEqual(sc.history[0].duration_ms, 30 * 60 * 1000, "0秒ではなく実働30分で記録する")

    def test_launch_failure_closes_immediately(self):
        """起動そのものが失敗したら通知は永久に来ない。その場で失敗として閉じる"""
        self.log.write_text(agent_call("t1", "ai-director", "要件定義", background=True), encoding="utf-8")
        with self.log.open("a", encoding="utf-8") as f:
            f.write(agent_result("t1", "Agent type 'ai-director' not found.",
                                 ts="2026-08-14T00:00:01.000Z", is_error=True))
        sc = Scanner(directory=self.dir)
        sc.scan()
        self.assertEqual(len(sc.open_runs), 0, "起動失敗を在席のまま放置しない")
        self.assertFalse(sc.history[0].ok)

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


class TestLogDirDetection(unittest.TestCase):
    """ログ置き場の特定。ディレクトリ名の規則はOSで変わりうるので、
    名前が一致しなくても中身の cwd で見つけられること"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.base = self.home / ".claude" / "projects"
        self.base.mkdir(parents=True)
        self.ws = self.home / "work" / "myproject"
        self.ws.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _log_dir(self, name, cwd):
        d = self.base / name
        d.mkdir()
        (d / "s1.jsonl").write_text(
            _line(type="assistant", cwd=str(cwd), message={"role": "assistant", "content": []}),
            encoding="utf-8")
        return d

    def test_finds_by_slug(self):
        want = self._log_dir(config.slug_for_path(self.ws), self.ws)
        with unittest.mock.patch.object(Path, "home", staticmethod(lambda: self.home)):
            self.assertEqual(config.find_transcript_dir(self.ws), want)

    def test_finds_by_cwd_when_name_differs(self):
        """Windows等で命名規則が違っても、ログ本文の cwd で見つかること"""
        want = self._log_dir("C--totally-different-naming", self.ws)
        self._log_dir("some-other-project", self.home / "work" / "other")
        with unittest.mock.patch.object(Path, "home", staticmethod(lambda: self.home)):
            self.assertEqual(config.find_transcript_dir(self.ws), want)

    def test_returns_none_when_absent(self):
        self._log_dir("unrelated", self.home / "work" / "other")
        with unittest.mock.patch.object(Path, "home", staticmethod(lambda: self.home)):
            self.assertIsNone(config.find_transcript_dir(self.ws))


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
