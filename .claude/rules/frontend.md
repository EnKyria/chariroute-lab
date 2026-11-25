---
paths:
  - "frontend/**/*"
---

# Frontend 規約（React / TypeScript / Vite）

## 方針
- MVP は 1 画面（出発地・目的地のプリセット選択 → 検索 → 結果表示）。ルーティングライブラリや状態管理ライブラリは入れない。
- 地図は必要になった時点で検討する。MVP の完了条件には含めない。
- S3 + CloudFront で静的配信する。SSR や Node サーバー前提の機能は使わない。

## TypeScript
- `strict: true` を有効にする。`any` は禁止（どうしても必要な場合は `unknown` にして型を絞り込む）。
- API のレスポンス型は `src/api/` に 1 か所だけ定義し、backend の Pydantic モデルと同じ名前のフィールドにする。

## API 呼び出し
- API のベース URL は `import.meta.env.VITE_API_BASE_URL` から読む。URL をコードに直接書かない。
- ローディング、エラー（400 / 422 / 503 / 通信失敗）、0 件の 3 状態を必ず画面に表示する。
  503 のときは「ポート情報を取得できません」と表示し、推定値をそれらしく見せない。
- GBFS データのクレジット（CC BY 4.0、出典：公共交通オープンデータ協議会 / ドコモ・バイクシェア）を画面に表示する。

## 品質
- `package.json` に `lint` / `typecheck` / `test` スクリプトを定義する。`scripts/check.py` がこれらを自動で実行する。
- テストは Vitest + Testing Library で、ユーザーから見える振る舞いを検証する。
- 依存の追加は最小限にし、追加理由を `docs/engineering-notes.md` に記録する。
