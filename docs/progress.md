# Progress

新しいセッションを始めたら、最初にこのファイルを読む。フェーズの完了時とセッションを切り替える前に更新する。
会話履歴にしか残っていない重要な情報は、ここか `docs/plan.md` / `docs/engineering-notes.md` に書き移す。
フェーズ番号の定義は `docs/plan.md` §5 を参照。

最終更新：2026-11-25（セッション 6：PHASE 5 のローカル結合確認の残り項目と、PHASE 6 の計画。コミット前）

## 現在のフェーズ
**PHASE 4：フロントエンド実装** — 完了（PR #4、squash コミット `da66ea4`。直線距離モデルのベースラインとして保存）。
**PHASE 4.5：地点指定の拡張と道路に沿った経路** — 完了（PR #6、squash コミット `5a756fc`）。ユーザー受入テストで、現在の UI と機能を MVP として承認された。
**PHASE 5：ローカル結合確認** — **残りの確認項目を実施済み（セッション 6、ブランチ `feature/phase5-local-check`、未コミット）**。正常系とユーザー受入テストは PHASE 4.5 で実施済み。結果は下の「PHASE 5 の確認結果」。
**PHASE 6：AWS デプロイ** — 計画のみ（`docs/plan.md` §7）。AWS の操作・リソース作成・CLI の導入・認証情報の取得は**まだ承認されていない**

## 現在のブランチと Git の状態
- リモート：`origin` = https://github.com/EnKyria/chariroute-lab（**public**）
- `main`：`dfffd2c`（PHASE 1）→ `89848ed`（PR #1、CI）→ `011db28`（PR #2、PHASE 2 の引き継ぎ）→ PR #3（PHASE 3、経路検索 API）の squash コミット
- `main`：… → PR #4（PHASE 4）の squash コミット `da66ea4`。`feature/frontend` はリモートとローカルの両方から削除済み（中身の一致を確認済み）
- `main`：… → PR #5（`feature/road-routing`。PHASE 4 の残作業と PHASE 4.5 の仕様）の squash コミット `32bd870`。`feature/road-routing` はマージ済みで、リモートとローカルの両方にない（2026-11-25 に `gh pr view 5` と `git ls-remote` で確認）
- `main`：… → PR #6（`feature/phase45-implementation`、PHASE 4.5）の squash コミット `5a756fc`。作業ブランチはマージ後に削除済み
- 作業ブランチ：`feature/phase5-local-check`（`5a756fc` から作成。セッション 6）。**未コミット**。コミット・push・PR はユーザーの承認待ち
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

### 2026-11-25（セッション 4）
- PHASE 4 の技術スタック：React / TypeScript / Vite / Leaflet・React Leaflet / OpenStreetMap / Vitest / React Testing Library / ESLint。必要最小限の npm 依存の追加は承認済み
- **Node.js を 22 系の最新（22.23.5）に更新**（22.11.0 では Vite 8 などが動かないため。古い系統に固定する案は不採用）。更新は Claude が winget で実行した
- `package-lock.json` を Git 管理し、CI では `npm ci` を使う
- 本番は CloudFront 経由の同一オリジン、ローカルは Vite の proxy
- MVP 完成を優先し、ハーネスの追加改善はしない。PHASE 4 の完了時点で停止し、AWS の操作はまだ行わない
- ユーザーがブラウザで画面を確認した。受入テストで追加要件が出た → PHASE 4 はコミット・PR・マージしてベースラインとして保存し（PR #4 は承認済みでマージ済み）、**PHASE 4.5** として計画する
- PHASE 4.5 の外部 API は openrouteservice を第一候補にする（→ 下記で取りやめ）
- 明日の技術面接に向けて、過剰な設計は避ける
- **PHASE 4.5 の方針を変更した**：openrouteservice は採用しない（新規のアカウント登録、API キーの発行、課金リスクを避けるため）。Muse で作った同様のアプリにならい、キーが不要な **FOSSGIS OSRM**（routed-bike / routed-foot。Table で候補を評価し、Route で経路を描く）と **Nominatim**（地点検索）を使う
- 外部サービスの利用の制約：
  - 個人利用・学習用の、低頻度の利用に限る
  - サービスごとに 1 秒 1 リクエストを守る。複数の Lambda が同時に動いても超えない設計にする
  - 大量の検索や並列リクエストはしない
  - アプリを識別できる User-Agent を付ける。クレジットと地図修正リンクを表示する
  - Nominatim のオートコンプリートはしない。**地点検索は、開発者が規約を確認して承認した後に実装する**
  - Nominatim に個人情報を送らない
  - URL は設定で変えられるようにする
  - 障害時にダミー経路を返さない
  - 座標が外部に送信され、保存されうることを利用者に明示する
- 一般公開は前提にしない。AWS にデプロイするときにアクセス制限を検討する
- PHASE 4 の残作業：**開発用の uvicorn の追加を承認**（`requirements-dev.txt`）。README に起動手順を書く。uvicorn と Vite の連携を確認する。Node.js の更新の理由と承認の状況を記録する
- 今回のセッションは、計画の修正と引き継ぎの準備までにする。実装は新しいセッションで始める
- **PHASE 4.5 の最終決定**（これまでの指示と矛盾する場合は、こちらを優先する。詳細は plan §6）：
  - 目的：効率的な貸出・返却ポートの組み合わせを探す。Google マップとの差別化のため、シェアサイクル固有の課題に集中する
  - 技術：GBFS、FOSSGIS OSRM、Nominatim、Geolocation、Leaflet + OSM、FastAPI、React。キー・有料契約・クレジットカードが不要な構成を維持する。openrouteservice は不採用
  - 地点の指定：GPS、地点検索（駅名・公開施設名）、プリセット、地図のタップ。出発地と目的地を自由に設定でき、入れ替えられる
  - **廃止**：徒歩のみの経路、徒歩との比較、おすすめの判定、時間の短縮効果
  - アルゴリズム：直線距離で各 10 件 + 直線距離モデルの最適な組（重複は除く。最大 11 件ずつ）。Table を 2 回、Route を 3 回で、1 回の検索あたり 5 リクエスト
  - 所要時間：道路距離 ÷ 独自の速度（徒歩 4.8・自転車 15 km/h）+ 手続き時間。第一案で、実環境で道路距離が取れることを確かめてから確定する
  - 障害時：**B 案（503）**。フォールバックしない
  - **利用規約は開発者本人が確認し、OSRM と Nominatim の採用を承認した**（個人利用・非商用・低頻度）。条件と対応は engineering-notes §9.5
  - **未解決**：FOSSGIS の規約にある「連絡先メールアドレス」の要件。個人のメインのアドレスを勝手に公開しない。対応方法が決まるまで、実 API を使わない
  - AWS の操作は承認しない（PHASE 6 で検討する）。レート制限を保証できない場合は、本番での実 API の利用を始めない

### 2026-11-25（セッション 5）
- PHASE 4.5 の実装を開始する。仕様の再検討や大規模な追加調査はしない。重大な問題は修正し、軽微な改善は MVP の後に回す
- **公開用の連絡先 `chariroute.dev@gmail.com` を作成し、公開を承認した**。フッターに mailto で表示する（FOSSGIS の連絡先の要件への対応。engineering-notes §9.5）
- 他の規約への対応を確認したうえで、**FOSSGIS の実 API を使った最小限のスモークテストを承認した**（1 秒 1 回以下・直列を厳守）
- ユーザーは外出中。実装・テスト・レビュー・品質チェックまで自律的に進める。軽微な設計判断は任せ、理由を engineering-notes に記録する。承認が必要な作業（AWS、依存の追加、コミット、push、PR、マージ）は保留する。ブラウザでの確認は帰宅後の確認事項にする
- Nominatim の実 API について、**1〜2 回のスモークテストを承認した**（検索対象は駅名・公開施設名）。実行済み（2 回。engineering-notes §9.7）
- **ユーザー受入テストを実施し、現在の UI と機能を MVP として承認した**。追加の機能開発とデザインの改善は不要
- コミット・push・PR の作成を承認した。CI が成功し、重大な問題がなく、最終コミットが変わっていないことを条件に、squash マージと作業ブランチの削除まで承認した。PHASE 4.5 の完了報告の後は停止する。AWS の操作はまだ承認していない

### 2026-11-25（セッション 6）
- PHASE 5 の残りの確認（スマートフォン幅・現在地の失敗・エリア外・締め切りの 503・通信エラー後の再検索・ポートなし・リミッターとプライバシー）を実施。実 API への追加リクエストはしない
- ユーザーの依頼で、地図の返却ポートの視認性を改善した（軽微な UI 改善。承認済み）
- PHASE 5 の確認結果と PHASE 6 の計画を確認した。コミット・push・PR を承認。CI の成功・重大な問題なし・最終コミットが変わっていないことを条件に、squash マージと作業ブランチの削除まで承認
- **PHASE 6 の計画への補足**（plan §7 に反映）：
  - CloudFront の共有シークレット（オリジンへのアクセス制限）と、ユーザー本人の認証は別の仕組みとして扱う。個人利用向けで固定費を抑えた認証方式を検討する（§7.6）
  - DynamoDB の分散リミッターは、通信中の排他制御・時刻のずれ・異常終了時の挙動も考慮する（§7.3）
  - `manylinux2014` が Python 3.12 で使えないという意味ではないので、依存ライブラリとの実際の互換性を確かめる（§7.4）
  - **今夜は、実 API を無効にした状態での AWS デプロイと疎通確認を優先する**（§7.1）
  - テスト用のデータを使うなら、明確なテストモードにする。通常の検索結果としてダミーの経路を返さない（§7.1）
- PHASE 6 の、AWS に接続しないコードの準備（plan §7.8 の手順 1）は**承認済み。ただし新しいセッションで実施する**
- **AWS の操作はまだ承認していない**

### ユーザー受入テストの結果（2026-11-25、ユーザーがブラウザで実施）
- **確認できた（ユーザーの報告）**：現在地の取得、地点検索、道路に沿った経路の描画が正常に動作する
- **受入テストで未確認だった項目**（スマートフォン幅、現在地の失敗、エリア外、締め切りの 503、外部サービスの障害）→ **PHASE 5（セッション 6）で確認した**。結果と、実機でしか確かめられない残りの項目は下の「PHASE 5 の確認結果」
- **既知の課題（改善は MVP の後）**：
  - 「なんば駅」などの検索で、駅ではない地物（同じ名前の道路など）が候補に並ぶ（engineering-notes §9.7）
  - 1 回の検索に 15〜20 秒ほどかかる（自転車の Table が約 9.7 秒）
  - 本番でのレート制限の保証は PHASE 6 の前提条件。**予約済み同時実行数 1 だけでは保証とみなさない**（実行環境の入れ替え・異常終了・ローカルとの同時利用を考慮する。plan §7）

## PHASE 5 の確認結果（2026-11-25、セッション 6）
**方法**：実 API に接続しないで確認した。
- スタブ API（標準ライブラリの使い捨てサーバー。リポジトリには入れていない）を `127.0.0.1:8000` で起動し、Vite の dev server（proxy）から呼んだ。シナリオ（成功・経路なし・各種 503・504・返却ポートと目的地の重なり）を切り替えた。
- ブラウザは、ヘッドレスの Chrome（専用の一時プロファイル）を DevTools Protocol で操作した。Chrome 拡張（Claude in Chrome）には接続できなかった。スマートフォンの幅・タッチ・位置情報はエミュレーションで再現した。
- OSM のタイル・FOSSGIS・Nominatim への通信はブロックした（地図の背景は灰色だが、マーカーと線は表示される）。**実 API への追加リクエストは 0 回。**

| 項目 | 結果 | 根拠 |
|---|---|---|
| 幅 360 / 390px の表示 | 横スクロールなし（`scrollWidth` = 画面幅）。ボタン・入力欄の重なりなし、高さはすべて 40px 以上（主なボタンは 44〜48px）、ボタンの文字の切れなし。地点検索を開いた状態と、結果の表示後も同じ | ヘッドレス Chrome で計測とスクリーンショット |
| 地図の操作とページのスクロール | 地図の上で指をドラッグすると、地図だけが動き、ページはスクロールしない（`touch-action: none`）。地図の外ではページをスクロールできる（左右に約 32px の余白）。地図はホイールでズームしない設定 | タッチのエミュレーション |
| 現在地の取得の失敗 | 拒否 →「許可されていません」、取得不可 →「取得できませんでした」、大阪の外 →「対象エリアの外です」。地点は変わらない。タイムアウト・非対応・非 HTTPS は自動テスト（FE-2）で確認済み | 位置情報のエミュレーション + vitest |
| 大阪エリアの外の地点 | 地図で外をタップ →「大阪市の周辺の地点を指定してください」、地点は変わらない。中をタップすると設定される。API は 400（`outside_area`、pytest `test_ap4_*`） | 同上 + pytest |
| OSRM の締め切り超過（503） | 読み込み中は「最大 30 秒ほど」の表示、検索ボタンと地点の入力は無効。503（`route_unavailable`）で「道路の経路を取得できません」、結果は出さない。サーバー側の締め切り（25 秒）で 503 になることは pytest `test_ap10_search_deadline_is_503` | スタブ（3 秒待って 503）+ pytest |
| そのほかの 503 / 504 | GBFS →「ポート情報を取得できません」、混雑 →「混雑しています」、504 →「時間内に取得できませんでした」。いずれも結果を出さない | スタブ |
| 通信エラーと再検索 | 「通信エラー」の後もボタンは有効で、入力は保持される。もう一度押すと結果に置き換わる。自動リトライはしない（押した回数だけ送る）。35 秒で打ち切ったときの表示も確認 | ブラウザ + **vitest を 2 件追加** |
| API が停止しているとき | Vite の proxy が 502 を返し、「サーバーでエラーが発生しました（HTTP 502）」。結果は出さない。復旧後は再検索できる | curl・画面 |
| 利用できるポートがないとき | 「利用できるシェアサイクルの経路が見つかりませんでした」。ポート・内訳・経路の線は出さない（API は 200 + `bike_share: null`、pytest `test_ap11_*`、`test_rr13_*`） | スタブ + pytest |
| レートリミッター | 1.1 秒の間隔、最初の送信前の待機、直列（スレッド間）、sleep が早く戻ったときの待ち直し、例外後の間隔、リトライなし、締め切りで送らない、OSRM の徒歩・自転車で共有、Nominatim は独立 | pytest（`test_outbound.py`・`test_osrm.py`・`test_places.py`） |
| プライバシー | ログに座標・検索語を出さない（pytest `test_ap12_*`・`test_pl5_*`、ログ出力の全箇所を目視でも確認）。422 の本文に入力値を返さない。フロントは `console`・localStorage・sessionStorage を使わない（ブラウザでも両ストレージが 0 件） | pytest・vitest・grep・ブラウザ |

**観察したこと（不具合ではない）**：
- 現在地は `maximumAge: 30 秒` なので、30 秒以内にもう一度押すと、ブラウザがキャッシュした位置が返る（エミュレーションで位置を変えても反映されなかった）。歩く速さなら 30 秒の誤差は小さいので、変えない。
- 凡例は 360px で 2 行になる（「目的地」が 2 行目に回る）。読みやすさに問題はない。

**ユーザーが実機で確かめる必要がある項目**（エミュレーションでは保証できない）：
1. iOS Safari / Android Chrome で、地図の上の 1 本指のドラッグで地図が動き、地図の外でページをスクロールできること。ピンチで地図がズームすること。
2. 実機の位置情報の許可ダイアログ（拒否・許可）と、屋内などで時間がかかったときのタイムアウト（10 秒）の表示。HTTPS でない URL（LAN の IP など）で開いたときの案内。
3. 実際の OSM タイルを表示したときの、返却ポート（オレンジ）と目的地（赤）の見分けやすさ。
4. 実際の FOSSGIS が遅いときの、25 秒の締め切りによる 503（再現のために実 API へ繰り返しリクエストすることはしない）。

**軽微な UI 改善（ユーザーの依頼、セッション 6）**：地図で返却ポートと目的地の色が近く、見分けにくかった。
- 返却ポートを明るいオレンジ（`#fb923c`）にし、濃い茶色の太い枠線（`#7c2d12`、3px）を付けた。目的地は濃い赤（`#b91c1c`）のまま。
- 出発地・目的地を大きめ（半径 11）にして先に描き、ポート（半径 8）を上に重ねる。重なっても「赤い輪の中のオレンジの点」として両方が見える（スタブで確認）。
- 凡例の点も同じ色と枠線にした。結果欄の「返却」タグも同じオレンジにした（白い文字だとコントラストが足りないので、文字を濃い茶色にした）。
- 配色・線の色・描く順を `mapPoints.ts` にまとめ、テストを 3 件追加した。機能と API は変えていない。

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

### PHASE 4（2026-11-25 完了）
- [x] Node.js とライブラリの互換性の確認 → Node.js 22.23.5 に更新、依存はバージョン固定（`frontend/package.json`）
- [x] OpenAPI スキーマを出力して `src/api/types.ts` を作成（backend のモデルと一致することを reviewer も確認）
- [x] API クライアント（エラーの種類の変換、応答の検証）、画面（プリセット選択・入れ替え・検索・比較・おすすめ・内訳・ポートと台数・地図・取得時刻と出典・注意書き）
- [x] OSM タイルの利用条件の確認（`docs/engineering-notes.md` §8）
- [x] UI テスト 22 件（fetch をスタブ化、外部ネットワークに接続しない）
- [x] `scripts/check.py` に frontend の build を追加、CI に setup-node（`.nvmrc`）と `npm ci` を追加
- [x] ローカル接続の確認：Vite dev server（proxy）→ 確認用ブリッジ（http.server → `main.handler`）→ 実 GBFS で、プリセットの取得、梅田→難波の検索（200、`bike_share` あり）、同じ地点（400）を確認。dev server が全モジュールを配信することも確認。ブラウザでの目視確認は Claude からはできなかった（Chrome 拡張に接続できなかった）が、**ユーザーがブラウザで画面を確認した**
- [x] reviewer：must 0 件。should 4 件のうち 3 件を修正（応答の検証の強化、検索中の入力の無効化、プリセット 0 件のエラー）、1 件（地図の依存の追加理由）は engineering-notes に記録済み。nit の「差分の丸め」も修正

## 未完了タスク（以降のフェーズ）
- [x] PHASE 4 の残作業：uvicorn 0.54.0 を `requirements-dev.txt` に追加し、venv にインストールした。`README.md` に起動手順を書いた。uvicorn + Vite の proxy で API の連携を確認した（下記）。Node.js の更新の理由と承認を engineering-notes §2 に記録した
- [x] PHASE 4.5 の調査：
  - researcher（1 回目）：ORS → 不採用（engineering-notes §9.1）
  - researcher（2 回目）：FOSSGIS OSRM・Nominatim・OSRM の API 仕様・AWS の同時実行数（§9.2〜9.4）
- [x] PHASE 4.5 の仕様の確定（`docs/plan.md` §6、CLAUDE.md の要件、engineering-notes §9.5・§9.6）
- [x] **PHASE 4.5 の実装**（セッション 5。PR #6 でマージ済み）：
  - evaluator：テストケース（バックエンド約 60 件・フロント 17 件）と、曖昧な点 8 件 → 決め方を engineering-notes §9.7 に記録
  - バックエンド：`app/outbound.py`（リミッター・ヘッダー・URL）、`app/osrm.py`、`app/road_routing.py`、`app/places.py`（Nominatim）、API の変更（Location、legs、`{detail, code}`、422 は入力値を返さない）、徒歩のみ・おすすめの削除
  - フロントエンド：地点の指定（プリセット・現在地・地点検索・地図のタップ、入れ替え）、道路に沿った経路の描画、3 区間の距離と推定時間、503 の種類の区別、外部送信の事前の明示、帰属表示、フッターの連絡先
  - 実 API のスモークテスト（2 回・合計 7 リクエスト）：Table で道路距離を取得できることを確認 → plan §6.5 を確定。自転車の Table が約 9.7 秒かかったため、タイムアウトを変更（Table 15 秒・検索全体 25 秒）
  - reviewer：must 0 件。should 4 件と nit 2 件を修正、残りは延期または PHASE 6 の前提条件として記録
  - ローカルでの結合確認（uvicorn + Vite の proxy。OSRM・Nominatim は到達できない URL にして、FOSSGIS には接続していない）：プリセット 200、同じ地点 400、エリア外 400、旧形式 422、OSRM の失敗 503（`route_unavailable`）、地点検索の失敗 503、GET の地点検索 405。サーバーのログに座標・検索語が出ないこと
- [x] **PHASE 4.5 の完了**：ユーザー受入テストで MVP として承認 → コミット・push・PR・CI・squash マージ・ブランチの削除
- [x] **PHASE 5**：ローカル結合確認（残りの項目。セッション 6、下の「PHASE 5 の確認結果」）
- [ ] **PHASE 6**：AWS デプロイ（実施計画は `docs/plan.md` §7。未承認）
- [ ] **PHASE 7**：総合評価・技術知見の整理

## 重要な設計判断（詳細は `docs/engineering-notes.md` §2）
- AWS 構成：API Gateway HTTP API → Lambda（プロキシ統合、Mangum）、フロントは S3 + CloudFront
- 経路は、直線距離で候補（貸出・返却とも最大 11 件）を絞り込み、OSRM の道路距離 ÷ 独自の速度 + 手続き時間で評価する（PHASE 4.5。plan §6）。直線距離モデル（分枝限定法）は候補の絞り込みと比較評価に使う
- 外部サービス（OSRM・Nominatim）の失敗は 503。フォールバックもダミーの経路も出さない
- GBFS の取得に失敗したら 503 を返し、ダミー値は返さない
- 品質ゲートは `scripts/check.py` の 1 か所に集約（人・Stop Hook・CI で共通）。CI には環境構築だけを書く
- サブエージェントは読み取り専用とし、ファイルの変更はメインエージェントだけが行う
- コミットには noreply アドレスを使う（ローカル設定にのみ設定）

## 未解決の問題
- **技術的負債：大阪エリアの判定**は、実データにもとづく仮定（接頭辞の意味と Z 系の扱いは公式資料なし）。新しいポートが市外に追加されると誤判定しうる。改善方法（行政区域のポリゴンによる判定など）は `docs/engineering-notes.md` §7
- 分枝限定法の最悪の計算量は総当たりと同じ（下限が効かない配置では約 0.8 秒）。実データでは起きていない
- ODPT のアクセス頻度の上限と、クレジット表記の正式な文言は未確認
- GBFS の取得タイムアウトはソケット操作ごとの値で、合計の締め切りではない → 検索全体の締め切り（25 秒）の中に収まる。PHASE 6 の Lambda のタイムアウトは 28 秒（plan §7.2）
- API Gateway のステージは `$default` を使う（別名ならパスがずれる） → PHASE 6
- **Git Credential Manager の資格情報の保存エラー**：未解決。ユーザーの指示で、今回は記録だけにして修正しない
- **MVP 後の課題（reviewer の軽微な指摘）**：(1) `RouteParams` を変えた場合（自転車 < 徒歩、迂回係数の変更）のランダムテストがない（テスト側の総当たりのパラメータ化が必要）、(2) 同値のタイブレークを意図的に作るテストは B8 の 1 件だけ、(3) `test_pruning_reduces_evaluated_pairs` の閾値は経験値なので根拠のコメントを足す、(4) テストのオラクルが大阪エリアの条件（除外リストの ID）を複製しているので、出典をコメントに書く
- reviewer（1 回目）の nit で未対応のもの：キャッシュの経過時間に `time.time` を使っている（時計の巻き戻りに弱い）、status のない info を数えていない、`last_updated` が float だと全体が 503 になる（実フィードは int）
- 既存の AWS 環境（Lambda の有無・ランタイム）が未確認 → PHASE 6
- Stop Hook：セッション 2 で、状態ファイル `.claude/.cache/stop-hook-state.json` が `stop_hook.py` の修正後に更新されていたため、**動作していると推定**。`/hooks` での目視確認はまだ。サブエージェント（reviewer）は読み込まれ、動作を確認済み
- Mangum 0.22 で DeprecationWarning が出る（動作には影響なし）
- **PHASE 4 で見つかったこと**：
  - **ユーザー受入テストで発生した追加要件**（→ PHASE 4.5）：直線の経路が川などを横断して実用的でない、現在地から検索したい、プリセット以外の地点を検索したい
- **PHASE 4.5 の未確認事項・残存課題**：
  - ~~FOSSGIS の利用規約の本文~~ → 開発者本人が確認した（2026-11-25）
  - ~~FOSSGIS の連絡先メールアドレスの要件~~ → 公開用のアドレスをフッターに表示して対応した（2026-11-25）
  - ~~Table で道路距離を取得できるか~~ → 実 API で確認した（engineering-notes §9.7）
  - **自転車の Table が約 9.7 秒かかる**（1 回の計測）。1 回の検索は 15〜20 秒。遅いときは締め切り（25 秒）を超えて 503 になりうる。改善するなら候補の数を減らす
  - **本番でのレート制限の保証**：プロセス内のリミッターは、プロセスをまたぐ制御ができない。予約済み同時実行数 1 だけでは保証とみなさない。条件が整うまで**本番では実 API 連携を無効にする**（plan §7.3）
  - Nominatim の実 API：ユーザーの承認を受けてスモークテスト（2 回）を実行した。形式は想定どおり、応答は約 1.2〜1.3 秒。「なんば駅」で駅ではない地物（「なんば」という名前の道路など）が返る精度の課題がある（engineering-notes §9.7。改善は MVP の後）
  - 延期した reviewer の指摘：取得中にコンポーネントが外れたときの setState、Nominatim の待ち行列の締め切り
  - 公開 OSRM の Table の最大サイズ（使っているのは最大 24 点なので、問題になっていない）
  - Nominatim の日本語の精度
  - 実行環境が入れ替わった直後の、送信間隔のわずかなリスク（plan §6.4）
  - 小文字のドライブ文字（`d:\`）から `npm test` を直接実行すると Vitest が失敗する（check.py 経由では起きない。engineering-notes §5）
  - OSM の公式タイルは SLA がなく、予告なく遮断されうる。利用が増える場合はタイルの提供元を切り替える。CloudFront で Referrer-Policy を設定するときは Referer を消さない（PHASE 6）
  - 大阪エリア判定の仮定があるため、画面に「公式アプリで確認」の注意書きを出している
  - reviewer の nit（未対応）：502 / 504 も「HTTP 50x」のサーバーエラー扱い、`VITE_API_BASE_URL` の末尾スラッシュを正規化しない

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
- 2026-11-25（セッション 6、`feature/phase5-local-check`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：OK。pytest：**545 件成功**（警告 1 件：Mangum の DeprecationWarning）
  - npm lint / typecheck：OK。vitest：**45 件成功**（+5：通信エラー後の再検索、35 秒の打ち切り、地図の配色と描く順 3 件）。vite build：OK
  - 既存のテストの削除・skip・期待値の変更はない
- 2026-11-25（セッション 5、`feature/phase45-implementation`、reviewer の指摘の修正後）：`python scripts/check.py` → **ALL PASSED**
  - ruff：OK。pytest：**545 件成功**（警告 1 件：Mangum の DeprecationWarning）
  - npm lint / typecheck：OK。vitest：**40 件成功**。vite build：OK（JS 約 397KB、gzip 約 122KB）
  - 既存のテストの削除・変更は、廃止した機能（徒歩のみ・おすすめ・比較）と、API の形式の変更によるものだけ。理由はテストのコメントに書いた
- 2026-11-25（セッション 4 の終了時、`feature/road-routing`、仕様の確定後）：`python scripts/check.py` → **ALL PASSED**（ruff OK、pytest 427 件、vitest 22 件、lint / typecheck / build OK）
- **uvicorn + Vite の連携の確認**（2026-11-25、手動）：
  - `uvicorn main:app --port 8000` と `npm run dev` を起動し、Vite の proxy 経由で確認した。
  - `GET /api/presets` が 200、`POST /api/routes/search`（大阪城公園 → 天王寺駅）が 200（`bike_share` あり、合計 35.7 分、徒歩 75.7 分）。
  - 不明な地点で 400、形式エラーで 422、画面の配信は 200。
  - `GBFS_BASE_URL` を到達できない URL にしたインスタンスで、503 が返ることも確認した。
- 2026-11-25（セッション 4、`feature/frontend`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed / pytest：427 件成功（警告 1 件：Mangum の DeprecationWarning）
  - npm lint / typecheck：OK、vitest：22 件成功、vite build：OK（JS 約 386KB、gzip 約 118KB）
- 2026-11-25（セッション 3、`feature/route-search`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：427 件成功（警告 1 件：Mangum の DeprecationWarning）
  - 実 GBFS での疎通確認（手動）：取得と検証 0.68 秒、大阪エリアのポート 745 件、経路計算（分枝限定法）中央値 3.05ms・最大 4.48ms、素朴な総当たり 中央値 778ms、両者の結果の差 0 件（56 組）
- 2026-11-25（セッション 2、`feature/ci`）：`python scripts/check.py` → **ALL PASSED**
  - ruff：All checks passed
  - pytest：9 件成功（警告 1 件：Mangum の DeprecationWarning）
  - CI と同じ `CHECK_PYTHON` の経路でも成功。Python が見つからない場合は exit 2 になることも確認
- GitHub Actions：PR #1 でジョブ `check` が pass（ruff OK、pytest 9 件、`check.py: ALL PASSED`）

## 次にやること
1. **新しいセッションで、PHASE 6 の AWS に接続しないコードの準備**（承認済み。plan §7.8 の手順 1）：実 API の有効・無効のフラグ（既定は無効）、共有シークレットの検証、`scripts/build_lambda.py`（wheel のタグと `.so` の一覧の出力）。
2. **実機での確認**（ユーザー）：上の「PHASE 5 の確認結果」の「ユーザーが実機で確かめる必要がある項目」。
3. **PHASE 6：AWS デプロイ**（**AWS の操作はまだ承認されていない**）：実施計画は `docs/plan.md` §7。今夜は、実 API を無効にしたデプロイと疎通確認を優先する。ユーザー認証（推奨案：CloudFront Functions の Basic 認証）と分散リミッターは、その後にする。
   - **本番では実 API（OSRM・Nominatim）を無効にしてデプロイする**。有効にする条件（分散リミッター、同時実行数 1 の設定の確認、緊急停止の訓練、ローカルとの同時利用の防止）は plan §7.3。予約済み同時実行数 1 だけでは保証とみなさない。
   - wheel のタグは、AWS の案内どおり `manylinux_2_28_x86_64` を指定し、実際に入った wheel で互換性を確かめる。Lambda のタイムアウトは 28 秒（HTTP API の統合タイムアウトは 30 秒で引き上げ不可）。
   - AWS CLI の導入と認証設定、棚卸し（`get-account-settings` で同時実行数の上限を確認）以降は、操作ごとにユーザーの承認を得る。
4. **PHASE 7**：総合評価・技術知見の整理。
