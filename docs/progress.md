# Progress

新しいセッションを始めたら、最初にこのファイルを読む。フェーズの完了時とセッションを切り替える前に更新する。
会話履歴にしか残っていない重要な情報は、ここか `docs/plan.md` / `docs/engineering-notes.md` に書き移す。
フェーズ番号の定義は `docs/plan.md` §5 を参照。

最終更新：2026-11-25（セッション 2 の終了時）

## 現在のフェーズ
**PHASE 2：GitHub・CI 構築** — 完了（引き継ぎ用 PR `feature/phase2-handoff` のマージをもって完了）。
→ 次は **PHASE 3：バックエンド実装**

## 現在のブランチと Git の状態
- リモート：`origin` = https://github.com/EnKyria/chariroute-lab（**public**）
- `main`：`dfffd2c`（PHASE 1）→ `89848ed`（PR #1、CI の追加、squash マージ）→ 引き継ぎ用 PR
- `main` は ruleset `protect-main`（ID 28061644）で保護している。**直接 push はできない**ので、変更は必ず `feature/<名前>` ブランチ → PR → CI（`check`）が緑 → squash マージ、の順で行う
- マージ済みのブランチは、リモートとローカルの両方から削除する。squash マージ後は `git branch -d` が使えないため、`git diff --quiet main <branch>` で中身が同じことを確かめてから `-D` で削除する
- コミットの作者：ローカル設定の `EnKyria <36327617+EnKyria@users.noreply.github.com>`
- Git 管理の対象外：`package/`、`deployment.zip`（旧 Lambda 成果物、削除しない）、`backend/.venv`、`backend/.venv-py310`（旧 3.10 の venv の退避先）、各種キャッシュ、`.claude/.cache/`

## ユーザーの意思決定
### 2026-11-25（セッション 1）
- Git のメールアドレスは個人のものではなく **GitHub の noreply アドレス**を使う
- AWS CLI の導入は**承認済み**。ただし実際の導入と認証設定は **PHASE 6 まで延期**する
- AWS リソースの作成・変更・削除は、引き続き**操作ごとに個別の承認**が必要
- フェーズ番号は PHASE 1〜7 に統一する（`docs/plan.md` §5）

### 2026-11-25（セッション 2）
- GitHub の操作対象は **`EnKyria/chariroute-lab` だけ**（許可リスト方式。CLAUDE.md「GitHub の操作範囲」）。操作の前に `gh api user --jq .login` で認証中のアカウントを確認する
- 技術調査を目的とした、外部の公開リポジトリと公式ドキュメントの読み取り専用の参照は許可。他リポジトリへの変更操作と非公開リポジトリへのアクセスは禁止
- Actions の SHA 固定は今後の改善事項とし、今回は MVP の完成を優先する
- リポジトリは **public**。コミットの作者名は GitHub のユーザー名（`EnKyria`）にする
- reviewer の must 指摘に対応して、`.claude/settings.json` の ask / deny を強化した（PowerShell 版、`python -m pip install` の経路、`git add -f` の禁止）
- `main` のブランチ保護（CI の動作確認後に設定する）：
  - PR 経由の変更を必須にする
  - CI（ジョブ `check`）の成功をマージの必須条件にする
  - force push を禁止する
  - ブランチの削除を禁止する
  - 他者のレビュー承認は**必須にしない**（個人開発のため）
- マージは **squash** で行い、マージ済みのブランチは削除する
- ブランチ保護の検証のために、`main` へ直接 push してはいけない

## 完了済みタスク
### PHASE 1（2026-11-25 完了）
- [x] 既存リポジトリの調査、Python 3.12 の venv、requirements、特性テスト（9 件）
- [x] `.gitignore` / `.gitattributes`、ハーネス（CLAUDE.md、rules、settings、Stop Hook、`scripts/check.py`）
- [x] サブエージェントの定義（researcher / reviewer / evaluator / aws-expert）
- [x] GBFS の取得可否・ライセンス・データ構造の確認（`docs/plan.md` §1）
- [x] reviewer による最終レビューと指摘への対応 → 初回コミット `dfffd2c`

### PHASE 2（2026-11-25 完了）
- [x] GitHub の認証（`gh auth login`、アカウント `EnKyria`）
- [x] public リポジトリの作成と `main` の push
- [x] `feature/ci`：GitHub Actions のワークフロー（`.github/workflows/ci.yml`）→ PR #1 の CI が pass（18 秒）→ squash マージ
- [x] `main` のブランチ保護（ruleset `protect-main`）の設定と、API による設定内容の確認
- [x] 引き継ぎ用 PR で、必須チェック `check` が機能することを確認（結果は「ブランチ保護の検証結果」を参照）

## 未完了タスク（以降のフェーズ）
- [ ] **PHASE 3**：GBFS の取得・キャッシュ、大阪市内のポート抽出、失敗時に 503、K×K の経路計算、プリセット API
- [ ] **PHASE 4**：フロントエンド（React / TS / Vite）
- [ ] **PHASE 5**：ローカル結合確認
- [ ] **PHASE 6**：AWS CLI の導入と認証設定、棚卸し、Lambda ビルド、HTTP API、S3 + CloudFront、CloudWatch
- [ ] **PHASE 7**：総合評価・技術知見の整理

## 重要な設計判断（詳細は `docs/engineering-notes.md` §2）
- AWS 構成：API Gateway HTTP API → Lambda（プロキシ統合、Mangum）、フロントは S3 + CloudFront
- 経路は直線距離 × 迂回係数 1.3 で概算し、ポートの組み合わせは K×K（K=10）で評価する
- GBFS の取得に失敗したら 503 を返し、ダミー値は返さない
- 品質ゲートは `scripts/check.py` の 1 か所に集約（人・Stop Hook・CI で共通）。CI には環境構築だけを書く
- サブエージェントは読み取り専用とし、ファイルの変更はメインエージェントだけが行う
- コミットには noreply アドレスを使う（ローカル設定にのみ設定）

## 未解決の問題
- **`backend/main.py` の `/api/routes/search` は固定のダミー応答を返す暫定実装**（GBFS を取得しない）。PHASE 3 で置き換えるまでは、AWS へのデプロイや公開をしない。置き換える際は、特性テストを変更する理由をコミットメッセージに書く
- 大阪市内のポートの抽出方法（`system_regions` が 404 で、`region_id` の意味が不明） → PHASE 3
- エリアをまたいだ返却の不可への対応（隣接市のポートを除外する） → PHASE 3
- ODPT のアクセス頻度に関する規約が未確認 → PHASE 3
- 既存の AWS 環境（Lambda の有無・ランタイム）が未確認 → PHASE 6
- Stop Hook：セッション 2 で、状態ファイル `.claude/.cache/stop-hook-state.json` が `stop_hook.py` の修正後に更新されていたため、**動作していると推定**。`/hooks` での目視確認はまだ。サブエージェント（reviewer）は読み込まれ、動作を確認済み
- Mangum 0.22 で DeprecationWarning が出る（動作には影響なし）

## ブランチ保護の検証結果（2026-11-25）
- **API で確認した事実**：`GET /repos/EnKyria/chariroute-lab/rules/branches/main` で、ruleset 28061644 の 4 つのルールが `main` に適用されている。
  - deletion
  - non_fast_forward
  - pull_request（`required_approving_review_count: 0`）
  - required_status_checks（`check`、integration_id 15368 = github-actions、`strict: false`）
  - あわせて `enforcement: active`、`bypass_actors: []`、`current_user_can_bypass: never` を確認した。
- **送っていないのに既定値で付いたパラメータ**：`require_extra_approval_for_unattributed_changes: true` と `allowed_merge_methods: [merge, squash, rebase]`。前者の意味は未調査。
- **PR での確認**：引き継ぎ用 PR の結果を PR_RESULT_PLACEHOLDER に記録する。
- **未検証**：`main` への直接 push と force push が実際に拒否されるか。ユーザーの指示により、検証目的の直接 push は行わない。dry-run もサーバー側のルールを評価しないため、根拠にしない。

## 今後の改善事項（MVP 後）
- GitHub Actions を、メジャータグ（`actions/checkout@v5`、`actions/setup-python@v6`）ではなくコミット SHA に固定する（Dependabot での更新もあわせて検討する）

## 最新の品質チェック結果
- 2026-11-25（セッション 2、`feature/ci`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：9 件成功（警告 1 件：Mangum の DeprecationWarning）
  - CI と同じ `CHECK_PYTHON` の経路でも成功。Python が見つからない場合は exit 2 になることも確認
- GitHub Actions：PR #1 でジョブ `check` が pass（ruff OK、pytest 9 件、`check.py: ALL PASSED`）

## 次にやること（PHASE 3：バックエンド実装）
1. このファイルを読み、`git switch main && git pull --ff-only` と `git log --oneline -5` で状態を確認する。`gh api user --jq .login` が `EnKyria` であることも確認する
2. `/hooks` で Stop Hook が読み込まれていることを目視で確認する（未確認）
3. 未解決の問題のうち、PHASE 3 の前提になる 3 点を調べる。調査は `researcher` に任せる
   - 大阪市内のポートの抽出方法
   - エリアをまたいだ返却への対応
   - ODPT のアクセス頻度に関する規約
4. `feature/gbfs-client` などのブランチを切る。`evaluator` に要求仕様を渡してテストケースを設計させてから、テスト先行で実装する
   - GBFS の取得、キャッシュ、失敗時の 503
   - 大阪市内のポートの抽出
   - K×K の経路計算
   - プリセット API
5. 特性テストを置き換えるときは、その理由をコミットメッセージに書く（`.claude/rules/testing.md`）
