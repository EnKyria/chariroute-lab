# Progress

新しいセッションを始めたら、最初にこのファイルを読む。フェーズの完了時とセッションを切り替える前に更新する。
会話履歴にしか残っていない重要な情報は、ここか `docs/plan.md` / `docs/engineering-notes.md` に書き移す。
フェーズ番号の定義は `docs/plan.md` §5 を参照。

最終更新：2026-11-25（セッション 1 の終了時）

## 現在のフェーズ
**PHASE 1：開発基盤・ハーネス構築** — 作業はすべて完了。残りは **reviewer による最終レビューと初回コミット**だけ。
→ 次は **PHASE 2：GitHub・CI 構築**

## 現在のブランチと Git の状態（2026-11-25 終了時点）
- ブランチ：`main`（`git init -b main` 済み、**コミット 0 件**）
- リモート：未設定
- 22 ファイルをすべてステージ済み（`A`）。未ステージや未追跡のファイルはない
  ```
  .claude/agents/{aws-expert,evaluator,researcher,reviewer}.md
  .claude/rules/{backend,frontend,testing}.md
  .claude/settings.json  .gitattributes  .gitignore  CLAUDE.md  pyproject.toml
  backend/{main.py,pyproject.toml,requirements.txt,requirements-dev.txt,tests/test_main.py}
  docs/{engineering-notes,plan,progress}.md
  scripts/{check,stop_hook}.py
  ```
- Git 管理の対象外：`package/`、`deployment.zip`（旧 Lambda 成果物、削除しない）、`backend/.venv`、`backend/.venv-py310`（旧 3.10 の venv の退避先）、各種キャッシュ、`.claude/.cache/`
- `user.email` は現在グローバル設定の個人メールアドレス → **コミット前に、このリポジトリのローカル設定を GitHub の noreply アドレスに変える**

## ユーザーの意思決定（2026-11-25）
- 初回コミットは、次のセッションで **reviewer による最終レビューを行った後**に実施する
- Git のメールアドレスは個人のものではなく **GitHub の noreply アドレス**（`<ID>+<ユーザー名>@users.noreply.github.com`）を使う
- GitHub リポジトリの作成・push・CI 構築は次のセッションで行う（PHASE 2）
- AWS CLI の導入は**承認済み**。ただし実際の導入と認証設定は **PHASE 6 まで延期**する
- AWS リソースの作成・変更・削除は、引き続き**操作ごとに個別の承認**が必要
- フェーズ番号は PHASE 1〜7 に統一する（`docs/plan.md` §5）

## 完了済みタスク（PHASE 1）
- [x] 既存リポジトリの調査（ダミー応答の FastAPI + Mangum、Lambda 用 zip）
- [x] Python 3.12.10 の導入（winget）、`backend/.venv` の作成
- [x] `requirements.txt` / `requirements-dev.txt`（Lambda 成果物と同じ版に固定）
- [x] 既存の挙動を固定する特性テスト（`backend/tests/test_main.py`、9 件）
- [x] `.gitignore` / `.gitattributes`（LF に統一）と `git init`
- [x] ハーネス：`CLAUDE.md`、`.claude/rules/`（3 ファイル）、`.claude/settings.json`（権限設定と Stop Hook）、`scripts/check.py`
- [x] サブエージェント定義（researcher / reviewer / evaluator / aws-expert。すべて読み取り専用で sonnet）
- [x] ドコモ・バイクシェア GBFS の取得可否・ライセンス・データ構造の確認（`docs/plan.md` §1）
- [x] セッション管理（このファイル）と、技術知見ノートの作成

## 未完了タスク
- [ ] **PHASE 1**：reviewer による最終レビュー → 指摘への対応 → noreply アドレスの設定 → 初回コミット（ユーザーの承認後）
- [ ] **PHASE 2**：GitHub リポジトリの作成と push、GitHub Actions（`scripts/check.py`）、ブランチ運用の開始
- [ ] **PHASE 3**：GBFS の取得・キャッシュ、大阪市内のポート抽出、失敗時に 503、K×K の経路計算、プリセット API
- [ ] **PHASE 4**：フロントエンド（React / TS / Vite）
- [ ] **PHASE 5**：ローカル結合確認
- [ ] **PHASE 6**：AWS CLI の導入と認証設定、棚卸し、Lambda ビルド、HTTP API、S3 + CloudFront、CloudWatch
- [ ] **PHASE 7**：総合評価・技術知見の整理

## 重要な設計判断（詳細は `docs/engineering-notes.md` §2）
- AWS 構成：API Gateway HTTP API → Lambda（プロキシ統合、Mangum）、フロントは S3 + CloudFront
- 経路は直線距離 × 迂回係数 1.3 で概算し、ポートの組み合わせは K×K（K=10）で評価する
- GBFS の取得に失敗したら 503 を返し、ダミー値は返さない
- 品質ゲートは `scripts/check.py` の 1 か所に集約（人・Stop Hook・CI で共通）
- サブエージェントは読み取り専用とし、ファイルの変更はメインエージェントだけが行う
- コミットには noreply アドレスを使う（ローカル設定にのみ設定）

## 未解決の問題
- **`backend/main.py` の `/api/routes/search` は固定のダミー応答を返す暫定実装**（GBFS を取得しない）。PHASE 3 で置き換えるまでは、AWS へのデプロイや公開をしない。置き換える際は、特性テストを変更する理由をコミットメッセージに書く
- 大阪市内のポートの抽出方法（`system_regions` が 404 で、`region_id` の意味が不明） → PHASE 3
- エリアをまたいだ返却の不可への対応（隣接市のポートを除外する） → PHASE 3
- ODPT のアクセス頻度に関する規約が未確認 → PHASE 3
- 既存の AWS 環境（Lambda の有無・ランタイム）が未確認 → PHASE 6
- Stop Hook とサブエージェントが新しいセッションで読み込まれるかが未確認 → 次のセッションの冒頭
- Mangum 0.22 で DeprecationWarning が出る（動作には影響なし）

## 最新の品質チェック結果
- 2026-11-25（セッション 1 の終了時）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：9 件成功（警告 1 件：Mangum の `asyncio.get_event_loop` DeprecationWarning）

## 次のセッションで行うこと
1. このファイルを読み、`git status` を確認する（22 ファイルがステージ済みのままであること）
2. `/hooks` で Stop Hook、`/agents` で 4 つのエージェントが読み込まれていることを確認する
3. **reviewer** にステージ済みの全ファイル（`git diff --cached`）を渡して最終レビューを行い、指摘に対応する
4. `gh api user` で GitHub の ID とユーザー名を取得し、`git config user.email <ID>+<ユーザー名>@users.noreply.github.com`（ローカル設定）を設定する
5. ユーザーの承認を得てから初回コミット → PHASE 1 完了 → このファイルを更新する
6. PHASE 2：GitHub リポジトリの作成（公開範囲はユーザーに確認）、push、CI の構築
