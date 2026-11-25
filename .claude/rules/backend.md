---
paths:
  - "backend/**/*.py"
  - "backend/requirements*.txt"
  - "backend/pyproject.toml"
---

# Backend 規約（Python 3.12 / FastAPI / Pydantic v2 / Mangum）

## 構成
- `backend/main.py` は FastAPI アプリと `handler = Mangum(app)` の定義に留める。
  ロジックが増えたら `backend/app/` 配下に分ける（例：`gbfs.py` 取得、`routing.py` 経路計算）。
- 経路計算は純粋関数として書き、HTTP・GBFS 取得から分離する（入力：ポート一覧と地点、出力：候補）。
  こうするとネットワークなしでテストできる。

## API
- リクエスト・レスポンスは必ず Pydantic モデルで型を定義し、`response_model` を指定する。
- 入力エラーは 422（Pydantic）、業務エラーは 400、GBFS 取得失敗は 503 とし、`detail` は日本語で書く。
- **GBFS 取得に失敗したときは、ダミーや古いデータを実データとして返さない。** 503 を返す。
  キャッシュを使う場合は、レスポンスにデータの取得時刻（`last_updated`）を含める。
- API Gateway HTTP API のプロキシ統合（payload format 2.0）経由で呼ばれる前提で書く。
  パスのプレフィックスは `/api/...` で統一する（`/health` は例外）。

## 外部通信
- HTTP クライアントにはタイムアウトを必ず指定する（目安は 5 秒）。
- 依存を増やすと Lambda の zip が大きくなる。標準ライブラリ（`urllib.request`）で足りるなら追加しない。
  追加する場合は `requirements.txt` に `==` でバージョンを固定する。

## Lambda 互換
- ネイティブ拡張を持つ依存（pydantic_core 等）は manylinux x86_64 / cp312 向けにビルドする。
  Windows でインストールした site-packages をそのまま zip にしない。
- モジュールのトップレベルで重い処理やネットワーク通信をしない（コールドスタートとテスト容易性のため）。
- 設定値は環境変数から読む。秘密情報をコードに書かない。

## スタイル
- 整形と lint は ruff（設定はルートの `pyproject.toml`）に従う。型ヒントは必須。
