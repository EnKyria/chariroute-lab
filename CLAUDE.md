# chariroute-lab

大阪市のドコモ・バイクシェアを使った経路検索サービス。推定所要時間が最小になる経路を返す MVP を作り、AWS 上で動かす。
あわせて、AI 駆動開発・ハーネス設計・評価駆動開発・GitHub を使ったチーム開発の実践知を蓄積し、開発者が設計判断を説明できる状態を目指す。

- 設計方針と実装計画：@docs/plan.md
- 進捗と引き継ぎ：@docs/progress.md
- 技術知見のログ（随時追記）：`docs/engineering-notes.md`
- 言語・領域ごとの規約は `.claude/rules/` に置く。該当ファイルを触ったときに自動で読み込まれる。

## セッション管理
- **セッション開始時**：`docs/progress.md` と `git status` / `git log --oneline -5` を確認し、現在のフェーズと次の作業を把握してから着手する。
- **フェーズの完了時・セッションを切り替える前**：`docs/progress.md` を更新する（完了・未完了のタスク、ブランチ、未解決の問題、最新の品質チェック結果、次にやること）。
- 決定事項や調査結果を会話履歴だけに残さない。設計は `docs/plan.md`、理由と学びは `docs/engineering-notes.md`、状態は `docs/progress.md` に書く。

## サブエージェントの使い分け（`.claude/agents/`）
サブエージェントは読み取り専用。**ファイルの変更はメインエージェントだけが行う。** 単純なタスクは委譲しない。同時に起動するのは原則 1 つまで。
| エージェント | 使う場面 | 使わない場面 |
|---|---|---|
| `researcher` | 実装前の仕様の裏付けで、複数ページの調査が必要なとき | 1 回の検索や既知の仕様で済むとき |
| `evaluator` | 新機能の実装**前**。要求仕様だけを渡してテストケースを設計させる | 既存テストの軽微な修正 |
| `reviewer` | 機能単位の実装後、コミットや PR の前。変更ファイルの一覧か diff を渡す | typo 修正やドキュメントだけの変更 |
| `aws-expert` | AWS の構成やデプロイ方式を決める前、棚卸し結果の評価 | 決定済みの手順を実行するとき（実行はメインがユーザーの了承を得て行う） |

## 変えてはいけない要件
- 対象地域は**大阪市**、対象事業者は**ドコモ・バイクシェアのみ**。他事業者向けの抽象化はしない。
- ポート情報と貸出・返却状況は **GBFS**（ODPT 公開フィード `docomo-cycle`、CC BY 4.0）から取得する。
- 入力はプリセット地点からの選択。経路は直線距離と移動速度にもとづく概算。
- 最寄りポートだけでなく、**複数の貸出ポートと返却ポートの組み合わせ**を評価し、合計所要時間（徒歩 + 自転車 + 徒歩）が最小のものを選ぶ。
- 実際に利用可能なポートだけを使う（貸出：`is_renting` かつ空き自転車 > 0、返却：`is_returning` かつ空きドック > 0）。
- **GBFS の取得に失敗したときは、ダミーデータを実データとして返さない**（503 で返す）。

## アーキテクチャ（目標）
```
Browser ─▶ CloudFront ─▶ S3（React / Vite のビルド成果物）
   └────▶ API Gateway HTTP API ─(Lambda プロキシ統合, payload 2.0)─▶ Lambda (Python 3.12, Mangum → FastAPI) ─▶ ODPT GBFS
                                                                       └▶ CloudWatch Logs / Metrics
```
- IAM は最小権限とする。Lambda の実行ロールは CloudWatch Logs への書き込みのみ。
- 既存の AWS リソースがあれば確認してから再利用する。

## リポジトリ構成
- `backend/`：FastAPI アプリ（`main.py`）、テスト（`tests/`）、依存定義（`requirements*.txt`）
- `frontend/`：React + TypeScript + Vite（未作成）
- `scripts/check.py`：品質ゲート。`scripts/stop_hook.py`：Claude Code の Stop Hook
- `package/` と `deployment.zip`：旧手順で作った Lambda 成果物。Git 管理の対象外で、削除しない

## セットアップとコマンド（Windows / Git Bash）
```bash
py -3.12 -m venv backend/.venv            # Python 3.12 必須（Lambda ランタイムと合わせる）
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
python scripts/check.py                    # lint と test の全件（push 前に必ず実行）
backend/.venv/Scripts/python.exe -m pytest backend/tests -k <name>   # 個別のテスト
```

## 開発フロー
1. Issue（またはタスク）単位で `feature/<短い名前>` ブランチを切る。`main` に直接コミットしない。
2. 先にテストを書くか更新してから実装する。外部の GBFS にはテストから接続せず、フィクスチャを使う。
3. `python scripts/check.py` が通るまで直す。終了時に Stop Hook が同じチェックを自動で検証する。
4. 設計判断・トラブル・学びがあれば `docs/engineering-notes.md` に追記する。
5. コミットや PR の前に変更内容をユーザーに提示する。PR は GitHub Actions の CI が通ってからマージする。

## 完了条件（各タスク共通）
- `python scripts/check.py` が終了コード 0 で終わる。
- 新しい振る舞いにテストがある。既存のテストを削除・skip していない。
- 要件（上記）に反していない。特に、データ取得に失敗したときにダミー値を返していない。
- 必要に応じて `docs/` を更新済み。

## GitHub の操作範囲
- **操作してよいリポジトリ：`EnKyria/chariroute-lab` だけ。** これ以外のリポジトリや Organization は、読み取りも含めて操作しない（許可リスト方式）。
- GitHub を操作する前に `gh api user --jq .login` で、認証中のアカウントが `EnKyria` であることを確認する。`gh` のコマンドでは `--repo EnKyria/chariroute-lab` のように対象を明示する。
- コミットの作者は、ローカル設定の `EnKyria <36327617+EnKyria@users.noreply.github.com>` とする。

## 事前確認が必要な操作（必ずユーザーの了承を得る）
- AWS リソースの作成・変更・削除、デプロイ、有料リソースの作成
- `git commit` / `git push`、ブランチの削除、履歴の書き換え
- 依存ライブラリの追加、ファイルやディレクトリの削除
- 機密情報（`.env`、`~/.aws`、鍵ファイル）は読まない、表示しない、コミットしない
