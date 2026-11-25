# GBFS テスト用フィクスチャ

このディレクトリの `station_information.json` と `station_status.json` は、
次のオープンデータを加工して作成したものです。

- 出典：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会
  「ドコモ・バイクシェア バイクシェア関連情報」（GBFS フィード `https://api-public.odpt.org/api/v4/gbfs/docomo-cycle/`）
  データセット：<https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-nationwide-bikeshare>
- ライセンス：[クリエイティブ・コモンズ 表示 4.0 国際（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.ja)
- 取得日時：2026-11-25（`last_updated` = 1795597594）

## 加工の内容
- 全国のポート約 6,200 件から、本リポジトリのプリセット地点（`backend/app/presets.py`）の
  半径 1km 以内にあるポートと、テストのための除外ケースの実例（那覇・東大阪・バッテリー交換専用の拠点）の
  計 153 件を抽出した。
- 抽出後に JSON を整形した（インデント・改行）。各レコードの値は変更していない。
- テストの中では、異常系を再現するため、読み込んだデータをメモリ上で書き換えることがある。

このデータは、取得時点の空き台数などのスナップショットです。現在の状況を表すものではありません。
