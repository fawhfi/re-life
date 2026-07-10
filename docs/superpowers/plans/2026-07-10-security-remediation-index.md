# Re-Life 網絡安全修復計畫索引

本索引把已批准的安全設計拆成五份按依賴順序執行的中文實作計畫。每份計畫都能獨立測試與提交，但後一階段可以假設前一階段已完成。

## 執行順序

1. [Session 與身份驗證](2026-07-10-session-authentication.md)
2. [帳戶與紀錄授權](2026-07-10-account-record-authorization.md)
3. [電郵驗證與密碼重設](2026-07-10-email-password-security.md)
4. [圖片上傳與 AI 驗證](2026-07-10-upload-ai-validation.md)
5. [Supabase 與瀏覽器平台強化](2026-07-10-platform-hardening.md)

## 共通執行規則

- 每項正式程式碼改動先寫會因漏洞仍存在而失敗的測試，確認紅燈後才實作。
- 每個任務只提交列出的檔案；不要混入無關重構或天氣 UI 測試修復。
- 聚焦測試通過後再執行完整測試；現有 `test_smoke.py` 天氣標籤失敗要獨立記錄。
- 任何安全驗證未能執行時，不得宣稱該階段已修復；必須記錄為未知或受阻。
- 既有瀏覽器 `localStorage` 身份資料不遷移，部署後要求重新登入。

## 規格覆蓋對照

- Session token 雜湊、30 天閒置期限、Cookie、登出與撤銷：計畫 1。
- 公開帳戶端點、免密碼切換、IDOR、紀錄 owner 與受保護掃描：計畫 2。
- 強制電郵驗證、代碼嘗試限制、登入枚舉、Argon2 rehash、重設撤銷：計畫 3。
- 有界圖片讀取、Pillow 重新編碼、頭像、Pydantic schema、AI 結果及 endpoint：計畫 4。
- RLS、private bucket、Edge Function 移除、正式環境驗證、CORS、CSRF、CSP、headers 與安全日誌：計畫 5。
- 每份計畫最後一個任務均包含原始漏洞重現檢查、合法行為控制及完整測試。

## 建議驗證命令

```powershell
python -m pytest tests/test_session_auth.py -v
python -m pytest tests/test_account_authorization.py tests/test_record_authorization.py -v
python -m pytest tests/test_email_auth_security.py -v
python -m pytest tests/test_image_security.py tests/test_ai_validation.py -v
python -m pytest tests/test_platform_security.py -v
python -m pytest tests -v
```

完整測試的已知 baseline 是一項與安全工作無關的天氣 UI assertion 失敗。安全相關測試不得以這個 baseline 為理由忽略任何新失敗。
