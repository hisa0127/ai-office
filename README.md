# AI Office

Watch your Claude Code subagents work in a pixel-art office.

The office has a **work room** and a **break room**, and where someone is *is* their status.
Start an agent and they walk in from the break room, sit at their desk and start typing. Finish,
and they head back to the sofa. When one stops responding, their screen turns red. One glance
tells you who is busy, who is free, and what is stuck — no labels to read.

```bash
pipx install ai-office-dashboard
cd your-project
ai-office
```

（開発版は `pipx install git+https://github.com/hisa0127/ai-office.git`）

The command is `ai-office`; the package on PyPI is `ai-office-dashboard`.

Everything runs on `127.0.0.1`. **No data ever leaves your machine** — the tool only reads the
session logs Claude Code already writes to `~/.claude/projects/`.

Free and unrestricted — no agent limit, no account, no telemetry.

---

# AI Office（日本語）

Claude Code のサブエージェントの稼働状況を、ピクセルアートのオフィスとして表示します。

## これは何か

Claude Code でマルチエージェントを回していると、「誰が今動いていて、誰が空いていて、何が止まって
いるのか」がチャットログからは分かりません。AI Office はそれをオフィスの俯瞰図にします。

オフィスは**作業部屋**と**休憩室**に分かれています。**どちらの部屋にいるかが、そのまま状態です。**

- **作業部屋の自席にいる＝仕事中**。エージェントが起動されると休憩室から歩いてきて着席し、タイピングを始めます
- **休憩室にいる＝手が空いている**。仕事が終わると席を立ち、休憩室に戻ってソファに座ります
- **画面が赤い＝止まっている**。15分以上応答が返らないエージェントは滞留として警告します
- 吹き出しには、そのエージェントが**いま何をしているか**（起動時の指示内容）が出ます。
  待機中は吹き出しを出しません（休憩室にいること自体が「空いている」の表示なので、ラベルが要りません）

## インストール

```bash
pipx install ai-office-dashboard    # または: uv tool install ai-office-dashboard

# 最新のソースから入れる場合
pipx install git+https://github.com/hisa0127/ai-office.git
```

Python 3.9 以上。依存パッケージはありません（標準ライブラリのみ）。
PyPI上の名前は `ai-office-dashboard`、起動コマンドは `ai-office` です。

## 使い方

```bash
cd ~/work/my-project     # Claude Code を使っているディレクトリ
ai-office                # → http://localhost:4321 が開きます
```

| オプション | 説明 |
|---|---|
| `--root PATH` | 監視するワークスペース（既定: カレントディレクトリ） |
| `--dir PATH` | セッションログの場所を直接指定する |
| `--port N` | ポート番号（既定: 4321。埋まっていたら自動で次の空きを使います） |
| `--lang ja\|en` | 表示言語（既定: OSの設定） |
| `--no-browser` | ブラウザを自動で開かない |
| `--check` | 検出結果だけ表示して終了する（設定確認用） |
| `--demo` | 架空の稼働を重ねて表示する（紹介用のスクリーンショットを撮るとき） |

## 何を読んでいるか

Claude Code は会話の履歴を `~/.claude/projects/<ワークスペース>/*.jsonl` に追記しています。
サブエージェントの起動はここに `Agent` ツールの呼び出しとして残り、完了すると同じ `tool_use_id`
を持つ結果が現れます。AI Office はこの**起動と完了の対**を追跡しているだけです。

| 表示 | 判定 |
|---|---|
| 作業部屋で着席 | 起動の記録があり、まだ結果が返っていない |
| 休憩室にいる | 実行中のものがない |
| 滞留（赤） | 実行中のまま15分以上結果が返っていない |
| あなた＝在席 | セッションログが直近5分以内に更新されている |

ログは追記された分だけを読みます（ファイルごとにバイト位置を記憶）。数百MBのログでも起動は1秒未満です。

## 設定（任意）

何も設定しなくても、`.claude/agents/*.md` から自動でエージェントを検出し、説明文の冒頭から役職名を
推測し、IDから見た目を決めます。変えたいときだけ `.ai-office.json` をワークスペースに置いてください。

```json
{
  "lang": "ja",
  "title": "うちのAI組織",
  "port": 4321,
  "stallMinutes": 15,
  "hide": ["general-purpose"],
  "agents": {
    "ai-secretary": { "label": "AI秘書", "order": 1,
                      "kits": ["long"], "prop": "clipboard", "shirt": "#3f7d6a" },
    "ai-coder":     { "label": "AIコーダー", "order": 2,
                      "kits": ["spiky", "phones"], "prop": "laptop" }
  }
}
```

- `kits`（髪型・装備、複数可）: `long` / `cap` / `glasses` / `bun` / `spiky` / `ponytail` / `phones`
- `prop`（持ち物）: `clipboard` / `binder` / `papers` / `palette` / `laptop` / `loupe` / `bag`
- 色: `shirt` / `hair` / `skin` / `pants` / `accent` / `cap` / `propColor`
- マシン共通の設定は `~/.config/ai-office/config.json` に置けます

## キャラクター

24×32ドット・4方向（正面／背面／左右）のスプライトです。バーチャルオフィス系のアバターに寄せて、
**頭を大きめ（約1.8頭身）・フラット塗り・大きい目**にしてあります。輪郭は黒縁ではなく
「隣の色を暗くした色つき輪郭」なので、縁が硬くならずに背景から浮きます。
歩く方向に体が向き、足を入れ替える4コマで歩行します。休憩室のソファでは座ります。

**社員の描き分けは色ではなくシルエットと持ち物で行います。** 長髪・キャップ・メガネ・おだんご・
ツンツン頭＋ヘッドホン・ポニーテールの組み合わせに、クリップボード／バインダー／書類／パレット／
ノートPC／虫眼鏡／カバンを持たせ、同じオフィス内で姿が重複しないよう自動で割り当てます
（あなた自身は王冠と杖の「王様」で固定）。

`devtools/sprite-preview.html` をブラウザで開くと、全キャラクターの4方向と歩行コマを一覧できます。

## 料金

無料です。エージェント数の制限も、アカウント登録も、利用状況の送信もありません。MITライセンスです。

## プライバシー

- サーバーは `127.0.0.1` にのみ待ち受けます。LANからも見えません
- 会話の内容を外部に送信することはありません。外部との通信はデザイン上ゼロです
- 吹き出しに出るのは、エージェント起動時の一行の説明（`description`）だけです
- 唯一の外部参照は、画面のドット絵フォント（Google Fonts）です。オフラインでも通常のフォントで動きます

## うまく動かないとき

**「セッションログが見つかりません」**
そのディレクトリで Claude Code をまだ使っていない可能性があります。`ai-office --check` で
検出結果を確認し、`--root` か `--dir` で場所を指定してください。

**「エージェントが1人も見つかりません」**
`.claude/agents/*.md` が必要です。サブエージェントを定義していない場合、ログに現れたエージェントが
自動的に追加されます（一度でも起動していれば表示されます）。

**ポート 4321 が埋まっている**
自動で 4322、4323… と空きを探して起動し、使ったポートを表示します。前に起動した `ai-office` が
残っていることが多いので、不要なら止めてください（`lsof -ti tcp:4321 | xargs kill`）。

**キャラクターが動かない**
ブラウザのタブが裏にあると、ブラウザ側の仕様でアニメーションが止まります（CPU節約のため）。
タブを前面に戻すと再開します。

## ライセンス

MIT License。`LICENSE` を参照してください。

## 免責

本ソフトウェアは Claude Code が出力するログの形式に依存しています。Anthropic 社による仕様変更で
動作しなくなる可能性があります。Anthropic PBC が開発・承認したものではありません。
Claude および Claude Code は Anthropic PBC の商標です。
