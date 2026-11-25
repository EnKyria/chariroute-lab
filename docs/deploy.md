# AWS デプロイ手順（PHASE 6）

設計と判断の根拠は `docs/plan.md` §7、出典は `docs/engineering-notes.md` §11・§12。手順は aws-expert が公式資料と照合した（2026-11-25）。
**⚠ の付いた手順は AWS の変更操作で、操作ごとにユーザーの承認が必要。** 読み取り専用の手順（🔍）も、AWS への接続そのものを承認してから行う。

- 「事実」は公式資料で確認したこと、「未確認」は確認できていないこと、「推論」は判断を表す。
- 秘密の値（共有シークレット・Basic 認証のパスワード）は**ユーザーが作り、ユーザーが入力する**。Claude は値を見ない。チャット・リポジトリ・ログ・シェルの履歴に残さない。シークレットを含む設定（Lambda の環境変数、ディストリビューションの設定）は、出力を `--query` で絞り、そのまま表示しない。
- コマンドは Git Bash の前提。`<...>` は置き換える値。ETag などを次のコマンドに渡すときは `--output text` を付ける（json のままだと引用符が付く）。

## 0. 構成と名前

```
Browser ─HTTPS─▶ CloudFront（Basic 認証：CloudFront Functions + KeyValueStore）
                   ├ *        ─OAC─▶ S3（frontend/dist。非公開）
                   └ /api/*   ─X-Origin-Verify─▶ API Gateway HTTP API（$default）─▶ Lambda（FastAPI）─▶ ODPT GBFS
                                                                                     （OSRM・Nominatim は無効）
```

| 項目 | 値 |
|---|---|
| リージョン | `ap-northeast-1`（CloudFront・CloudFront Functions・KeyValueStore・Budgets はグローバル） |
| Lambda 関数 | `chariroute-api`（python3.12 = Amazon Linux 2023、x86_64、256 MB、タイムアウト 28 秒） |
| 実行ロール | `chariroute-api-role`（1 つのロググループへの書き込みだけ） |
| ロググループ | `/aws/lambda/chariroute-api`（保持 14 日） |
| HTTP API | `chariroute-http-api`（ステージ `$default`、ルート `$default`、payload 2.0） |
| S3 バケット | `chariroute-web-<ACCOUNT_ID>`（非公開、Block Public Access すべて有効） |
| CloudFront Function | `chariroute-basic-auth`（cloudfront-js-2.0、viewer request。KeyValueStore を使う関数は 2.0 が必須：事実） |
| KeyValueStore | `chariroute-auth`（キー `basic_auth_sha256`） |
| 予算 | `chariroute-monthly`（月 $5、メール通知だけ） |

**Lambda の環境変数**（本番）：

| 変数 | 値 | 意味 |
|---|---|---|
| `EXTERNAL_APIS_ENABLED` | `false` | FOSSGIS OSRM・Nominatim への送信。**`true` と厳密に一致したときだけ有効**。未設定・綴りの誤りも無効。plan §7.3 の条件（分散リミッター、予約済み同時実行数 1 の確認、緊急停止の訓練、Referer）が全て整い、ユーザーが承認するまで `false` のまま |
| `ORIGIN_VERIFY_SECRET` | （ユーザーが生成。32 文字以上、ASCII） | CloudFront が付ける `X-Origin-Verify` と照合する。**Lambda 上で未設定・32 文字未満なら全てのリクエストを 403**（安全側） |
| `OUTBOUND_REFERER` | 未設定 | 実 API を有効にするときに設定する（plan §7.3 (e)） |

- `update-function-configuration --environment` は `Variables` の**全体を置き換える**（事実）。一部だけ変えるときも、全ての変数を指定する。
- Lambda は環境変数を保存時に暗号化する（事実）。ただし `lambda:GetFunctionConfiguration` の権限がある人には見える。CloudFront のカスタムヘッダーも `get-distribution-config` で見える。個人利用で権限が本人だけなので許容する（推論。機密が増えたら Secrets Manager を検討）。
- テストモード（ダミーの経路）は実装していない。設定で有効にする手段もない。

## 1. 事前準備（ユーザーが行う。Claude は値を見ない）

1. AWS CLI v2 を導入する。ルートユーザーのアクセスキーは使わない。**IAM Identity Center（`aws configure sso`）+ MFA** を推奨する。権限は §8。
2. 秘密の値を、リポジトリの**外**のファイルに作る。
   ```bash
   mkdir -p ~/.chariroute && chmod 700 ~/.chariroute
   python -c "import secrets; print(secrets.token_urlsafe(48))" > ~/.chariroute/origin-secret
   # curl 用のヘッダーファイル（コマンドラインや履歴に値を出さないため）
   printf 'X-Origin-Verify: %s\n' "$(cat ~/.chariroute/origin-secret)" > ~/.chariroute/origin-header
   chmod 600 ~/.chariroute/*
   ```
3. Basic 認証の資格情報を決め、SHA-256 だけを作る。**パスワードは 20 文字以上のランダムな値**にし、パスワードマネージャーに保存する（401 に回数制限はなく、総当たりへの耐性はパスワードの強さだけで決まる）。
   ```bash
   read -r -p 'user: ' U; read -r -s -p 'password: ' P; echo
   printf 'Basic %s' "$(printf '%s:%s' "$U" "$P" | base64 -w0)" | sha256sum | cut -d' ' -f1 > ~/.chariroute/basic-auth-sha256
   unset U P
   ```
   - KeyValueStore には、この 16 進 64 文字だけを置く。資格情報の平文は AWS にも置かない。
4. ビルドする（AWS に接続しない）。
   ```bash
   python scripts/check.py                 # 全件成功を確認
   python scripts/build_lambda.py          # build/lambda.zip と build/lambda-report.json
   (cd frontend && npm run build)          # frontend/dist（VITE_API_BASE_URL は空のまま＝同一オリジン）
   ```
   - `build/lambda-report.json` の `problems` が空で、`native_files` が `pydantic_core` の `.so` だけであること。

## 2. 🔍 読み取り専用の棚卸し（既存のリソースを変更しない）

```bash
export AWS_REGION=ap-northeast-1
aws sts get-caller-identity                                   # アカウントと、ルートでないこと
aws lambda get-account-settings                               # AccountLimit.ConcurrentExecutions / UnreservedConcurrentExecutions
aws lambda list-functions --query 'Functions[].{n:FunctionName,r:Runtime,m:LastModified}' --output table
aws apigatewayv2 get-apis --query 'Items[].{n:Name,id:ApiId,p:ProtocolType,e:ApiEndpoint}' --output table
aws apigateway get-rest-apis --query 'items[].{n:name,id:id}' --output table     # REST API（旧手順のものがありうる）
aws s3api list-buckets --query 'Buckets[].Name'
aws cloudfront list-distributions --query 'DistributionList.Items[].{id:Id,d:DomainName,e:Enabled,c:Comment}' --output table
aws cloudfront list-functions --query 'FunctionList.Items[].Name'
aws cloudfront list-key-value-stores --query 'KeyValueStoreList.Items[].Name'
aws iam list-roles --query "Roles[?contains(RoleName,'chariroute') || contains(RoleName,'lambda')].RoleName"
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/ --query 'logGroups[].{n:logGroupName,r:retentionInDays}' --output table
aws budgets describe-budgets --account-id <ACCOUNT_ID> --query 'Budgets[].BudgetName'
```
- **既存の Lambda・API Gateway・バケットなどが見つかっても、上書き・削除・再利用はしない。** 名前・作成日・用途を一覧にしてユーザーに報告し、扱いを個別に決める（CLAUDE.md）。名前が重なるときは、§0 の名前を変える（例 `chariroute-api-v2`）。
- `UnreservedConcurrentExecutions` が 101 未満なら、予約済み同時実行数 1 は設定できない可能性が高い（「未予約分 − 100」まで。plan §7.3）。**0（緊急停止）が同じ規則で拒否されるかは未確認**なので、§6 の訓練で試す。
- アカウントが Free プランか Paid プランかを、請求のコンソールで確認する（Free プランは使えるサービスが限られる）。

## 3. ⚠ 費用の管理（最初に作る）

**AWS Budgets は通知であって、課金を止めない**（事実）。予算アクションで適用できるのは IAM ポリシー・SCP と、EC2・RDS インスタンスの停止で、Lambda・CloudFront・API Gateway を止める機能はない（事実）。止めるのは §6 の手順で、人が行う。

```bash
aws budgets create-budget --account-id <ACCOUNT_ID> \
  --budget file://budget.json --notifications-with-subscribers file://notifications.json
```
```json
// budget.json
{"BudgetName": "chariroute-monthly", "BudgetType": "COST", "TimeUnit": "MONTHLY",
 "BudgetLimit": {"Amount": "5", "Unit": "USD"}}
```
```json
// notifications.json（メールアドレスはユーザーが入力する）。実績 80%・100%、予測 100%
[{"Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 80, "ThresholdType": "PERCENTAGE"},
  "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "<EMAIL>"}]},
 {"Notification": {"NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN", "Threshold": 100, "ThresholdType": "PERCENTAGE"},
  "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "<EMAIL>"}]},
 {"Notification": {"NotificationType": "FORECASTED", "ComparisonOperator": "GREATER_THAN", "Threshold": 100, "ThresholdType": "PERCENTAGE"},
  "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "<EMAIL>"}]}]
```
- 監視と通知だけの予算は無料（事実。アクション付きは 3 つ目から 1 日 $0.10）。
- **Budgets の情報は 1 日最大 3 回、通常 8〜12 時間おきに更新される**（事実）。短時間の大量アクセスには間に合わないので、CloudWatch のメトリクス（Lambda の Invocations、CloudFront の Requests）でも気づけるようにする。
- 任意：Cost Anomaly Detection（追加料金なし：AWS の発表。検出まで最大 24 時間で、今夜の異常検知には使えない）。

## 4. ⚠ バックエンド（IAM → ログ → Lambda → HTTP API）

### 4.1 IAM の実行ロール
```bash
aws iam create-role --role-name chariroute-api-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name chariroute-api-role --policy-name logs-write-only --policy-document '{
  "Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["logs:CreateLogStream","logs:PutLogEvents"],
  "Resource":"arn:aws:logs:ap-northeast-1:<ACCOUNT_ID>:log-group:/aws/lambda/chariroute-api:*"}]}'
```
- `logs:CreateLogGroup` は付けない（ロググループは次の手順で先に作る。既存のロググループがあれば Lambda はそれを使う：事実）。マネージドポリシー `AWSLambdaBasicExecutionRole` は全てのロググループが対象なので使わない。
- ロールの作成直後は IAM の反映が遅れ、次の `create-function` が「role cannot be assumed」で失敗することがある（推論）。**10 秒ほど待ってから**進み、失敗したら同じコマンドをもう一度実行する。

### 4.2 ロググループ
```bash
aws logs create-log-group --log-group-name /aws/lambda/chariroute-api
aws logs put-retention-policy --log-group-name /aws/lambda/chariroute-api --retention-in-days 14
```

### 4.3 Lambda
```bash
# 環境変数のファイル（リポジトリの外。値は表示しない）
python - <<'EOF'
import json, pathlib
home = pathlib.Path.home() / ".chariroute"
secret = (home / "origin-secret").read_text().strip()
(home / "lambda-env.json").write_text(json.dumps({"Variables": {
    "EXTERNAL_APIS_ENABLED": "false", "ORIGIN_VERIFY_SECRET": secret}}))
EOF
chmod 600 ~/.chariroute/lambda-env.json

aws lambda create-function --function-name chariroute-api \
  --runtime python3.12 --architectures x86_64 --handler main.handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/chariroute-api-role \
  --zip-file fileb://build/lambda.zip --memory-size 256 --timeout 28 \
  --environment file://$HOME/.chariroute/lambda-env.json \
  --query '{arn:FunctionArn,sha:CodeSha256,state:State}'
# 作成直後は Pending。Active になるまで、呼び出しや設定の変更は失敗する（事実）
aws lambda wait function-active-v2 --function-name chariroute-api
```
- `CodeSha256` が `build/lambda-report.json` の `zip_code_sha256` と一致すること（アップロードした zip がビルドしたものと同じ）。
- ロググループは既定の名前（`/aws/lambda/<関数名>`）なので `--logging-config` は指定しない。
- 予約済み同時実行数：`aws lambda put-function-concurrency --function-name chariroute-api --reserved-concurrent-executions 1`。**失敗したら記録して先へ進む**（実 API が無効なので、今夜は必須ではない。実 API を有効にする前には必須：plan §7.3 (c)）。
- 以降、設定を変えるたびに `aws lambda wait function-updated-v2 --function-name chariroute-api` で更新の完了を待つ（更新中の再更新は失敗する：事実）。

### 4.4 HTTP API
```bash
# クイック作成：$default ルート・自動デプロイの $default ステージ・Lambda プロキシ統合（payload 2.0）
aws apigatewayv2 create-api --name chariroute-http-api --protocol-type HTTP \
  --target arn:aws:lambda:ap-northeast-1:<ACCOUNT_ID>:function:chariroute-api \
  --query '{id:ApiId,endpoint:ApiEndpoint}'
# CLI で作った統合には、Lambda の呼び出し権限が自動では付かない（事実。コンソールだけが付ける）
aws lambda add-permission --function-name chariroute-api --statement-id apigw-invoke \
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com \
  --source-arn 'arn:aws:execute-api:ap-northeast-1:<ACCOUNT_ID>:<API_ID>/$default/$default'
aws lambda get-policy --function-name chariroute-api --query Policy --output text   # SourceArn がこの API だけであること
```
- CORS は設定しない（CloudFront の同一オリジン）。アクセスログは今夜は使わない（使うなら plan §7.8 の項目だけ。`sourceIp`・`path` は入れない）。
- **スロットリングは §4.5 の確認の後に設定する**（先に設定すると、確認の curl が 429 になり、結果を切り分けにくい）。

### 4.5 API の確認（CloudFront を経由しない直接の呼び出し）
```bash
E=https://<API_ID>.execute-api.ap-northeast-1.amazonaws.com
curl -s -o /dev/null -w '%{http_code}\n' $E/health                                   # 403（ヘッダーなし）
curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Origin-Verify: wrong' $E/api/presets  # 403
curl -s -w '\n%{http_code}\n' -H @$HOME/.chariroute/origin-header $E/api/presets     # 200
curl -s -w '\n%{http_code}\n' -H @$HOME/.chariroute/origin-header -H 'content-type: application/json' \
  -d '{"origin":{"preset_id":"umeda"},"destination":{"preset_id":"namba"}}' $E/api/routes/search
# → 503 {"code":"route_disabled"}（その前に GBFS を取得している。GBFS が取れなければ 503 gbfs_unavailable）
```
- 200 が返れば、Lambda 上で `pydantic_core`（manylinux_2_17 の wheel）を import できている（plan §7.4 の最終確認）。
- `aws logs tail /aws/lambda/chariroute-api --since 10m` で、座標・地点名・検索語・シークレットが出ていないこと。

確認が終わったら、ルートのスロットリングを設定する（best-effort。過剰な呼び出しを抑える補助で、上限の保証ではない：事実）：
```bash
aws apigatewayv2 update-stage --api-id <API_ID> --stage-name '$default' \
  --default-route-settings ThrottlingRateLimit=1,ThrottlingBurstLimit=2
```
- 引数の形は `aws apigatewayv2 update-stage help` で確かめてから実行する（公式の例は `--route-settings` のもので、この形は API の構造からの推論）。
- 画面の表示（プリセット）と検索が続くと 429 になりうる。困ったら値を上げる（例 レート 2・バースト 5）。

## 5. ⚠ フロントエンドと CloudFront

### 5.1 S3
```bash
B=chariroute-web-<ACCOUNT_ID>
aws s3api create-bucket --bucket $B --create-bucket-configuration LocationConstraint=ap-northeast-1
aws s3api put-public-access-block --bucket $B --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
# ファイル名にハッシュが付く assets は長くキャッシュし、index.html は毎回確かめさせる
aws s3 sync frontend/dist/assets s3://$B/assets --delete --cache-control 'public,max-age=31536000,immutable'
aws s3 cp frontend/dist/index.html s3://$B/index.html --cache-control 'no-cache' --content-type 'text/html; charset=utf-8'
aws s3 ls s3://$B --recursive
```
- 新しいバケットの Object Ownership は既定で「バケット所有者の強制」で、OAC はこれを前提にする（事実）。
- ディストリビューションを作る**前に**上げておく（CloudFront は 404 を既定で 10 秒キャッシュする：事実）。
- CachingOptimized の最小 TTL は 1 秒なので、`index.html` の更新は最大で数秒遅れて見える（事実。個人利用なら許容）。

### 5.2 Basic 認証（KeyValueStore と Function）。**ディストリビューションより先に作る**
一般公開前に認証を有効にするため、ディストリビューションは最初から Basic 認証の関数を付けて作る（URL が認証なしで開いている時間を作らない）。
```bash
aws cloudfront create-key-value-store --name chariroute-auth --query 'KeyValueStore.{arn:ARN,status:Status}'
aws cloudfront describe-key-value-store --name chariroute-auth --query 'KeyValueStore.Status' --output text   # READY を待つ
# データの操作は別の API（cloudfront-keyvaluestore）。ETag も cloudfront 側のものとは別（事実）
aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn <KVS_ARN> --query ETag --output text
aws cloudfront-keyvaluestore put-key --kvs-arn <KVS_ARN> --if-match <ETAG> \
  --key basic_auth_sha256 --value "$(cat ~/.chariroute/basic-auth-sha256)" --query ETag --output text
```
- **KeyValueStore の API は SigV4A で署名する**（事実）。一時的な認証情報では、STS のグローバルエンドポイントの（v1 の）セッショントークンが使えず、認証エラーになる（事実）。上の `cloudfront-keyvaluestore describe-key-value-store` が通ることを、ここで必ず確かめる。
  - 通らなければ、STS のリージョナルエンドポイントを使う設定（`sts_regional_endpoints = regional`）を試す。
  - それでも通らなければ、CloudFront コンソールの KeyValueStores の画面でキーを登録・編集・削除する（§6 の緊急停止も同じ画面でできる）。

```bash
aws cloudfront create-function --name chariroute-basic-auth \
  --function-config '{"Comment":"Basic auth","Runtime":"cloudfront-js-2.0","KeyValueStoreAssociations":{"Quantity":1,"Items":[{"KeyValueStoreARN":"<KVS_ARN>"}]}}' \
  --function-code fileb://infra/cloudfront/basic-auth.js --query ETag --output text
```
公開の前に、DEVELOPMENT ステージで動作を確かめる（**構文がランタイムで通ることの最終確認**。関数の書き方は AWS の公式サンプル（`import cf from 'cloudfront'; import crypto from 'crypto';`、`async function handler`）に合わせた）：
```bash
ETAG=$(aws cloudfront describe-function --name chariroute-basic-auth --query ETag --output text)
# 資格情報なし → 401 を期待
cat > /tmp/cf-noauth.json <<'EOF'
{"version":"1.0","context":{"eventType":"viewer-request"},"viewer":{"ip":"203.0.113.1"},
 "request":{"method":"GET","uri":"/","querystring":{},"headers":{"host":{"value":"example.cloudfront.net"}},"cookies":{}}}
EOF
aws cloudfront test-function --name chariroute-basic-auth --if-match $ETAG --stage DEVELOPMENT \
  --event-object fileb:///tmp/cf-noauth.json --query 'TestResult.{err:FunctionErrorMessage,out:FunctionOutput}'
```
- 期待：`FunctionErrorMessage` が空で、`FunctionOutput` に `"statusCode":401` と `www-authenticate`。
- 正しい資格情報での確認は、ユーザーが自分の端末でイベントのファイルを作って行う（本番のパスワードをファイルやチャットに残さないため、確認後にファイルを消す）。期待：`FunctionOutput` にリクエスト（`uri`）が返り、`authorization` が消えている。
- DEVELOPMENT ステージで KeyValueStore を読めるかは未確認。読めないときは 503 になる（安全側）ので、その場合は公開後に §5.5 で確かめる。
- 構文エラーが出たら公開しない。原因を調べてから直す。
- 確認できたら公開する：`aws cloudfront publish-function --name chariroute-basic-auth --if-match $ETAG --query 'FunctionSummary.FunctionMetadata.FunctionARN' --output text`。ディストリビューションに関連付けられるのは公開（LIVE）した関数（推論）。

### 5.3 OAC とディストリビューション
```bash
aws cloudfront create-origin-access-control --origin-access-control-config \
  'Name=chariroute-oac,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3' --query 'OriginAccessControl.Id' --output text
```
マネージドポリシーの ID（事実。固定の値。念のため `aws cloudfront list-cache-policies --type managed` などで照合する）：

| ポリシー | ID |
|---|---|
| CachingOptimized | `658327ea-f89d-4fab-a63d-7e88639e58f6` |
| CachingDisabled | `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` |
| AllViewerExceptHostHeader（API Gateway 向け。Host 以外を転送） | `b689b0a8-53d0-40ab-baf2-68738e2966ac` |
| SecurityHeadersPolicy（`Referrer-Policy: strict-origin-when-cross-origin`・HSTS・nosniff 等） | `67f7725c-6f97-4210-82d7-5512b31e9d03` |

ディストリビューションの設定（`dist.json`。**シークレットを含むので `~/.chariroute/` に置き、リポジトリに入れない**）の要点：

| 項目 | 値 |
|---|---|
| Origins | `s3`：`<B>.s3.ap-northeast-1.amazonaws.com`、OAC の Id、`S3OriginConfig.OriginAccessIdentity` は空 / `api`：`<API_ID>.execute-api.ap-northeast-1.amazonaws.com`、`CustomOriginConfig.OriginProtocolPolicy=https-only`、TLSv1.2、**`CustomHeaders`：`X-Origin-Verify` = シークレット**（閲覧者が同名のヘッダーを送っても CloudFront が上書きする：事実） |
| DefaultCacheBehavior（`*`） | `s3`、ViewerProtocolPolicy **`https-only`**、AllowedMethods GET/HEAD、CachingOptimized、SecurityHeadersPolicy、`Compress: true`、FunctionAssociations：viewer-request → `chariroute-basic-auth`（LIVE の ARN） |
| CacheBehaviors（`/api/*`） | `api`、ViewerProtocolPolicy **`https-only`**、AllowedMethods **GET/HEAD/OPTIONS/PUT/POST/PATCH/DELETE**（POST を通すにはこの 7 つの組しかない：事実。未定義のメソッドは FastAPI が 405 を返す）、CachedMethods GET/HEAD、**CachingDisabled**、AllViewerExceptHostHeader、SecurityHeadersPolicy、同じ Function |
| その他 | DefaultRootObject `index.html`、PriceClass `PriceClass_200`（日本を含む）、HttpVersion `http2and3`、Logging なし、カスタムエラーレスポンスなし、証明書は CloudFront の既定（`*.cloudfront.net`） |

```bash
aws cloudfront create-distribution --distribution-config file://$HOME/.chariroute/dist.json --query 'Distribution.{id:Id,domain:DomainName,arn:ARN}'
```
- `https-only` の場合、http:// へのリクエストはリダイレクトされずに 403 になる（事実。資格情報を平文で送らせない）。
- **フラットレートの料金プラン（Free を含む）には加入しない**（加入すると請求サイクルの終わりまで削除できない。plan §7.7）。
- execute-api の既定のエンドポイントを無効にする設定は使わない（カスタムドメインが前提で、無効にすると CloudFront からも届かない。推論）。直接の呼び出しは共有シークレットで 403 にする。

### 5.4 S3 のバケットポリシー（このディストリビューションからだけ読める）
ポリシーにディストリビューションの ARN が要るので、作成の後に設定する。設定するまで S3 は拒否する（安全側）。
```bash
aws s3api put-bucket-policy --bucket $B --policy '{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
  "Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"s3:GetObject","Resource":"arn:aws:s3:::'$B'/*",
  "Condition":{"StringEquals":{"AWS:SourceArn":"<DISTRIBUTION_ARN>"}}}]}'
aws cloudfront wait distribution-deployed --id <DISTRIBUTION_ID>
```

### 5.5 確認
```bash
D=https://<DOMAIN>.cloudfront.net
curl -s -o /dev/null -w '%{http_code}\n' $D/                          # 401（資格情報なし）
curl -s -o /dev/null -w '%{http_code}\n' $D/api/presets               # 401
curl -s -o /dev/null -w '%{http_code}\n' http://<DOMAIN>.cloudfront.net/   # 403（https-only）
curl -s -o /dev/null -w '%{http_code}\n' https://$B.s3.ap-northeast-1.amazonaws.com/index.html   # 403（S3 は非公開）
curl -s -o /dev/null -w '%{http_code}\n' https://<API_ID>.execute-api.ap-northeast-1.amazonaws.com/api/presets   # 403
```
ブラウザで `$D` を開き（資格情報はユーザーが入力する）、次を確かめる：
1. 画面・プリセット・帰属表示・連絡先・**OSM の地図タイル**が表示される（Referer がオリジンだけになるので、タイルが表示されることを実際に確かめる）。
2. 経路検索で「道路の経路を取得できません／この環境では、道路の経路の検索（外部の経路サービスへの接続）を停止しています」が出て、経路・内訳・地図の線が出ない。
3. 地点検索で「この環境では、地点検索…を停止しています」が出て、候補が出ない。
4. 開発者ツールで、`/api/*` の応答に `Cache-Control: no-store` があり、キャッシュされていない（`X-Cache` が `Hit` でない）こと。
5. 存在しないパス（例 `/nothing`）は 403 か 404 になる（OAC で `s3:ListBucket` を許可していないので、S3 は 403 を返すと推論）。画面への影響はない。
6. `aws logs tail /aws/lambda/chariroute-api --since 10m` に、座標・地点名・検索語・シークレット・Authorization が出ていないこと。

## 6. 緊急停止（訓練を 1 回行い、反映の時間と復旧を記録する）

速い順。どれも ⚠。

| 手段 | 止まる範囲 | 反映 | 復旧 |
|---|---|---|---|
| **KeyValueStore のキーを消す** | 画面と API の全て（関数が 503 を返し、オリジンに届かない） | 発表時のブログに「数秒以内」（現行の資料に保証値はない）。**訓練で実測する** | `put-key` で戻す |
| Lambda の予約済み同時実行数を 0 | API（Lambda を実行しない。GBFS の取得も止まる。公式に「意図的に止めるには 0」とある：事実） | 即時性は公式に記載なし | `put-function-concurrency` で 1、または `delete-function-concurrency` |
| Lambda の `ORIGIN_VERIFY_SECRET` を別の値にする（環境変数は全て指定し直す） | API（全て 403） | 新しい実行環境から | 元に戻す |
| CloudFront のディストリビューションを無効にする | 画面と API の入口 | 数分（目標 5 分以内：AWS のブログ） | `Enabled=true` に戻す |
| HTTP API の `$default` ステージを削除する | API（`Not Found` になる：事実） | 即時（推論） | 作り直しが必要。最後の手段 |

```bash
# KeyValueStore のキーを消す（コンソールの KeyValueStores の画面でもできる）
ETAG=$(aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn <KVS_ARN> --query ETag --output text)
aws cloudfront-keyvaluestore delete-key --kvs-arn <KVS_ARN> --if-match $ETAG --key basic_auth_sha256
# 復旧
ETAG=$(aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn <KVS_ARN> --query ETag --output text)
aws cloudfront-keyvaluestore put-key --kvs-arn <KVS_ARN> --if-match $ETAG --key basic_auth_sha256 --value "$(cat ~/.chariroute/basic-auth-sha256)"

# Lambda を止める / 戻す
aws lambda put-function-concurrency --function-name chariroute-api --reserved-concurrent-executions 0
aws lambda delete-function-concurrency --function-name chariroute-api   # 予約なしに戻す（1 を設定できたなら put で 1）

# ディストリビューションを無効にする（設定にシークレットが含まれるので、ファイルは ~/.chariroute/ に置き、表示しない）
aws cloudfront get-distribution-config --id <DISTRIBUTION_ID> > ~/.chariroute/dist-current.json
python - <<'EOF'
import json, pathlib
p = pathlib.Path.home() / ".chariroute"
d = json.loads((p / "dist-current.json").read_text())
cfg = d["DistributionConfig"]; cfg["Enabled"] = False
(p / "dist-disabled.json").write_text(json.dumps(cfg)); (p / "dist-etag").write_text(d["ETag"])
EOF
aws cloudfront update-distribution --id <DISTRIBUTION_ID> --if-match "$(cat ~/.chariroute/dist-etag)" \
  --distribution-config file://$HOME/.chariroute/dist-disabled.json --query 'Distribution.Status' --output text
```
- 訓練では、KeyValueStore のキーを消して 503 になるまでの時間と、戻して 200（認証後）に戻るまでの時間を測る。関数が返した 503 がキャッシュされないかも確かめる（未確認）。
- 予約済み同時実行数 0 のときに HTTP API が返すステータスを記録する（plan §7.2 の未確認事項）。
- 実 API を有効にした後は、`EXTERNAL_APIS_ENABLED=false` への変更が「外部への送信だけを止める」手段になる（送信のたびに読む）。
- 共有シークレットを入れ替えるときは、CloudFront のカスタムヘッダー → Lambda の環境変数の順に更新する。その間は API が 403 になる（値を 1 つしか受け付けないため）。
- 停止したら、何を・いつ・なぜ止めたかを `docs/progress.md` に記録する。

## 7. 削除（作成の逆順。全て ⚠。消す前に対象を一覧で確かめる）

1. CloudFront：`Enabled=false` に更新（§6）→ `aws cloudfront wait distribution-deployed` → `delete-distribution --id <ID> --if-match <ETAG>`。
2. CloudFront Function（`delete-function`）・KeyValueStore（`delete-key-value-store`）・OAC（`delete-origin-access-control`）。関数と KeyValueStore は、ディストリビューションから外れてから消せる。
3. S3：`aws s3 rm s3://$B --recursive` → `aws s3api delete-bucket --bucket $B`（バージョニングは有効にしていない）。
4. HTTP API：`aws apigatewayv2 delete-api --api-id <API_ID>`。
5. Lambda：`aws lambda delete-function --function-name chariroute-api`。
6. ロググループ：`aws logs delete-log-group --log-group-name /aws/lambda/chariroute-api`（**Lambda を消しても残る**）。
7. IAM：`delete-role-policy` → `delete-role`。
8. Budgets：`delete-budget`（費用の確認が終わってから）。
9. 最後に §2 の読み取り専用のコマンドで、`chariroute` の名前のリソースが残っていないことを確かめる。
- ローカルの `~/.chariroute/`（シークレット）は、ユーザーが自分で消す。

## 8. 操作に必要な権限（人が使う IAM Identity Center の権限セット）

最小権限の目安（推論。Service Authorization Reference は未確認なので、最初の AccessDenied で足す運用にする）。`AdministratorAccess` は使わず、作業の期間だけ割り当てる。List 系はリソースを絞れないので `*`。

| サービス | アクション（リソース） |
|---|---|
| IAM | `iam:CreateRole`・`PutRolePolicy`・`GetRole`・`ListRoles`・`DeleteRolePolicy`・`DeleteRole`（`role/chariroute-api-role`）、`iam:PassRole`（同じロールだけ、条件 `iam:PassedToService=lambda.amazonaws.com`） |
| Lambda | `lambda:CreateFunction`・`GetFunction`・`GetFunctionConfiguration`・`UpdateFunctionCode`・`UpdateFunctionConfiguration`・`AddPermission`・`RemovePermission`・`GetPolicy`・`PutFunctionConcurrency`・`DeleteFunctionConcurrency`・`GetFunctionConcurrency`・`DeleteFunction`（`function:chariroute-api`）、`ListFunctions`・`GetAccountSettings`（`*`） |
| API Gateway | `apigateway:GET`・`POST`・`PATCH`・`DELETE`（`arn:aws:apigateway:ap-northeast-1::/apis` と `/apis/*`）、`apigateway:GET`（`/restapis`。棚卸しの REST API の一覧） |
| CloudWatch Logs | `logs:CreateLogGroup`・`PutRetentionPolicy`・`FilterLogEvents`・`DeleteLogGroup`（`log-group:/aws/lambda/chariroute-api*`）、`DescribeLogGroups`（`*`）。`aws logs tail --follow` を使うなら `StartLiveTail` |
| S3 | `s3:CreateBucket`・`PutBucketPublicAccessBlock`・`PutBucketPolicy`・`GetBucketPolicy`・`ListBucket`・`DeleteBucket`（バケット）、`PutObject`・`GetObject`・`DeleteObject`（`<B>/*`）、`ListAllMyBuckets`（`*`） |
| CloudFront | `cloudfront:CreateDistribution`・`GetDistribution`・`GetDistributionConfig`・`UpdateDistribution`・`DeleteDistribution`・`ListDistributions`・`CreateOriginAccessControl`・`GetOriginAccessControl`・`ListOriginAccessControls`・`DeleteOriginAccessControl`・`ListCachePolicies`・`ListOriginRequestPolicies`・`ListResponseHeadersPolicies`・`CreateFunction`・`DescribeFunction`・`GetFunction`・`UpdateFunction`・`TestFunction`・`PublishFunction`・`DeleteFunction`・`ListFunctions`・`CreateKeyValueStore`・`DescribeKeyValueStore`・`DeleteKeyValueStore`・`ListKeyValueStores` |
| CloudFront KeyValueStore | `cloudfront-keyvaluestore:DescribeKeyValueStore`・`PutKey`・`DeleteKey`・`GetKey`・`ListKeys`（`arn:aws:cloudfront::<ACCOUNT_ID>:key-value-store/<id>`） |
| Budgets | `budgets:ViewBudget`・`ModifyBudget`（作成・削除を含む） |
| 請求の確認 | `ce:GetCostAndUsage`（任意） |

- `sts:GetCallerIdentity` に権限は要らない（推論）。`lambda:InvokeFunction` は使わない（確認は API Gateway 経由）。
- Lambda の実行ロールの権限は §4.1 のとおり、1 つのロググループへの書き込みだけ。

## 9. 費用の見積もり（個人利用。確認日 2026-11-25）

前提：1 日 20 回の画面表示と 20 回の検索（月 約 600 回）。1 回の画面表示で CloudFront へのリクエストは約 5 回（HTML・JS・CSS・API 2 回）。地図タイルは OSM から直接取得するので AWS を通らない。

| サービス | 単価・無料枠（事実） | 月の想定 | 見込み |
|---|---|---|---|
| CloudFront | 常時無料枠：データ転送 1 TB・リクエスト 1,000 万 | 約 3,000 リクエスト・1 GB 未満 | $0 |
| CloudFront Functions | $0.10/100 万回、常時無料枠 200 万回 | 約 3,000 回 | $0 |
| KeyValueStore | 関数からの読み取り $0.03/100 万回（常時無料枠 200 万回）、**それ以外の API 操作 $1/1,000 回** | 読み取り 約 3,000 回、API 操作 20〜30 回（作成・訓練） | $0〜$0.05 |
| HTTP API | $1.00/100 万リクエスト（us-east-1 の値。東京の単価は未確認）。**12 か月・100 万回の無料枠は、2025-07-15 以降に作ったアカウントには当てはまらない**（新しいアカウントは無料利用クレジットの対象） | 約 1,200 回 | $0.01 未満 |
| Lambda | 無料枠：月 100 万リクエスト・40 万 GB 秒 | 1,200 回 × 最大 28 秒 × 0.25 GB ≦ 約 8,400 GB 秒 | $0 |
| CloudWatch Logs | 取り込み・保存・スキャンで月 5 GB の無料枠 | 数 MB | $0 |
| S3 | 保存 約 0.5 MB、GET は CloudFront のキャッシュで少数 | — | $0.01 未満 |
| AWS Budgets | 監視・通知だけの予算は無料 | 1 件 | $0 |
| データ転送（Lambda → ODPT GBFS） | リージョンからインターネットへの転送は月 100 GB まで無料（2021 年の AWS の発表） | 受信が主体 | $0 |

- **想定：月 $0〜$0.10 程度**（推論）。固定費のかかるもの（WAF・独自ドメインの証明書・NAT・EC2）は使わない。
- 大量アクセスを受けた場合の目安：Basic 認証で弾かれたリクエストは CloudFront と Functions の分だけ（1,000 万 / 200 万回まで無料）。認証を通った後は、100 万リクエストで HTTP API 約 $1 + Lambda（無料枠を超えた分）。
- Budgets は止めないので、異常に気づいたら §6 で止める。
