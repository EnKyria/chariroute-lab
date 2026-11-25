# Progress

新しいセッションを始めたら、最初にこのファイルを読む。フェーズの完了時とセッションを切り替える前に更新する。
会話履歴にしか残っていない重要な情報は、ここか `docs/plan.md` / `docs/engineering-notes.md` に書き移す。
フェーズ番号の定義は `docs/plan.md` §5 を参照。

最終更新：2026-11-25（セッション 3 の終了時：PHASE 3 完了）

## 現在のフェーズ
**PHASE 3：バックエンド実装** — 完了（PR #3 `feature/route-search` の squash マージをもって完了）。
→ 次は **PHASE 4：フロントエンド実装**（新しいセッションで着手する。開始条件は「次にやること」を参照）

## 現在のブランチと Git の状態
- リモート：`origin` = https://github.com/EnKyria/chariroute-lab（**public**）
- `main`：`dfffd2c`（PHASE 1）→ `89848ed`（PR #1、CI）→ `011db28`（PR #2、PHASE 2 の引き継ぎ）→ PR #3（PHASE 3、経路検索 API）の squash コミット
- 作業ブランチ `feature/route-search` は、マージ後にリモートとローカルの両方から削除する（中身の一致を確認してから）
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

### 2026-11-25（セッション 3）
- MVP 完成までの開発速度を優先する。ハーネスの追加改善や環境整備は、実装の妨げにならない限り行わない
- Git Credential Manager の資格情報の保存エラーは、未解決事項として記録だけする（今回は修正しない）
- PHASE 3 の完了時点で停止する。フロントエンドの実装と AWS の変更はまだ行わない
- 組み合わせの評価は、性能が許容できるなら**最適解を保証する方式を優先する** → 分枝限定法を採用（K=10 の近似は廃止）
- マージ前に reviewer の再レビューを 1 回だけ行う。重大な指摘だけを修正し、軽微な改善は MVP 後の課題にする
- 引き継ぎ専用の PR は作らない（progress.md の更新は PR #3 に含める）
- PHASE 4 は新しいセッションで着手する

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

### PHASE 3（2026-11-25 完了、PR #3）
- [x] researcher：大阪エリアの範囲（公式：大阪市のみ、エリア外への返却は不可）、接頭辞・Z 系・バッテリー交換専用の拠点（公式資料なし）、ODPT の規約（上限は未確認）
- [x] 実データの分析 → 大阪エリアの判定方法の決定（`docs/plan.md` §1）
- [x] evaluator：評価シナリオ 47 件と、未確定の仕様 9 件 → 決定して明文化（`docs/engineering-notes.md` §2・§7）
- [x] `backend/app/`（routing / gbfs / presets）と `backend/main.py` の置き換え（ダミーの応答を削除）
- [x] テスト 427 件（経路計算・GBFS・API・Lambda）。テストから外部ネットワークに接続できないガード付き
- [x] 最終確認（ユーザーの指示）：組み合わせの評価を K=10 の近似から**最適解を保証する分枝限定法**に変更。総当たりとの性能比較、大阪エリア判定の技術的負債の記録、フィクスチャのライセンスと機密情報の確認（README を追加）
- [x] 実 GBFS での疎通確認と性能の計測（`backend/tools/smoke_gbfs.py`）
- [x] reviewer（1 回目）：must 3 件を修正、should は修正または PHASE 6 への記録で対応
- [x] reviewer（2 回目、分枝限定法の再レビュー）：**重大な指摘なし**。下限の正当性（三角不等式、速度は max で取るので速度の大小が入れ替わっても成立）、枝刈りによる取りこぼしなし、同値の扱い（`>` best + 1e-9 なので同値の組は刈らない）、テスト側の総当たりの独立性、候補がない場合の挙動を確認済み
- [x] PR #3 の作成、CI（`check`）の成功、squash マージ

## 未完了タスク（以降のフェーズ）
- [ ] **PHASE 4**：フロントエンド（React / TS / Vite）
- [ ] **PHASE 5**：ローカル結合確認
- [ ] **PHASE 6**：AWS CLI の導入と認証設定、棚卸し、Lambda ビルド、HTTP API、S3 + CloudFront、CloudWatch
- [ ] **PHASE 7**：総合評価・技術知見の整理

## 重要な設計判断（詳細は `docs/engineering-notes.md` §2）
- AWS 構成：API Gateway HTTP API → Lambda（プロキシ統合、Mangum）、フロントは S3 + CloudFront
- 経路は直線距離 × 迂回係数 1.3 で概算し、利用可能な全てのポートの組から最小を選ぶ（分枝限定法。最適解を保証。当初の K×K は廃止）
- GBFS の取得に失敗したら 503 を返し、ダミー値は返さない
- 品質ゲートは `scripts/check.py` の 1 か所に集約（人・Stop Hook・CI で共通）。CI には環境構築だけを書く
- サブエージェントは読み取り専用とし、ファイルの変更はメインエージェントだけが行う
- コミットには noreply アドレスを使う（ローカル設定にのみ設定）

## 未解決の問題
- **技術的負債：大阪エリアの判定**は、実データにもとづく仮定（接頭辞の意味と Z 系の扱いは公式資料なし）。新しいポートが市外に追加されると誤判定しうる。改善方法（行政区域のポリゴンによる判定など）は `docs/engineering-notes.md` §7
- 分枝限定法の最悪の計算量は総当たりと同じ（下限が効かない配置では約 0.8 秒）。実データでは起きていない
- ODPT のアクセス頻度の上限と、クレジット表記の正式な文言は未確認
- GBFS の取得タイムアウトはソケット操作ごとの値で、合計の締め切りではない → PHASE 6 で Lambda のタイムアウトを 15 秒にする
- API Gateway のステージは `$default` を使う（別名ならパスがずれる） → PHASE 6
- **Git Credential Manager の資格情報の保存エラー**：未解決。ユーザーの指示で、今回は記録だけにして修正しない
- **MVP 後の課題（reviewer の軽微な指摘）**：(1) `RouteParams` を変えた場合（自転車 < 徒歩、迂回係数の変更）のランダムテストがない（テスト側の総当たりのパラメータ化が必要）、(2) 同値のタイブレークを意図的に作るテストは B8 の 1 件だけ、(3) `test_pruning_reduces_evaluated_pairs` の閾値は経験値なので根拠のコメントを足す、(4) テストのオラクルが大阪エリアの条件（除外リストの ID）を複製しているので、出典をコメントに書く
- reviewer（1 回目）の nit で未対応のもの：キャッシュの経過時間に `time.time` を使っている（時計の巻き戻りに弱い）、status のない info を数えていない、`last_updated` が float だと全体が 503 になる（実フィードは int）
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
- **PR での確認（観測した事実）**：PR #2 の最初のコミット `233bb55` で確認した。`gh pr view` を 5〜6 秒おきに実行した結果（時刻は UTC）は次のとおり。
  - 09:00:44：`mergeStateStatus=UNKNOWN`、チェックなし（PR 作成の直後）
  - 09:00:52〜09:01:03：**`BLOCKED`**。`check` は `IN_PROGRESS`
  - 09:01:09：**`CLEAN`**。`check` は `COMPLETED/SUCCESS`
  - `gh pr checks --required` で、`check` が**必須チェック**として表示された（pass、15 秒）。check-run は github-actions（app_id 15368）が作成していた
  - 「必須チェックが終わるまではマージできず、成功すると解除される」ことを確認した。ただし、BLOCKED の原因がほかのルールではなく必須チェックだけであることは、状態の変化から推定したもので、API で原因を直接確かめたわけではない
  - この記録を追記したコミットの CI は、PR #2 の上で確認する（docs への再追記はしない）
- **未検証**：`main` への直接 push と force push が実際に拒否されるか。ユーザーの指示により、検証目的の直接 push は行わない。dry-run もサーバー側のルールを評価しないため、根拠にしない。

## 今後の改善事項（MVP 後）
- GitHub Actions を、メジャータグ（`actions/checkout@v5`、`actions/setup-python@v6`）ではなくコミット SHA に固定する（Dependabot での更新もあわせて検討する）

## 最新の品質チェック結果
- 2026-11-25（セッション 3、`feature/route-search`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：427 件成功（警告 1 件：Mangum の DeprecationWarning）
  - 実 GBFS での疎通確認（手動）：取得と検証 0.68 秒、大阪エリアのポート 745 件、経路計算（分枝限定法）中央値 3.05ms・最大 4.48ms、素朴な総当たり 中央値 778ms、両者の結果の差 0 件（56 組）
- 2026-11-25（セッション 2、`feature/ci`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：9 件成功（警告 1 件：Mangum の DeprecationWarning）
  - CI と同じ `CHECK_PYTHON` の経路でも成功。Python が見つからない場合は exit 2 になることも確認
- GitHub Actions：PR #1 でジョブ `check` が pass（ruff OK、pytest 9 件、`check.py: ALL PASSED`）

## 次にやること（PHASE 4：フロントエンド実装、新しいセッション）
### 開始条件（着手前に確認する）
1. このファイルを読み、`git switch main && git pull --ff-only` と `git log --oneline -5` で、PR #3 の squash コミットが `main` にあることを確認する。`gh api user --jq .login` が `EnKyria` であることも確認する
2. `python scripts/check.py` が `main` で ALL PASSED になる（backend の 427 件）
3. `feature/route-search` が削除済みである（`git branch -a`）
4. 依存の追加（Node.js のパッケージ：React、Vite、TypeScript、Vitest、Testing Library など）は、**ユーザーの承認を得てから**行う。Node.js と npm のバージョンも先に確認する

### 作業内容
- `feature/frontend` などのブランチで `frontend/` を作る（React + TS + Vite、`.claude/rules/frontend.md` に従う）
- API の型は `src/api/` に 1 か所だけ定義し、backend の Pydantic モデル（`backend/main.py` の `PresetsResponse`、`RouteResponse` など）と同じフィールド名にする
- 画面：プリセットの選択 → 検索 → 結果。`recommended`、`bike_share: null`（候補なし）、各区間の内訳、ローディング・エラー（400 / 422 / 503 / 通信失敗）の表示。503 は「ポート情報を取得できません」
- `data.attribution` と `data.license_url` によるクレジット表示、`data.last_updated` の表示
- 所要時間は概算（直線距離 × 迂回係数）であることを画面に明記する
- CORS：ローカルの結合（PHASE 5）では Vite の proxy を使うか FastAPI に CORS を設定する（本番は HTTP API 側で設定する予定）
- `package.json` の `lint` / `typecheck` / `test` を `scripts/check.py` が実行することを確認する
