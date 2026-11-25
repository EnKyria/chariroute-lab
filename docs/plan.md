# 設計方針と実装計画

最終更新：2026-11-25

## 1. データソース（2026-11-25 に確認済み）

| 項目 | 内容 |
|---|---|
| フィード | `https://api-public.odpt.org/api/v4/gbfs/docomo-cycle/gbfs.json`（GBFS v2.3、ttl 60 秒） |
| 使用するファイル | `station_information.json`（約 0.8MB）、`station_status.json`（約 1MB） |
| 認証 | 不要（ODPT の公開エンドポイント）。HTTP 200 で取得できることを確認済み |
| 提供者・ライセンス | 株式会社ドコモ・バイクシェア / CC BY 4.0（クレジット：公共交通オープンデータ協議会）[ckan.odpt.org](https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-bikeshare) |
| 収録範囲 | **全国**のポート 6,229 件。大阪市付近の矩形範囲（緯度 34.55–34.78、経度 135.40–135.60）には 746 件 |
| `station_information` の項目 | `station_id`, `name`, `lat`, `lon`, `capacity`, `region_id` |
| `station_status` の項目 | `station_id`, `is_installed`, `is_renting`, `is_returning`, `num_bikes_available`, `num_docks_available`, `last_reported` |

### 未解決事項（実装前に確認する）
- **大阪市内のポートの抽出方法**。`system_regions.json` は 404 で、`region_id` の意味がわからない（同じ ID に他県のポートも含まれる）。
  案：矩形範囲で粗く絞り込んだ後、ポート名の接頭辞（エリアコード）の傾向を調べて決める。
- **エリアをまたいだ返却の可否**。ドコモ・バイクシェアでは原則として同じエリア内でしか返却できない（[OSM Wiki](https://wiki.openstreetmap.org/wiki/Import/Catalogue/GBFS_Docomo_Bike_Share_Import)）。
  大阪市内で完結させれば問題ない想定だが、隣接市のポートを候補に含めない処理が必要。
- ODPT 自体の利用規約（アクセス頻度の上限など）を確認する。ttl に合わせたキャッシュで、アクセスは 1 分に 1 回程度に抑える。

## 2. 経路計算

```
合計所要時間 = 徒歩(出発地 → 貸出ポート A) + 自転車(A → 返却ポート B) + 徒歩(B → 目的地)
```
- 距離はハバーサイン式で求めた直線距離 × 迂回係数（初期値 1.3）。
- 速度の初期値は徒歩 4.8 km/h、自転車 15 km/h。貸出・返却の手続き時間として各 1 分を加える。
- 候補の選び方：
  - A は出発地から近い順に「利用可能な」ポートを最大 K 件（初期値 10）。
  - B は目的地から近い順に「返却可能な」ポートを最大 K 件。
  - K×K 通り（100 通り程度）をすべて評価し、合計が最小の組を採用する。
- 徒歩のみの所要時間も計算して並べて返す。自転車のほうが遅い場合もそのまま返し、UI で判断できるようにする。
- パラメータは定数にまとめ、テストで値を固定する（評価駆動：代表的な地点ペアの結果を比較できるようにする）。

## 3. API（予定）
- `GET /health`
- `GET /api/presets`：プリセット地点の一覧（id, name, lat, lon）。地点はバックエンドに 1 か所だけ定義する。
- `POST /api/routes/search`：`{origin_id, destination_id}` を受け取り、自転車経路（ポート A/B、各区間の所要時間）、徒歩のみの経路、`data_last_updated` を返す。
  - 現行の `{origin, destination}` 文字列 API からの**仕様変更**になる。特性テストもあわせて更新する。
  - GBFS の取得に失敗したら 503。成功から ttl 以内のデータだけキャッシュする（Lambda のメモリ内）。

## 4. AWS 構成

| 要素 | 方針 |
|---|---|
| API | API Gateway **HTTP API**、Lambda プロキシ統合（payload format 2.0）、CORS は HTTP API 側で設定する |
| 計算 | Lambda（python3.12 / x86_64）、`main.handler`、メモリ 256MB 程度、タイムアウト 10 秒 |
| フロント | S3（非公開）+ CloudFront（OAC） |
| 監視 | CloudWatch Logs（保持期間を設定）、Lambda と API Gateway の標準メトリクス |
| IAM | Lambda 実行ロールは `AWSLambdaBasicExecutionRole` 相当のみ。デプロイ用の権限は別に最小化する |
| 既存環境 | **未確認**。AWS CLI 未導入・認証情報なし。AWS CLI の導入は承認済みだが、実際の導入と認証設定は PHASE 6 で行う。その後、読み取り専用のコマンドで棚卸しする |

- デプロイ方法は棚卸しの結果で決める。既存の Lambda があれば `update-function-code` で再利用し、IaC 化は MVP 後に回す。

## 5. フェーズ計画

フェーズ番号はこの表で統一する（2026-11-25 決定）。進捗は `docs/progress.md` で管理する。

| PHASE | 名称 | 主なタスク | 完了条件 |
|---|---|---|---|
| 1 | 開発基盤・ハーネス構築 | venv、requirements、特性テスト、Git、CLAUDE.md / rules / settings / Stop Hook / agents、**reviewer による最終レビュー後に初回コミット** | `scripts/check.py` が成功し、初回コミット済み |
| 2 | GitHub・CI 構築 | GitHub リポジトリの作成と push、GitHub Actions で `scripts/check.py` を実行、ブランチ運用の開始 | PR で CI が緑になる |
| 3 | バックエンド実装 | GBFS の取得・キャッシュ、大阪市内のポート抽出、失敗時に 503、経路計算（K×K の評価）、プリセット API | フィクスチャを使ったテストと、代表的な地点ペアのテストが成功 |
| 4 | フロントエンド実装 | React / TS / Vite で 1 画面、3 状態（ローディング・エラー・0 件）の表示、クレジット表示 | lint / typecheck / test が成功 |
| 5 | ローカル結合確認 | uvicorn と Vite dev server で、実際の GBFS を使ってエンドツーエンドで確認。Mangum 経由のテスト | ローカルで検索が成功し、GBFS の取得失敗時に 503 が画面に表示される |
| 6 | AWS デプロイ | AWS CLI の導入と認証設定、既存リソースの読み取り専用の棚卸し、Lambda ビルドスクリプト（manylinux/cp312）、HTTP API、S3 + CloudFront、CloudWatch | 公開 URL で検索でき、CloudWatch でログを確認できる |
| 7 | 総合評価・技術知見の整理 | 評価シナリオでの総合テスト、`docs/engineering-notes.md` の整理、面接向けの説明の準備 | 評価結果と知見が docs にまとまっている |

- AWS リソースの作成・変更・削除は、PHASE 6 であっても**操作ごとに個別にユーザーの承認を得る**。
