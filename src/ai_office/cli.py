"""コマンドラインの入り口。"""

from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, config, roster
from .scanner import Scanner
from .server import serve
from .state import StateBuilder

BANNER = "🏢 AI Office"


def _t(lang: str, ja: str, en: str) -> str:
    return ja if lang == "ja" else en


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-office",
        description="Claude Code のサブエージェントの稼働状況を、ピクセルアートのオフィスとして表示します。",
    )
    p.add_argument("--root", metavar="PATH", help="監視するワークスペース(既定: カレントディレクトリ)")
    p.add_argument("--dir", metavar="PATH", help="セッションログのディレクトリを直接指定する")
    p.add_argument("--port", type=int, help="ポート番号(既定: 4321)")
    p.add_argument("--lang", choices=["ja", "en"], help="表示言語(既定: OSの設定)")
    p.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    p.add_argument("--check", action="store_true", help="検出結果だけ表示して終了する")
    p.add_argument("--demo", action="store_true",
                   help="架空の稼働を重ねて表示する(紹介用のスクリーンショットを撮るとき)")
    p.add_argument("--version", action="version", version=f"ai-office {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    cfg = config.load(args.root, args.dir, {"port": args.port, "lang": args.lang})
    lang = cfg.lang

    scanner = Scanner(directory=cfg.transcript_dir)

    print(BANNER)
    if not cfg.transcript_dir:
        print(_t(lang,
                 f"⚠ セッションログが見つかりません: {cfg.workspace}",
                 f"⚠ No Claude Code session logs found for: {cfg.workspace}"))
        print(_t(lang,
                 "  そのワークスペースで Claude Code を一度も使っていないか、別の場所にあります。",
                 "  Either Claude Code has never run there, or the logs live elsewhere."))
        print(_t(lang, "  --root か --dir で指定してください。", "  Point at them with --root or --dir."))
    else:
        t0 = time.time()
        scanner.scan()
        print(_t(lang,
                 f"  ログ読み込み完了 {time.time() - t0:.1f}秒"
                 f"（{len(scanner.sessions)}セッション / 実行記録{len(scanner.history)}件）",
                 f"  Scanned in {time.time() - t0:.1f}s "
                 f"({len(scanner.sessions)} sessions, {len(scanner.history)} runs)"))

    agents = roster.discover(cfg.workspace, cfg["agents"], cfg["hide"], sorted(scanner.seen_agent_ids))
    if not agents:
        print(_t(lang,
                 "⚠ エージェントが1人も見つかりません（.claude/agents/*.md がありません）",
                 "⚠ No agents found (.claude/agents/*.md is missing)"))

    builder = StateBuilder(cfg, scanner, agents, demo=args.demo)

    print(_t(lang, f"  ワークスペース: {cfg.workspace}", f"  Workspace: {cfg.workspace}"))
    print(_t(lang, f"  検出したエージェント: {len(agents)}人 "
                   f"({', '.join(a.label for a in agents[:6])}{'…' if len(agents) > 6 else ''})",
             f"  Agents found: {len(agents)}"))

    if args.check:
        return 0

    port = int(cfg["port"])
    try:
        httpd, hub, port = serve(builder, port, float(cfg["pollSeconds"]))
    except OSError as e:
        print(_t(lang,
                 f"✗ ポート {port} 付近に空きがありません: {e}。--port で別の番号を指定してください。",
                 f"✗ No free port near {port}: {e}. Try --port."))
        return 1

    if port != int(cfg["port"]):
        print(_t(lang,
                 f"  ポート {cfg['port']} は使用中だったので {port} で起動します"
                 f"（すでに ai-office が動いているかもしれません）",
                 f"  Port {cfg['port']} was busy, using {port} instead"))

    url = f"http://localhost:{port}"
    if args.demo:
        print(_t(lang, "  ※ デモ表示: 架空の稼働を重ねています", "  * demo mode: showing fabricated activity"))
    print()
    print(f"  {url}")
    print(_t(lang, "  終了は Ctrl+C", "  Ctrl+C to stop"))
    print()

    if not args.no_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(_t(lang, "\n終了しました。", "\nStopped."))
    finally:
        hub.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
