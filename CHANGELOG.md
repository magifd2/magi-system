# Changelog

このプロジェクトの変更履歴です。[Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) 形式に準拠し、[Semantic Versioning](https://semver.org/lang/ja/) に従います。

---

## [0.27.5] - 2026-03-18

### Changed
- `llm.py` — LLMエンドポイント・APIキー・モデルを環境変数 `MAGI_BASE_URL` / `MAGI_API_KEY` / `MAGI_MODEL` で上書き可能にした。未設定時は従来のデフォルト値にフォールバック。

---

## [0.27.4] - 2026-03-18

### Fixed
- `discussion.py` — ファイナルレポート生成時の `max_tokens` を 4096 → 8192 に拡大。長い議論のレポートが途中で打ち切られる問題を修正。

---

## [0.27.3] - 2026-03-17

### Fixed
- `display.py` — ヘッダーの「■ 議論収束」表示でRichマークアップタグが生テキストとして表示される問題を修正。`Text.append()` は markup を解釈しないため `Text.append_text(Text.from_markup(...))` に変更。

---

## [0.27.2] - 2026-03-17

### Fixed
- `llm.py` — ペルソナ応答の `max_tokens` を 2048 → 4096 に再拡大。2048 でも日本語 opinion が長くなると依然として打ち切られるケースがあったため。opinion 文字数制限は 200文字程度のままとし、議論コンテキストの損失を避ける。

---

## [0.27.1] - 2026-03-17

### Fixed
- `llm.py` — ペルソナ応答の `max_tokens` を 1024 → 2048 に拡大。日本語1文字あたり2〜3トークン消費するため、opinion 200文字＋emotions＋convergence_reason の合計が 1024 を超えてJSONが途中で打ち切られていた問題を修正。

---

## [0.27.0] - 2026-03-17

### Added
- `llm.py` — デバッグログ機能を追加。環境変数 `MAGI_DEBUG=1` を設定すると、LLMの生出力および各パース段階（RAW・CLEAN_RAW・JSON_STR・OPINION_RAW・OPINION_CLEANED など）をカレントディレクトリの `magi_debug.log` に記録する。Gemini / litellm-proxy 経由時の JSON 混入問題の原因特定に使用する。実行例: `MAGI_DEBUG=1 uv run magi -t "トピック"`

---

## [0.26.0] - 2026-03-17

### Fixed
- `llm.py` — `<think>` / `<thinking>` / `<reasoning>` ブロック内に `{}` が含まれると `_extract_json_block` の greedy regex がブロック全体を飲み込んでJSONパースが失敗する問題を修正。`_strip_thinking_blocks()` ヘルパーを追加し、JSON抽出前に除去するよう変更。
- `llm.py` — `_build_fallback_response()` でJSONクリーン後に空文字になった場合、`raw_text[:500]`（生JSON）がそのまま `opinion` になる問題を修正。`"opinion"\s*:\s*"..."` の正規表現で値を直接抽出するフォールバックを追加。

---

## [0.25.0] - 2026-03-17

### Added
- `llm.py` — `_clean_opinion()` ヘルパーを追加。`opinion` フィールドに混入するJSONオブジェクト・配列・`<think>` タグ・コードフェンスを除去。Gemini / litellm-proxy 経由時の出力汚染に対応。

### Changed
- `llm.py` — `_build_fallback_response()` の既存JSON残骸除去処理を `_clean_opinion()` に統一。

---

## [0.24.1] - 2026-03-17

### Added
- `llm.py` — `PERSONA_TEMPERATURES` 辞書を追加し、ペルソナごとに temperature を個別設定。MELCHIOR=0.2（論理・確定的推論）、BALTHASAR=0.7（感情・多様な表現）、CASPER=0.4（実利・バランス）。未登録ペルソナのデフォルトは 0.5。

---

## [0.24.0] - 2026-03-17

### Added
- `persona.py` — `PERSONA_PRIORITIES` 辞書を追加。MELCHIOR（科学的根拠・論理整合性・再現性）、BALTHASAR（倫理・人間感情・社会影響）、CASPER（実装可能性・コスト・リスク）の意思決定優先順位をシステムプロンプトに明示し、ペルソナ差異を強化。
- `persona.py` — `Persona` に `current_phase` / `turns_since_last` インスタンス変数を追加。
- `discussion.py` — `_get_discussion_phase()` 静的メソッドを追加。ターン数に応じて「問題定義→論点探索→解決策設計→合意形成」の4フェーズを返し、各ペルソナのシステムプロンプトに現在フェーズを注入。早期収束防止と議論構造の明確化を実現。
- `discussion.py` — `_bigram_similarity()` ユーティリティ関数を追加（日本語バイグラムJaccard類似度）。

### Changed
- `discussion.py` — `_pick_next_speaker()` をランダム選択から最大不一致スコア方式（Maximum Disagreement）に変更。否定感情（+2×強度）・役割対立（+1）・発言間隔（+0.5×turns）の合計スコアで次話者を選択し、議論密度と対立構造を向上。
- `discussion.py` — LLM呼び出し前に Novelty Check を追加。直近2発言のバイグラム類似度が0.7超の場合に「新しい切り口で発言してください」という `extra_instruction` を自動付与し、同一主張ループを抑制。
- `discussion.py` / `persona.py` — 毎ターン `turns_since_last` と `current_phase` を全ペルソナに更新。

---

## [0.23.0] - 2026-03-17

### Fixed
- `discussion.py` — 最終レポートの `max_tokens` を 1500 → 2500 に拡大。レポートが途中で切れる問題を修正。

### Changed
- `llm.py` `check_topic_coverage()` — カバレッジ評価手順に「導入の是非（賛否判断）が明示されているか」の確認ステップを追加。「こう実装すれば動く」という実装論だけでは是非の判断とみなさない旨を明記。
- `discussion.py` — ファシリテーター最終警告に「導入すべきか否かの賛否を各ペルソナが明示すること」の指示を追加。

---

## [0.22.1] - 2026-03-17

### Fixed
- `discussion.py` — カバレッジチェックのリトライが永遠に走らないバグを修正。`turn == COVERAGE_CHECK_TURN`（一度しか真にならない）を `turn == self._next_coverage_check_turn`（動的管理）に変更。チェック失敗時に `_next_coverage_check_turn = current_turn + 4` でリトライターンをスケジュールするよう修正。
- `discussion.py` — 強制通過条件の `>` を `>=` に修正（`MAX_COVERAGE_RETRIES=1` の場合に `_coverage_checked=1` で強制通過できなかった）。
- `discussion.py` — `__init__` に `_next_coverage_check_turn: int = COVERAGE_CHECK_TURN` を追加。

---

## [0.22.0] - 2026-03-17

### Added
- `persona.py` `_build_system_prompt()` — `coverage_passed: bool` 引数を追加。`False` の間は `convergence_vote`/`convergence_reason` フィールドをJSONスキーマから完全に除去し、収束の概念自体をモデルに届けない。`True` になった時点で初めて収束フィールドとルール10〜12が出現する。
- `persona.py` `Persona` — `coverage_passed: bool = False` インスタンス変数を追加。`system_prompt` プロパティが参照して `_build_system_prompt` に渡す。
- `discussion.py` `_set_coverage_passed()` — カバレッジ通過時に `self._coverage_passed` と全ペルソナの `coverage_passed` フラグを同時に `True` に設定するヘルパーを追加。

---

## [0.21.0] - 2026-03-17

### Changed
- `llm.py` `check_topic_coverage()` — カバレッジ評価プロンプトの観点をハードコードから動的抽出に変更。固定の「技術スタック固有リスク」等の観点を削除し、「まず議題から主要論点を列挙→各論点の議論充足度を判定→未議論論点をリストアップ」という手順をLLMに委ねる設計に。テクニカル・プロセス・組織・リスクを横断的にカバーできるようになった。

---

## [0.20.0] - 2026-03-17

### Changed
- `discussion.py` — カバレッジチェックのタイミングを「収束確定時」から「固定ターン（`COVERAGE_CHECK_TURN=8`）」に変更。Qwen3クラスが早期（ターン4〜7）に収束モードに入っても、ペルソナがまだ議論モードにいるタイミングで欠落論点を注入できるようになった。
- `discussion.py` — `_check_convergence()` にカバレッジ通過フラグ（`_coverage_passed`）のガードを追加。チェックが通過するまで収束確定をブロックする。
- `discussion.py` — カバレッジ注入メッセージを報告形式から行動指示形式（「収束判断を一時保留し、以下の点に正面から回答してください」）に変更。
- `llm.py` — `check_topic_coverage()` メソッドを `LLMClient` に移動。`missing_points` を文字列から `list[str]` に変更し、`_extract_json_block` を流用。

### Added
- `discussion.py` — `COVERAGE_CHECK_TURN = 8`・`MAX_COVERAGE_RETRIES = 1` 定数を追加。
- `discussion.py` — `_run_coverage_check()` メソッドを追加（旧 `_check_topic_coverage()` を再設計）。チェック回数を `_coverage_checked` でカウントし、`MAX_COVERAGE_RETRIES` 超過時は強制通過。

### Removed
- `discussion.py` — 旧 `_check_topic_coverage()` メソッドと `MAX_TOPIC_COVERAGE_RETRIES` 定数を削除。

---

## [0.19.0] - 2026-03-17

### Added
- `discussion.py` — `_check_topic_coverage()` メソッドを追加。収束候補が確定した時点でLLMに「元の議題の論点が十分にカバーされているか」を評価させ、`adequate=False` の場合は収束を保留する「議題適合チェック」フェーズを導入。
  - 不足論点（`missing_points`）をファシリテーターメッセージとして注入し、対象ペルソナの `convergence_vote` をリセットして議論を継続させる。
  - `MAX_TOPIC_COVERAGE_RETRIES = 2` の上限を設け、無限ループを防止。上限到達後は収束をそのまま確定する。
  - LLM呼び出しエラー時は `(True, "")` を返してフォールバック（収束ブロックしない）。

---

## [0.18.0] - 2026-03-17

### Changed
- `CONVERGENCE_THRESHOLD` を 3 → 2 に変更。3人全員一致は20Bモデルには過剰な要件であり、過半数2名合意で収束とする現実的な設計に変更。少数意見が残る形は議論記録として誠実。
- `MIN_TURNS_BEFORE_CONVERGENCE` を 6 → 10 に変更。閾値を2に下げた分、早すぎる収束を防ぐため最低ターン数を引き上げてバランスを調整。
- `_check_convergence()` の直近マーカー閾値から `- 1` を除去。`CONVERGENCE_THRESHOLD` 自体が2になったため `THRESHOLD - 1` の緩和補正は不要。

---

## [0.17.0] - 2026-03-17

### Fixed
- `discussion.py` `_check_convergence()` — 直近マーカー確認の閾値を `CONVERGENCE_THRESHOLD`（3）から `CONVERGENCE_THRESHOLD - 1`（2）に緩和。全員一致フラグ＋直近3名全員マーカーという二重の厳格条件が、1名の条件付き発言1ターンで収束をブロックしていた問題を修正。
- `persona.py` `update_from_response()` — 一度 `convergence_vote = True` になったペルソナはコード側でフラグを守り、LLMが次ターンに `false` を返しても上書きしないよう修正。システムプロンプトのルール11（合意維持）を20Bモデルが守れないケースへのコードガード。

### Changed
- `llm.py` — `presence_penalty` / `frequency_penalty` を 0.6 → 0.8 に引き上げ。ターン5付近でペルソナが他者の発言を丸コピーする劣化パターンの抑制を強化。

---

## [0.16.0] - 2026-03-17

### Fixed
- **A-1**: `discussion.py` — `turn_count` をペルソナ発言数（`turn` 変数）に統一。`_build_state()` のデフォルトを 0 に変更し、全呼び出し元で明示的に渡すよう修正。ファシリテーターメッセージを含む `len(shared_memory)` を誤ってターン数として使っていたバグを解消。
- **A-3**: `save.py` — 議論ログの連番をペルソナ発言のみにカウント。ファシリテーター/システム注入メッセージはターン番号を付けず区切り線＋太字スタイルで表示するよう変更。

### Changed
- **B-1**: `llm.py` — `RECENT_TURNS_TO_KEEP` を 8 → 16 に拡大。20B モデルのコンテキスト余裕を活かし、直近16ターンの履歴を保持するよう変更。
- **B-2**: `llm.py` — urgency 注入閾値をハードコードの `turn > 12` から `turn > max_turns * 0.6`（動的計算）に変更。`chat_with_persona` に `max_turns` 引数を追加し、`discussion.py` から `MAX_TURNS` を渡すよう修正。
- **C-3**: `discussion.py` — `closing_instruction` から「JSON形式で」の記述を削除。締めくくりフェーズはプレーンテキストの発言を促す自然な指示に変更。

### Added
- **B-3**: `discussion.py` — `_check_convergence()` メソッドを追加。従来の `convergence_vote` フラグカウントに加え、直近4件のペルソナ発言メッセージ内に `【収束に同意】` マーカーが `CONVERGENCE_THRESHOLD` 件以上含まれることを確認してから収束判定を行う。古い（陳腐化した）フラグによる誤収束を防止。
- **B-4**: `discussion.py` — `MAX_TURNS * 0.75` ターン超過時点で収束票がゼロの場合、より強い「最終警告」ファシリテーターメッセージを `shared_memory` へ自動注入。全ペルソナに即時折衷案提示と `convergence_vote: true` を強く促す。
- **C-1**: `llm.py` — `_build_fallback_response()` の JSON 残骸除去をイテレート方式（入れ子 `{}` の反復除去）に強化。加えて markdown コードフェンス除去・連続空行の圧縮も実施。
- **C-2**: `llm.py` — `_parse_persona_response()` 内でセルフエコー後処理を追加。LLM が自分自身のペルソナ名を名指しで呼びかけるパターン（例: `MELCHIOR、`）を正規表現で除去してから `opinion` に格納。

---

## [0.15.0] - 2026-03-17

### Added
- 会話履歴の切り詰め（Truncation）ロジックを `llm.py` に実装。メッセージ数が `RECENT_TURNS_TO_KEEP + 1`（デフォルト9件）を超えた場合、最初のメッセージ（ファシリテーターの議題提示）と直近8件のみをLLMへ渡す。中間部分には `（...中盤の議論履歴は省略...）` プレースホルダーを挿入。自己スタンスはシステムプロンプトの長期記憶で補完されるため主張の一貫性は維持される。

---

## [0.14.0] - 2026-03-17

### Added
- `_build_system_prompt` に `current_stance` 引数を追加。`Persona.current_stance`（直前の自分の主張）をシステムプロンプト内の「長期記憶」セクションとして常に埋め込むことで、履歴が切り詰められても自己の主張の一貫性を維持できるようにした。

---

## [0.13.0] - 2026-03-17

### Added
- `convergence_vote = true` を出したターンの発言テキスト冒頭に `【収束に同意】` マーカーを自動付与。LLMが次回以降の発言履歴で自分の同意済みステータスをテキストとして認識できるようにした。
- システムプロンプトにルール11「合意の維持と仲裁」を追加：過去の発言に `【収束に同意】` マーカーがある場合は `convergence_vote` を `false` に戻すことを禁止し、未合意ペルソナへの仲裁・説得役に回るよう指示。

---

## [0.12.0] - 2026-03-17

### Changed
- システムプロンプトのルール8を「合意形成の許可」に改訂：議論が成熟し折衷案で意見が一致し始めた場合は、初期スタンスに固執せず大局的な合意を優先してよいと明示
- システムプロンプトのルール10（収束判断）を改訂：全員が折衷案に賛同しこれ以上議論の余地がない場合は `convergence_vote` を必ず `true` にするよう強調。意地を張って `false` を出し続けることを明示禁止

---

## [0.11.1] - 2026-03-17

### Changed
- ファシリテーター警告の介入タイミングをハードコードの `turn == 10` から `turn == MAX_TURNS // 2` に変更。`MAX_TURNS` を変更した際に警告タイミングが自動追従するようになった。

---

## [0.11.0] - 2026-03-17

### Added
- ターン10経過時にファシリテーターが「折衷案を提示せよ」という警告メッセージを `shared_memory` へ自動注入し、平行線ループを強制的に打破する仕組みを追加

### Changed
- システムプロンプトにルール7を追加：他者が同じ主張を繰り返していると感じた場合、名指しで指摘して議論を次のステップへ強制的に進めることを義務化

---

## [0.10.0] - 2026-03-17

### Changed
- `MAX_TURNS` を 20 → 50 に変更（議論がより深く展開できるよう上限を拡大）
- `CONVERGENCE_THRESHOLD` を 2 → 3 に変更（全ペルソナ一致を収束条件に変更）

---

## [0.9.0] - 2026-03-17

### Fixed
- システムプロンプトにルール4を追加：名指しできる相手を `other_names`（自分以外のペルソナ）に限定し、自分自身への同調・自画自賛（セルフエコー）を明示禁止。`{name}` と `{other_names_str}` を変数として埋め込み、LLMの自己認識のブレを抑制。

---

## [0.8.0] - 2026-03-17

### Added
- ファシリテーターによる議題の冒頭投下。議論開始時に担当スタンス一覧とともに議題を `shared_memory` へ注入し、1ターン目のペルソナが自然なコンテキストで発言を開始できるようにした。
- `display.py` にファシリテーターの表示スタイルを追加（白文字・ダークレッド背景）

---

## [0.7.0] - 2026-03-17

### Changed
- システムプロンプトのルール3を改訂：相手のペルソナ名を名指しで呼びかけてから反論・補足を行うよう義務化（例：「BALTHASAR、あなたの提案には…」）

---

## [0.6.0] - 2026-03-17

### Changed
- システムプロンプトのルール3を改訂：直前の発言内の具体的なキーワード・提案・論拠を引用した上で反論・疑問・批判・補足を行うよう強制。自分の主張の一方的な繰り返しを明示禁止。
- システムプロンプトにルール4を追加：他のペルソナが新しい代替案・妥協案を出した場合はそれを無視せず「アリかナシか」の評価を必須化。

---

## [0.5.0] - 2026-03-17

### Changed
- `LLMClient.chat_with_persona` の生成パラメータ調整：`temperature` 0.7→0.8、`presence_penalty=0.6`・`frequency_penalty=0.6` を追加し、繰り返し発言を抑制
- システムプロンプトのルール3・4を改訂：平行線を検知した場合に「妥協案の提示」または「相手への具体的な質問」を許可・推奨
- `chat_with_persona` に `turn` パラメータを追加。ターン13以降は「議論が長期化しているため落としどころを模索せよ」という焦り指示をプロンプトに注入

---

## [0.4.0] - 2026-03-17

### Added
- 議論開始時に各ペルソナへ「推進派」「懐疑派」「代替案提案派」をランダム割当
- `PersonaState` に `initial_role` フィールドを追加
- モニタリング画面のペルソナパネルに初期スタンスのバッジを表示

### Changed
- システムプロンプトに反論・批判を必ず含める旨のルールを追加（単純な同調を明示禁止）
- 感情状態（negative/positive）に応じた発言スタイル指示をプロンプトに追加
- 収束判定に最低ターン数（6ターン）を設定し、序盤の安易な同調収束を防止

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
