# ChariRoute（chariroute-lab）

大阪市内でドコモ・バイクシェアを使うときに、効率的な貸出ポートと返却ポートの組み合わせを探すアプリ（個人利用・学習用の MVP）。

- バックエンド：FastAPI（Python 3.12）。AWS Lambda では Mangum 経由で動く
- フロントエンド：React + TypeScript + Vite + Leaflet（OpenStreetMap のタイル）
- データ：ODPT が公開しているドコモ・バイクシェアの GBFS（CC BY 4.0）

所要時間は推定値です。現在の実装は、直線距離 × 迂回係数で計算しています。
PHASE 4.5 では、FOSSGIS の OSRM による道路に沿った 3 区間（徒歩・自転車・徒歩）の経路、GPS・地点検索・地図のタップによる地点の指定を追加し、徒歩のみとの比較は廃止します（[docs/plan.md](docs/plan.md) §6）。

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
# 1. API サーバー（http://127.0.0.1:8000）
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# 2. 画面（http://127.0.0.1:5173）。/api へのリクエストは Vite の proxy で 127.0.0.1:8000 に転送される
cd frontend
npm run dev
```

ブラウザで http://127.0.0.1:5173 を開きます。API のスキーマは http://127.0.0.1:8000/docs で確認できます。

- API サーバーは、検索のたびに ODPT の GBFS にアクセスします（60 秒間はキャッシュを使う）。インターネットへの接続が必要です。
- GBFS の取得に失敗したときの表示（503）を確かめるには、取得先を到達できない URL にして起動します：
  `GBFS_BASE_URL=https://127.0.0.1:9/gbfs .venv/Scripts/python.exe -m uvicorn main:app --port 8000`

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
| `VITE_API_BASE_URL` | frontend | API のベース URL。空なら同一オリジン（本番は CloudFront、ローカルは Vite の proxy） |
| `VITE_TILE_URL` | frontend | 地図タイルの URL テンプレート。空なら OpenStreetMap の公式タイル |

`VITE_` で始まる変数はビルド成果物に含まれ、ブラウザから見えます。秘密の値は入れないでください。

## ドキュメント

- [docs/plan.md](docs/plan.md)：設計方針と実装計画
- [docs/progress.md](docs/progress.md)：進捗と引き継ぎ
- [docs/engineering-notes.md](docs/engineering-notes.md)：技術選定・設計判断・発生した問題の記録

## クレジット

- ポート情報：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会（[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.ja)）のデータを加工して作成
- 地図：© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
