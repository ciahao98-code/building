# E-BERSe 個人網站部署

此版本供一位站主使用。打開部署提供的 HTTPS 網址後，瀏覽器會要求輸入自己的 Email 與網站專用密碼。Email 用作登入名稱。網站可上傳照片辨識、手動編輯、儲存草稿及下載可編輯的 XLSX。

## Render 一次設定

1. 解壓縮，將壓縮檔中的程式檔案放到一個 GitHub 私人儲存庫的根目錄。
2. 在 Render 建立 Web Service，連接該私人儲存庫，Runtime 選 Python。
3. Build Command 設為 `python -m py_compile app.py hosted.py report.py`，Start Command 設為 `python hosted.py`。可在進階設定將 Health Check Path 設為 `/healthz`。
4. 在 Render 的 Environment 頁面設定 `EAC_LOGIN_EMAIL` 為自己的 Email，`EAC_LOGIN_PASSWORD` 為至少 16 字元、只用在這個網站的密碼。要使用照片辨識時，加入 `OPENAI_API_KEY`，使用有 API 額度的金鑰。以上秘密只填入 Render Environment。
5. 若要讓草稿在網站重啟與重新部署後保留，請使用支援持久磁碟的方案，掛載磁碟到 `/opt/render/project/src/data`，再設定 `EAC_DATA_DIR=/opt/render/project/src/data`。未掛載磁碟時，請使用「下載案件 JSON」保存案件進度。
6. 部署完成後，開啟 Render 顯示的 HTTPS 網址，輸入第 4 步設定的 Email 和密碼。日常操作直接用瀏覽器。

Excel 採用隨附的 E-BERSe 範本。黃色輸入欄可在 Excel 中修改及另存。原範本公式的參照問題需在正式送件前覆核。從網路下載的檔案若在 Excel「受保護的檢視」中開啟，確認來源後可按「啟用編輯」。
