# Re-Life 網絡安全修復設計

**日期：** 2026-07-10

**狀態：** 已批准

## 目標

在保留現有 `app_users` 帳戶系統的前提下，修復應用程式失效的身份驗證與授權邊界；同時強化電郵驗證、密碼重設、檔案上傳、AI 結果處理、Supabase 存取、瀏覽器安全控制，以及正式環境的安全失敗行為。

獎勵與積分仍屬模擬功能，其產品規則不作修改；但所有操作必須綁定目前已驗證帳戶，避免一名使用者影響另一名使用者。

## 已確認的產品決定

- 保留自建 `app_users` 帳戶系統，不遷移至 Supabase Auth。
- 新增由伺服器與資料庫管理的 Session。
- 部署後要求所有現有使用者重新登入；不信任或遷移 `localStorage` 內的身份資料。
- 允許新增安全相關的 Supabase 資料表及 schema 變更。
- 移除免密碼使用者選擇器及所有公開帳戶查詢功能。
- 不提供公開使用者頁面或使用者搜尋。
- 圖片掃描、紀錄、帳戶修改及獎勵兌換都必須登入。
- 建立帳戶前必須完成電郵驗證。
- 只有同時設定 `APP_ENV=development` 與 `ALLOW_DEV_AUTH_CODES=true` 時，才可回傳開發用驗證碼。
- Session 連續 30 天沒有活動便失效；登出撤銷目前 Session，重設密碼撤銷該帳戶全部 Session。
- 正式環境的前端與 API 使用相同來源。
- 正式環境無法使用 Supabase、Session 儲存、驗證碼儲存、郵件服務或限流服務時，必須安全失敗。
- 保留目前模擬積分與獎勵規則。

## 目前可利用的漏洞路徑

### 由客戶端控制身份

登入與註冊會把使用者名稱和識別碼寫入 `localStorage`。後續 API 請求把這些值作為 `user_id`、`display_name` 或 `user_key` 傳送，而後端直接視其為資源擁有者。攻擊者可以提交另一帳戶的識別碼，以該帳戶身份讀取、建立、修改或刪除資料。

### 免密碼帳戶切換

`GET /api/users` 公開帳戶清單，首頁使用者選擇器則在沒有密碼的情況下呼叫 `loginAs()`。這是一條直接的帳戶接管路徑。

### 缺少物件層授權

紀錄查詢、建立、清空、圖片上傳及刪除都沒有綁定已驗證主體；以紀錄 ID 刪除時也沒有檢查擁有權。

### 可繞過註冊驗證

電郵驗證碼與帳戶建立是兩個分開的操作；註冊端點本身沒有要求已成功驗證的證明，並會把任何提供的電郵標記為已驗證。

### 不安全的信任邊界

上傳流程信任宣告的 MIME type；帳戶資料接受任意頭像字串；AI 輸出未完整驗證；正式環境依賴故障時可靜默退回程序記憶體。

## 安全不變量

1. 已驗證主體只能來自有效、由伺服器簽發的 Session Cookie。
2. 客戶端提交的帳戶識別碼永遠不能決定擁有權或授權結果。
3. 使用者只能讀取或修改自己的帳戶與紀錄。
4. 沒有消耗有效且未過期的電郵驗證碼，就不能建立帳戶。
5. 原始 Session token、密碼、驗證碼、重設碼、API key 與 service-role key 不得寫入日誌或回傳給正式環境客戶端。
6. 正式環境必要安全依賴不可用時，身份驗證必須安全失敗。
7. 圖片與 AI 結果在使用或保存前，必須在伺服器邊界完成驗證。
8. 會修改狀態的瀏覽器請求必須同源，並受到 CSRF 防護。

## 1. 資料庫型 Session 架構

新增 `app_sessions` 資料表，包含：

- 自動產生的 Session ID；
- 指向 `app_users` 並在刪除帳戶時連帶刪除的 `user_id`；
- 隨機 Session token 的唯一 SHA-256 雜湊；
- `created_at` 與 `last_seen_at`；
- 可為空的 `revoked_at`；
- 長度受限、可供稽核與支援使用，但不包含秘密的裝置與請求資料。

登入或註冊成功後，伺服器以密碼學安全亂數產生 256-bit token。資料庫只保存 SHA-256 雜湊；原始 token 置於 `rel_session` Cookie，設定 `HttpOnly`、`SameSite=Lax`、`Path=/`，正式環境再加入 `Secure`。

每個受保護請求都會雜湊 Cookie token，查找未撤銷的 Session 及其使用者；若 `last_seen_at` 已相隔至少 30 天便拒絕。有效 Session 會更新活動時間與 Cookie 期限。為避免每個請求都寫入資料庫，可在短時間內合併活動更新，但接近到期邊界的有效請求必須延長 Session。

登出會設定目前 Session 的 `revoked_at` 並清除 Cookie；重設密碼會撤銷該使用者所有 Session。適用時使用 constant-time 比較，原始 token 永不寫入日誌。

新增端點：

- `GET /api/auth/me`：回傳目前標準化使用者，否則回傳 `401`。
- `POST /api/auth/logout`：撤銷目前 Session 並清除 Cookie。

登入與註冊成功回應同樣會設定 Session Cookie。正式環境 Supabase 不可用時，Session 操作回傳 `503`；只有明確設定的開發模式才可使用記憶體 Session。

## 2. 授權與 API 表面

解析目前 Session 的 FastAPI dependency，成為所有受保護路由唯一的授權邊界。

### 受保護資源

- `/` 在未登入時重新導向 `/login`。
- `/api/scan/ai` 要求有效 Session。
- 所有 `/api/records` 操作與紀錄圖片上傳要求有效 Session。
- `/api/rewards/redeem` 要求有效 Session，但保留模擬獎勵規則。
- 帳戶讀取與更新改用 `/api/users/me`，並只能操作 Session 使用者。

### 移除帳戶探索端點

移除：

- `GET /api/users`
- `GET /api/users/by-name/{display_name}`
- `GET /api/users/by-email/{email}`
- `GET /api/users/by-id/{identifier}`
- `PATCH /api/users/{identifier}`

以以下自助端點取代必要功能：

- `GET /api/users/me`
- `PATCH /api/users/me`

### 紀錄擁有權

紀錄 API 不再接受 `user_id`、`display_name` 或 `user_key` 作為授權輸入。後端建立、列出、清空紀錄或上傳紀錄圖片時，直接使用 Session 使用者的資料庫 ID。

刪除紀錄時同時以紀錄 ID 與 Session 使用者 ID 過濾。紀錄不存在和屬於其他使用者都回傳 `404`，避免洩漏資源存在。儲存路徑使用由伺服器取得的帳戶識別分區。

### 前端身份

移除 `showUserPicker()` 與 `loginAs()`。不再從 `RE_LIFE_CURRENT_USER`、`RE_LIFE_CURRENT_USER_ID`、`RE_LIFE_CURRENT_USER_KEY` 恢復身份。頁面啟動時呼叫 `/api/auth/me`；收到 `401` 便導向 `/login`。

`localStorage` 只保留語言、主題、聲音等非安全偏好。

## 3. 註冊、登入與密碼重設

### 註冊

`POST /api/send-verification` 使用密碼學安全亂數產生六位數驗證碼。資料庫只保存以專用正式環境秘密計算的 HMAC digest，以及用途、標準化電郵、期限、嘗試次數與消耗狀態。驗證碼十分鐘後過期，重新發送會使舊碼失效。

前端提交驗證碼時，以 display name、email、password 和 code 一次呼叫 `POST /api/auth/register`。後端先驗證並消耗驗證碼，才建立使用者與 Session。移除獨立的 `/api/verify-code`。

驗證碼錯誤五次後不能再使用。帳戶建立會強制唯一的標準化電郵與 display name，密碼至少八個字元。

### 登入

帳戶不存在與密碼錯誤回傳相同的 `INVALID_CREDENTIALS`。身份驗證限流同時使用請求 IP 與標準化帳戶 key。Argon2 成功驗證後，如現有 hash 不符合最新參數，立即重新雜湊。

### 密碼重設

忘記密碼的回應不透露電郵是否已註冊。重設碼採用與驗證碼相同的期限、雜湊、嘗試次數、重送及開發模式規則。重設成功後更新 Argon2 hash、消耗代碼，並撤銷該帳戶所有 Session。

### 開發驗證碼與依賴故障

只有同時設定 `APP_ENV=development` 與 `ALLOW_DEV_AUTH_CODES=true` 時才回傳 `dev_code`；其他環境郵件發送失敗只回傳一般服務錯誤。

正式環境若缺少驗證碼秘密或郵件設定，應拒絕啟動。設定的分散式限流器或持久化驗證碼／Session 儲存不可用時，身份驗證端點回傳 `503`。

## 4. 檔案上傳、頭像與 AI 驗證

為掃描圖片、紀錄圖片及頭像建立共用圖片驗證邊界：

- 讀取請求時即執行位元組上限，不先接受無界限內容；
- 判定格式時忽略宣告的 MIME type 和副檔名；
- 使用 Pillow 解碼，只接受 JPEG、PNG 或 WebP；
- 拒絕損壞圖片、解壓縮炸彈及不合理尺寸；
- 傳送或保存前重新編碼，移除 EXIF 與嵌入內容；
- 使用伺服器產生的檔名和 Session 衍生儲存前綴。

`scan-images` bucket 改為 private。應用程式產生的代理 URL 保持短期有效，並不得暴露 service-role key。

帳戶更新不再接受任意 `photoUrl` 或 data URL。Emoji 頭像只允許伺服器定義的白名單；圖片頭像使用受保護 multipart 上傳端點及相同的解碼／重新編碼流程。前端使用 `textContent`、`src` 等 DOM property，而不把未驗證字串串接到 `innerHTML`。

為身份驗證、帳戶更新、紀錄、掃描及獎勵定義 Pydantic request／response model，限制字串長度、標準化電郵、支援的語言、固定 enum，以及整數和清單範圍。

AI 結果在評分或保存前先標準化並驗證。material、mode、grade 等類別值必須屬於支援 enum；分數必須是有限數且在文件範圍內；文字及清單受長度和數量限制。無效 provider 輸出會觸發安全 fallback 或受控錯誤，不可直接寫入資料庫。

正式環境自訂 AI endpoint 必須使用 HTTPS。外部呼叫維持嚴格 timeout、限制回應大小，並只向客戶端回傳一般上游錯誤。

## 5. Supabase 與瀏覽器強化

在 `app_users`、`app_sessions`、`auth_codes`、`scan_records` 啟用 RLS，撤銷 `anon` 與 `authenticated` 的直接資料權限。瀏覽器永不接收 service-role key；FastAPI 是自建帳戶資料表唯一的資料存取權威。

把 `scan-images` bucket 設為 private，保留只允許 service role 的儲存 policy。移除未使用的 `admin_users`、`my_records` Edge Functions 及其設定，避免保留第二套不一致的身份模型。

在匯入讀取設定的模組前載入 `.env`。正式環境啟動時驗證：

- Supabase URL 與 service-role key；
- 應用程式環境；
- 允許的 origins 與 hosts；
- 驗證碼秘密；
- 郵件服務設定；
- 分散式限流設定；
- Session 與上傳安全設定。

公開設定回應只使用明確 allowlist，不序列化任意環境資料。

新增 `TrustedHostMiddleware`、明確 CORS origin 清單、只供已設定本機開發 origin 使用的 credential 支援，以及 unsafe method 的同源驗證。Origin 不合法時，在狀態變更前回傳 `403`。

保留 `X-Content-Type-Options`、只在 HTTPS 正式環境使用的 HSTS、Referrer Policy、frame denial 與 Permissions Policy。新增限制 script、style、圖片、連線、object、frame、base URL 及表單目的地的 CSP。移除 inline 身份切換 handler，其餘 inline handler 與 script 遷移至註冊事件監聽器，使 CSP 不依賴任意 inline script。

## 6. 錯誤處理與安全日誌

統一狀態碼語義：

- `401`：缺少、過期或已撤銷的身份驗證；
- `403`：已登入但違反 origin 或安全政策；
- `404`：資源不存在或不屬於目前使用者；
- `422`：結構化輸入驗證失敗；
- `429`：限流；
- `503`：必要安全依賴不可用。

可能洩漏帳戶、紀錄、provider 設定或內部基礎設施時，客戶端只收到一般錯誤。

安全日誌包含產生的 request ID、事件類別、路由、結果，以及可用時的內部帳戶 ID；不包含密碼、驗證碼、重設資料、Cookie、原始 Session token、API key、service-role key、完整 request body 或完整電郵地址。

## 7. 測試策略

所有正式程式變更都採用 red-green-refactor。回歸測試必須先經真正的 FastAPI 或 helper 邊界展示不安全行為，並因預期的安全原因失敗。

必要測試包括：

- 受保護端點拒絕未登入請求；
- 登入與已驗證註冊會發出安全 Session Cookie；
- 偽造帳戶識別碼不能影響擁有權；
- 使用者不能讀取、修改、清空或刪除其他使用者的紀錄；
- 免密碼帳戶清單與切換功能不存在；
- 登出、密碼重設、撤銷及 30 天沒有活動會使 Session 失效；
- Session 儲存只包含 token 雜湊；
- 無效、過期、重用或超過嘗試次數的驗證碼不能建立帳戶；
- 正式環境不回傳開發碼或使用記憶體身份 fallback；
- 重設流程不枚舉帳戶，並撤銷所有 Session；
- CSRF 與錯誤 Origin 在修改狀態前失敗；
- 偽造 MIME、超大圖片、損壞檔案、解壓縮炸彈及異常尺寸被拒絕；
- 接受的圖片會重新編碼並移除 metadata；
- 無效 AI enum、非有限或超出範圍分數、過大輸出被拒絕或安全處理；
- RLS、private storage、已移除 Edge Functions、安全 headers、CORS 與啟動驗證符合設計。

正向控制涵蓋合法登入、Session 恢復、自身帳戶更新、掃描、紀錄 CRUD、頭像更新、密碼重設與模擬獎勵。

現有且無關安全工作的天氣 UI assertion 會記錄為 baseline failure，不在此安全工作中修改。每個階段都執行聚焦安全測試與完整測試；已知的無關 baseline 會獨立報告，不會隱藏。

## 8. 交付階段

### 階段一：Session 與身份驗證

新增 Session schema、Session service、登入 Cookie、`/api/auth/me`、登出、閒置到期、撤銷、正式環境安全失敗與聚焦測試。

### 階段二：帳戶與紀錄授權

以 `/api/users/me` 取代公開帳戶端點，把所有紀錄操作綁定 Session 使用者，移除使用者選擇器與客戶端身份，加入跨帳戶 exploit 測試。

### 階段三：電郵驗證與密碼重設

註冊時消耗驗證碼，限制驗證碼嘗試及正式環境寄送行為，統一登入錯誤，需要時重新雜湊 Argon2 密碼，重設時撤銷 Session，並加入回歸測試。

### 階段四：上傳與 AI 驗證

新增共用圖片驗證與重新編碼、受保護頭像上傳、private storage、Pydantic request model、AI 輸出驗證、外部 endpoint 限制與對抗性輸入測試。

### 階段五：平台強化

套用 RLS 與 grants，移除未使用 Edge Functions，修正環境載入，新增啟動驗證，強制 CORS／host／origin 規則，強化 headers 與 CSP，完成安全驗證矩陣。

每個階段都必須讓應用程式處於可工作、可測試狀態。需要的 schema 先於依賴它的程式碼部署。由於現有瀏覽器身份不會遷移，部署後自然要求安全重新登入。

## 完成標準

只有符合以下條件才算完成：

- 原有免密碼切換和識別碼偽造路徑不能再重現；
- 所有受保護操作都從有效資料庫 Session 取得擁有權；
- 合法使用者可註冊、登入、恢復 Session、只管理自己的資料、重設密碼及登出；
- 所有聚焦安全測試通過；
- 相關現有測試維持 baseline 或改善；
- 資料庫及 storage policy 符合只經後端存取的模型；
- 正式環境缺少安全設定時會安全失敗，不洩漏秘密或開發碼；
- 任何剩餘限制或無法執行的整合驗證都明確記錄。
