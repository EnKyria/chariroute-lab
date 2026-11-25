# ChariRoute（chariroute-lab）

大阪市内でドコモ・バイクシェアを使うときに、効率的な貸出ポートと返却ポートの組み合わせを探すアプリ（個人利用・学習用の MVP）。

- バックエンド：FastAPI（Python 3.12）。AWS Lambda では Mangum 経由で動く
- フロントエンド：React + TypeScript + Vite + Leaflet（OpenStreetMap のタイル）
- データ：ODPT が公開しているドコモ・バイクシェアの GBFS（CC BY 4.0）
- 道路の経路：FOSSGIS の OSRM（`routed-foot` / `routed-bike`）。地点検索：Nominatim（OpenStreetMap）

出発地と目的地は、プリセット・現在地（GPS）・地点検索（駅名・施設名）・地図のタップで指定できます。
貸出・返却ポートの候補（直線距離で各最大 11 か所）の全ての組を OSRM の道路距離で評価し、
徒歩（出発地 → 貸出）・自転車（貸出 → 返却）・徒歩（返却 → 目的地）の合計の推定所要時間が最小の組を、
道路に沿った経路として表示します（[docs/plan.md](docs/plan.md) §6）。

- 所要時間は、道路距離 ÷ 一定の速度（徒歩 4.8 km/h・自転車 15 km/h）+ 貸出・返却の手続き（各 1 分）の**推定値**です。
- 候補を直線距離で絞り込むため、全てのポートの組の中での最適解は保証しません。
- 外部の公開サービス（FOSSGIS・Nominatim）は、個人利用・非商用・低頻度の範囲で利用しています。
  リクエストは各サービスで 1.1 秒以上の間隔を空けて直列に送り、自動リトライはしません。
- 運営者の連絡先：chariroute.dev@gmail.com

## 必要な環境

| ツール | バージョン | 備考 |
|---|---|---|
| Python | 3.12 | Lambda のランタイムに合わせる |
| Node.js | 22 系の 22.22.2 以上 | `frontend/.nvmrc`。Vite 8 は 22.12 以上、jsdom 31 は 22.22.2 以上が必要 |
| npm | Node.js に同梱 | |

コマンドは Windows の Git Bash を前提に書いています。macOS や Linux では、`.venv/Scripts/python.exe` を `.venv/bin/python` に読み替えてください。

## セットアップ（初回のみ）

```bash
# バックエンド
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt

# フロントエンド（package-lock.json のとおりにインストールする）
cd frontend && npm ci && cd ..
```

## ローカルでの起動

ターミナルを 2 つ使います。

```bash
# 1. API サーバー（http://127.0.0.1:8000）。外部の経路・地点検索サービスは、明示的に有効にしたときだけ使う
cd backend
EXTERNAL_APIS_ENABLED=true .venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

```bash
# 2. 画面（http://localhost:5173）。/api へのリクエストは Vite の proxy で 127.0.0.1:8000 に転送される
cd frontend
npm run dev
```

ブラウザで http://localhost:5173 を開きます（Vite は `localhost` で待ち受けます。環境によっては `127.0.0.1` では開けません）。
現在地の取得は、HTTPS か `localhost` で開いたページでだけ動きます。API のスキーマは http://127.0.0.1:8000/docs で確認できます。

- **`EXTERNAL_APIS_ENABLED=true` を付けないと**、FOSSGIS の OSRM・Nominatim には送信せず、経路検索と地点検索は 503（「この環境では…停止しています」）になります（本番の既定と同じ。[docs/plan.md](docs/plan.md) §7.3）。`true` 以外の値（`1`・`yes` など）も無効として扱います。
- API サーバーは、検索のたびに ODPT の GBFS（60 秒間はキャッシュを使う）と FOSSGIS の OSRM（1 回の検索で 5 リクエスト）にアクセスします。インターネットへの接続が必要です。1 回の検索には 15〜20 秒ほどかかります（自転車の Table が約 10 秒かかるため）。
- **uvicorn は 1 プロセスで動かします**（`--workers` を使わない）。リミッターがプロセスごとなので、複数のプロセスでは 1 秒 1 回を保証できません。
- **OSRM のスモークテスト（`backend/tools/smoke_osrm.py`）と開発サーバーを同時に動かさないでください**（FOSSGIS への同時接続を 1 つに保つため）。検索ボタンの連打や、自動化した繰り返しの検索もしないでください。
- GBFS の取得に失敗したときの表示（503）を確かめるには、取得先を到達できない URL にして起動します：
  `GBFS_BASE_URL=https://127.0.0.1:9/gbfs .venv/Scripts/python.exe -m uvicorn main:app --port 8000`
- 道路の経路を取得できないときの表示（503）も、同じように `OSRM_FOOT_URL=https://osrm.invalid/foot OSRM_BIKE_URL=https://osrm.invalid/bike` で確かめられます（FOSSGIS には接続しません）。

## 品質チェック

```bash
python scripts/check.py            # backend（ruff・pytest）と frontend（lint・typecheck・test・build）の全件
python scripts/check.py frontend   # frontend だけ
```

- push の前に必ず実行します。CI（GitHub Actions）でも同じスクリプトを実行します。
- テストは外部のネットワークに接続しません。
- Windows で `frontend` の `npm test` を直接実行するときは、**大文字のドライブ文字**（`D:\...`）のディレクトリから実行してください。小文字の `d:\` からだと Vitest が失敗します（[docs/engineering-notes.md](docs/engineering-notes.md) §5）。

## 環境変数（任意）

| 変数 | 使う場所 | 内容 |
|---|---|---|
| `GBFS_BASE_URL` | backend | GBFS の取得先（https のみ）。既定は ODPT の docomo-cycle |
| `OSRM_FOOT_URL` / `OSRM_BIKE_URL` | backend | OSRM の取得先（https のみ）。既定は `https://routing.openstreetmap.de/routed-foot` / `routed-bike` |
| `NOMINATIM_URL` | backend | Nominatim の取得先（https のみ）。既定は `https://nominatim.openstreetmap.org` |
| `EXTERNAL_APIS_ENABLED` | backend | `true` のときだけ OSRM・Nominatim に送信する。**既定（未設定）は無効**。ODPT の GBFS は対象外 |
| `ORIGIN_VERIFY_SECRET` | backend | CloudFront が付ける `X-Origin-Verify` ヘッダーと照合する共有シークレット（32 文字以上）。設定したとき、または Lambda 上では検証が必須になり、Lambda 上で未設定なら全て 403。ローカルでは通常設定しない |
| `OUTBOUND_USER_AGENT` | backend | 外部サービスに送る User-Agent。既定は `ChariRoute/0.1 (+https://github.com/EnKyria/chariroute-lab)` |
| `OUTBOUND_REFERER` | backend | 外部サービスに送る Referer。設定したときだけ付ける（本番の URL が決まったら設定する） |
| `VITE_API_BASE_URL` | frontend | API のベース URL。空なら同一オリジン（本番は CloudFront、ローカルは Vite の proxy） |
| `VITE_TILE_URL` | frontend | 地図タイルの URL テンプレート。空なら OpenStreetMap の公式タイル |

`VITE_` で始まる変数はビルド成果物に含まれ、ブラウザから見えます。秘密の値は入れないでください。

## AWS 用のビルド

```bash
python scripts/build_lambda.py   # build/lambda.zip（Linux 用の wheel）と build/lambda-report.json
cd frontend && npm run build     # frontend/dist
```

デプロイの手順は [docs/deploy.md](docs/deploy.md) にあります（AWS の操作は、手順ごとに承認を得てから行います）。

## ドキュメント

- [docs/plan.md](docs/plan.md)：設計方針と実装計画
- [docs/deploy.md](docs/deploy.md)：AWS へのデプロイ・緊急停止・削除の手順
- [docs/progress.md](docs/progress.md)：進捗と引き継ぎ
- [docs/engineering-notes.md](docs/engineering-notes.md)：技術選定・設計判断・発生した問題の記録

## クレジット

- ポート情報：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会（[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)）のデータを加工して作成
- 地図・道路データ：© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors（ODbL）。地図の誤りは [fixthemap](https://www.openstreetmap.org/fixthemap) から報告できます
- 道路の経路：[OSRM / FOSSGIS](https://routing.openstreetmap.de/about.html)（routing.openstreetmap.de）
- 地点検索：[Nominatim](https://nominatim.org/) / OpenStreetMap
