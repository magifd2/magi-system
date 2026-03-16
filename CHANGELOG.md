# Changelog

このプロジェクトの変更履歴です。[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) 形式に準拠し、[Semantic Versioning](https://semver.org/lang/ja/) に従います。

---

## [0.3.0] - 2026-03-17

### Added
- コマンドラインオプション対応 (`-t/--topic`, `-s/--save`, `-o/--output`)
- 収束後の締めくくりフェーズ：全ペルソナが最終コメントを述べてから終了
- `extra_instruction` パラメータを `LLMClient.chat_with_persona` に追加

### Fixed
- `rich.Prompt` / `rich.Confirm` をビルトイン `input()` ベースのヘルパーに置き換え（マルチバイト文字入力の不具合修正）

---

## [0.2.0] - 2026-03-17

### Added
- 議論ログと最終レポートの Markdown ファイル保存機能 (`src/magi/save.py`)
- 保存ファイル名：`magi_YYYYMMDD_HHMMSS_<トピック>.md`

### Fixed
- `screen=True` に変更し、議論中の表示スクロールを抑止
- `Layout` による固定分割レイアウトに刷新（ヘッダー固定 / 会話ログ可変 / ペルソナパネル固定）
- ペルソナパネルを横並びから縦積み（左：会話ログ、右：ペルソナ3列縦）に変更
- 会話ログを降順表示（最新が上）に変更し、パネルのクロップで最新発言が見えなくなる問題を修正

---

## [0.1.0] - 2026-03-17

### Added
- 初期実装
- MELCHIOR / BALTHASAR / CASPER の3ペルソナによる多角的議論システム
- OpenAI API 互換エンドポイント (LM Studio) によるLLM呼び出し
- ペルソナごとの記憶・感情状態・収束判断の管理
- Rich によるリアルタイムモニタリング表示
- 2ペルソナ以上の収束判断による議論自動終了
- LLM による最終レポート自動生成（フォールバックあり）
- uv による仮想環境管理
