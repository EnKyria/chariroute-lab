# Progress

新しいセッションを始めたら、最初にこのファイルを読む。フェーズの完了時とセッションを切り替える前に更新する。
会話履歴にしか残っていない重要な情報は、ここか `docs/plan.md` / `docs/engineering-notes.md` に書き移す。
フェーズ番号の定義は `docs/plan.md` §5 を参照。

最終更新：2026-11-25（セッション 2、`feature/ci` の PR 作成時）

## 現在のフェーズ
**PHASE 2：GitHub・CI 構築** — 進行中。CI のワークフローを `feature/ci` で追加し、PR で CI を確認している段階。
残り：CI が緑になる → マージ → `main` のブランチ保護 → 保護の動作確認（引き継ぎ用 docs の PR）

## 現在のブランチと Git の状態
- リモート：`origin` = https://github.com/EnKyria/chariroute-lab（**public**）
- `main`：初回コミット `dfffd2c`（PHASE 1）を push 済み
- `feature/ci`：`.github/workflows/ci.yml` の追加と、docs の更新
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

## 完了済みタスク
### PHASE 1（2026-11-25 完了）
- [x] 既存リポジトリの調査、Python 3.12 の venv、requirements、特性テスト（9 件）
- [x] `.gitignore` / `.gitattributes`、ハーネス（CLAUDE.md、rules、settings、Stop Hook、`scripts/check.py`）
- [x] サブエージェントの定義（researcher / reviewer / evaluator / aws-expert）
- [x] GBFS の取得可否・ライセンス・データ構造の確認（`docs/plan.md` §1）
- [x] reviewer による最終レビューと指摘への対応 → 初回コミット `dfffd2c`

### PHASE 2（進行中）
- [x] GitHub の認証（`gh auth login`、アカウント `EnKyria`）
- [x] public リポジトリの作成と `main` の push
- [x] `feature/ci`：GitHub Actions のワークフロー（`.github/workflows/ci.yml`）
- [ ] PR で CI が緑になることの確認 → マージ
- [ ] `main` のブランチ保護の設定と、保護の動作確認

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

## 今後の改善事項（MVP 後）
- GitHub Actions を、メジャータグ（`actions/checkout@v5`、`actions/setup-python@v6`）ではなくコミット SHA に固定する（Dependabot での更新もあわせて検討する）

## 最新の品質チェック結果
- 2026-11-25（セッション 2、`feature/ci`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：9 件成功（警告 1 件：Mangum の DeprecationWarning）
  - CI と同じ `CHECK_PYTHON` の経路でも成功。Python が見つからない場合は exit 2 になることも確認
- GitHub Actions：PR で確認中

## 次にやること
1. PR の CI が緑になることを確認して、マージする（ユーザーの承認後）
2. `main` のブランチ保護を設定する（上の方針。ユーザーの承認後）
3. 引き継ぎ用の docs の PR で、保護が効いているか確認する（直接 push の拒否、CI が必須チェックになっていること）
4. PHASE 2 完了 → このファイルを更新 → PHASE 3 へ
