# 設計方針と実装計画

最終更新：2026-11-25

## 1. データソース（2026-11-25 に確認済み）

| 項目 | 内容 |
|---|---|
| フィード | `https://api-public.odpt.org/api/v4/gbfs/docomo-cycle/gbfs.json`（GBFS v2.3、ttl 60 秒） |
| 使用するファイル | `station_information.json`（約 0.8MB）、`station_status.json`（約 1MB） |
| 認証 | 不要（ODPT の公開エンドポイント）。HTTP 200 で取得できることを確認済み |
| 提供者・ライセンス | 株式会社ドコモ・バイクシェア / CC BY 4.0（クレジット：公共交通オープンデータ協議会）[ckan.odpt.org](https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-nationwide-bikeshare)（全国版。PHASE 1 で記録した `d-bikeshare` は東京エリアのデータセットだったため、2026-11-25 に訂正）。クレジット表示の提供者名は「株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会」 |
| 収録範囲 | **全国**のポート 6,229 件。大阪市付近の矩形範囲（緯度 34.55–34.78、経度 135.40–135.60）には 746 件 |
| `station_information` の項目 | `station_id`, `name`, `lat`, `lon`, `capacity`, `region_id` |
| `station_status` の項目 | `station_id`, `is_installed`, `is_renting`, `is_returning`, `num_bikes_available`, `num_docks_available`, `last_reported` |

### 大阪エリアの判定（2026-11-25、PHASE 3 で決定。根拠は `docs/engineering-notes.md` §2）
- 公式：大阪エリアは大阪市で、エリア外（京都・奈良を含む）には返却できない（[docomo-cycle.jp/osaka](https://docomo-cycle.jp/osaka/)）。
- GBFS に地域の項目はない（`system_regions` は 404、`region_id` は全国にまたがる）。
- 判定（仮定。誤判定の可能性と改善方法は `docs/engineering-notes.md` §7「技術的負債」）：名前が `^[A-Z]-\d+\.` で始まる ∧ 緯度 34.55〜34.78・経度 135.35〜135.65 ∧ 東大阪市内の 2 件（ID 7808、7810）を除く。実装は `backend/app/gbfs.py`。
- 「【バッテリー交換のみ】」の拠点は、名前の条件と空き数 0 の両方で除外される。

### 未確認事項
- ポート名の接頭辞の意味と、Z 系のポートの扱い（公式資料なし）。新しいポートが市外に追加されると誤判定しうる。
- ODPT の公開 API のアクセス頻度の上限（規約の本文で確認できなかった）。ttl のキャッシュで、1 つの実行環境から 1 分に 2 回までに抑えている。
- クレジット表記の正式な文言（ckan.odpt.org の FAQ は未確認）。

## 2. 経路計算

```
合計所要時間 = 徒歩(出発地 → 貸出ポート A) + 自転車(A → 返却ポート B) + 徒歩(B → 目的地)
```
- 距離はハバーサイン式で求めた直線距離 × 迂回係数（初期値 1.3）。
- 速度の初期値は徒歩 4.8 km/h、自転車 15 km/h。貸出・返却の手続き時間として各 1 分を加える。
- 候補の選び方：
  - A は「貸出可能な」全てのポート、B は「返却可能な」全てのポート。A = B の組は除く。
  - 全ての (A, B) の中で合計が最小の組を採用する。**この所要時間モデルでの最適解を保証する**（2026-11-25 変更）。
  - 計算は分枝限定法（合計の下限で、最適解になりえない組を打ち切る）。結果は全探索と同じで、実データでは 1 回 約 3ms（素朴な総当たりは約 0.7 秒）。根拠と計測は `docs/engineering-notes.md` §2・§7。
  - 当初の「近い順に K=10 件ずつ」の方式は、最適解を保証しないため廃止した。
- 徒歩のみの所要時間も計算して並べて返す。自転車のほうが遅い場合もそのまま返し、UI で判断できるようにする。
- パラメータは定数にまとめ、テストで値を固定する（評価駆動：代表的な地点ペアの結果を比較できるようにする）。

## 3. API（PHASE 3 で実装済み）
- `GET /health`
- `GET /api/presets`：プリセット地点の一覧（id, name, lat, lon）。8 か所。`backend/app/presets.py` だけで定義する。
- `POST /api/routes/search`：`{origin_id, destination_id}` を受け取り、`origin`、`destination`、`recommended`（`bike_share` / `walk`）、`bike_share`（ポート A/B、各区間の距離と所要時間、合計。候補がなければ `null`）、`walk`、`data`（`last_updated`（JST）、提供者、ライセンス、クレジット表記）を返す。
  - 旧 `{origin, destination}` 文字列 API からの仕様変更。特性テストは置き換えた。
  - 判定の順序は 422（形式）→ 400（不明な地点・同じ地点）→ 503（GBFS の取得失敗）。
  - 503 にする条件：通信エラー、タイムアウト、HTTP エラー、不正な JSON、必須構造の欠落、大阪エリアのポートが 0 件、データが 900 秒より古い、`last_updated` が 300 秒より未来。
  - キャッシュは経過時間が ttl（フィードの値、上限 300 秒）未満で、かつデータが古すぎない間だけ使う。期限切れのキャッシュは失敗時にも返さない。
  - 個々のポートのレコードが不正なら、そのポートだけを捨てる。
  - `bike_share` は、利用可能な全ての貸出・返却ポートの組の中で合計所要時間が最小の組（このモデルでの最適解）。所要時間は直線距離 × 迂回係数による概算で、実際の道路の経路ではない。
  - `data.attribution` はクレジット表記（「出典：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会（CC BY 4.0）のポート情報を加工して作成」）。`data.dataset_url` はデータセットのページ。

## 4. AWS 構成

| 要素 | 方針 |
|---|---|
| API | API Gateway **HTTP API**、Lambda プロキシ統合（payload format 2.0）、CORS は HTTP API 側で設定する |
| 計算 | Lambda（python3.12 / x86_64）、`main.handler`、メモリ 256MB 程度、タイムアウト **15 秒**（GBFS の取得はファイルごとに 4 秒のソケットタイムアウトで、合計の締め切りではないため余裕を持たせる。PHASE 3 の reviewer の指摘） |
| フロント | S3（非公開）+ CloudFront（OAC） |
| 監視 | CloudWatch Logs（保持期間を設定）、Lambda と API Gateway の標準メトリクス |
| IAM | Lambda 実行ロールは `AWSLambdaBasicExecutionRole` 相当のみ。デプロイ用の権限は別に最小化する |
| 既存環境 | **未確認**。AWS CLI 未導入・認証情報なし。AWS CLI の導入は承認済みだが、実際の導入と認証設定は PHASE 6 で行う。その後、読み取り専用のコマンドで棚卸しする |

- API Gateway のステージは `$default` を使う。別名のステージだとパスにステージ名が付き、FastAPI のルート（`/api/...`）にマッチしなくなる（使う場合は Mangum の `api_gateway_base_path` を設定する）。
- 環境変数 `GBFS_BASE_URL`（任意、https のみ）で取得先を変更できる。
- デプロイ方法は棚卸しの結果で決める。既存の Lambda があれば `update-function-code` で再利用し、IaC 化は MVP 後に回す。

## 5. フェーズ計画

フェーズ番号はこの表で統一する（2026-11-25 決定）。進捗は `docs/progress.md` で管理する。

| PHASE | 名称 | 主なタスク | 完了条件 |
|---|---|---|---|
| 1 | 開発基盤・ハーネス構築 | venv、requirements、特性テスト、Git、CLAUDE.md / rules / settings / Stop Hook / agents、**reviewer による最終レビュー後に初回コミット** | `scripts/check.py` が成功し、初回コミット済み |
| 2 | GitHub・CI 構築 | GitHub リポジトリの作成と push、GitHub Actions で `scripts/check.py` を実行、ブランチ運用の開始 | PR で CI が緑になる |
| 3 | バックエンド実装 | GBFS の取得・キャッシュ、大阪市内のポート抽出、失敗時に 503、経路計算（組み合わせの評価）、プリセット API | フィクスチャを使ったテストと、代表的な地点ペアのテストが成功 |
| 4 | フロントエンド実装 | React / TS / Vite で 1 画面、3 状態（ローディング・エラー・0 件）の表示、クレジット表示 | lint / typecheck / test が成功 |
| 5 | ローカル結合確認 | uvicorn と Vite dev server で、実際の GBFS を使ってエンドツーエンドで確認。Mangum 経由のテスト | ローカルで検索が成功し、GBFS の取得失敗時に 503 が画面に表示される |
| 6 | AWS デプロイ | AWS CLI の導入と認証設定、既存リソースの読み取り専用の棚卸し、Lambda ビルドスクリプト（manylinux/cp312）、HTTP API、S3 + CloudFront、CloudWatch | 公開 URL で検索でき、CloudWatch でログを確認できる |
| 7 | 総合評価・技術知見の整理 | 評価シナリオでの総合テスト、`docs/engineering-notes.md` の整理、面接向けの説明の準備 | 評価結果と知見が docs にまとまっている |

- AWS リソースの作成・変更・削除は、PHASE 6 であっても**操作ごとに個別にユーザーの承認を得る**。
