# ❓ 常見問題解答 (FAQ)

本文件整理了使用者在使用過程中遇到的常見問題及解決方案。

---

## 📊 資料相關

### Q1: 美股程式碼（如 AMD, AAPL）分析時價格顯示不正確？

**現象**：輸入美股程式碼後，顯示的價格明顯不對（如 AMD 顯示 7.33 元），或被誤識別為 A 股。

**原因**：早期版本程式碼匹配邏輯優先嚐試國內 A 股規則，導致程式碼衝突。

**解決方案**：
1. 已在 v2.3.0 修復，系統現在支援美股程式碼自動識別
2. 如仍有問題，可在 `.env` 中設定：
   ```bash
   YFINANCE_PRIORITY=0
   ```
   這將優先使用 Yahoo Finance 資料來源獲取美股資料

> 📌 相關 Issue: [#153](https://github.com/ZhuLinsen/daily_stock_analysis/issues/153)

---

### Q2: 報告中"量比"欄位顯示為空或 N/A？

**現象**：分析報告中量比資料缺失，影響 AI 對縮放量的判斷。

**原因**：預設的某些實時行情源（如新浪介面）不提供量比欄位。

**解決方案**：
1. 已在 v2.3.0 修復，騰訊介面現已支援量比解析
2. 推薦配置實時行情源優先順序：
   ```bash
   REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
   ```
3. 系統已內建 5 日均量計算作為兜底邏輯

> 📌 相關 Issue: [#155](https://github.com/ZhuLinsen/daily_stock_analysis/issues/155)

---

### Q3: Tushare 獲取資料失敗，提示 Token 不對？

**現象**：日誌顯示 `Tushare 獲取資料失敗: 您的token不對，請確認`

**解決方案**：
1. **無 Tushare 賬號**：無需配置 `TUSHARE_TOKEN`，系統會自動使用免費資料來源（AkShare、Efinance）
2. **有 Tushare 賬號**：確認 Token 是否正確，可在 [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) 個人中心檢視
3. 本專案所有核心功能均可在無 Tushare 的情況下正常執行

---

### Q4: 資料獲取被限流或返回為空？

**現象**：日誌顯示 `熔斷器觸發` 或資料返回 `None`，或出現 `RemoteDisconnected`、`push2his.eastmoney.com` 連線被關閉等

**原因**：免費資料來源（東方財富、新浪等）有反爬機制，短時間大量請求會被限流。

**解決方案**：
1. 系統已內建多資料來源自動切換和熔斷保護
2. 減少自選股數量，或增加請求間隔
3. 避免頻繁手動觸發分析
4. 若東財介面頻繁失敗，可設定 `ENABLE_EASTMONEY_PATCH=true` 啟用東財補丁（注入 NID 令牌與隨機 User-Agent，降低被限流機率）
5. 將 `MAX_WORKERS=1` 改為序列獲取，減少對東財的併發壓力

---

## ⚙️ 配置相關

### Q5: GitHub Actions 執行失敗，提示找不到環境變數？

**現象**：Actions 日誌顯示 `GEMINI_API_KEY` 或 `STOCK_LIST` 未定義

**原因**：GitHub 區分 `Secrets`（加密）和 `Variables`（普通變數），配置位置不對會導致讀取失敗。

**解決方案**：
1. 進入倉庫 `Settings` → `Secrets and variables` → `Actions`
2. **Secrets**（點選 `New repository secret`）：存放敏感資訊
   - `GEMINI_API_KEY`
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - 各類 Webhook URL
3. **Variables**（點選 `Variables` 標籤）：存放非敏感配置
   - `STOCK_LIST`
   - `GEMINI_MODEL`
   - `REPORT_TYPE`

---

### Q6: 修改 .env 檔案後配置沒有生效？

**解決方案**：
1. 確保 `.env` 檔案位於專案根目錄
2. **Docker 部署**：修改後需重啟容器
   ```bash
   docker-compose down && docker-compose up -d
   ```
3. **GitHub Actions**：`.env` 檔案不生效，必須在 Secrets/Variables 中配置
4. 檢查是否有多個 `.env` 檔案（如 `.env.local`）導致覆蓋

---

### Q7: 如何配置代理訪問 Gemini/OpenAI API？

**解決方案**：

在 `.env` 中配置：
```bash
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=10809
```

> ⚠️ 注意：代理配置僅對本地執行生效，GitHub Actions 環境無需配置代理。

---

### LLM 配置常見問題

> 完整說明見 [LLM 配置指南](LLM_CONFIG_GUIDE.md)。

**Q: 配置了 GEMINI_API_KEY 和 LLM_CHANNELS，為什麼只用渠道？**

系統按優先順序只取一種：`LITELLM_CONFIG` (YAML) > `LLM_CHANNELS` > legacy keys。一旦配置了渠道或 YAML，legacy 區域（`GEMINI_API_KEY` 等）不參與解析。

**Q: test_env 輸出 ✗ 未配置任何 LLM 怎麼辦？**

配置 `LITELLM_CONFIG` / `LLM_CHANNELS` 或至少一個 `*_API_KEY`（如 `GEMINI_API_KEY`、`DEEPSEEK_API_KEY`、`AIHUBMIX_KEY`）。執行 `python test_env.py --config` 校驗配置，`python test_env.py --llm` 實際呼叫 API 測試。

**Q: 如何同時使用多個模型（如 AIHubmix + DeepSeek + Gemini）？**

使用渠道模式：設定 `LLM_CHANNELS=aihubmix,deepseek,gemini`，並配置各渠道的 `LLM_{NAME}_BASE_URL`、`LLM_{NAME}_API_KEY`、`LLM_{NAME}_MODELS`。也可在 Web 設定頁 → AI 模型 → 渠道編輯器中視覺化配置。

---

## 📱 推送相關

### Q8: 機器人推送失敗，提示訊息過長？

**現象**：分析成功但未收到推送，日誌顯示 400 錯誤或 `Message too long`

**原因**：不同平臺訊息長度限制不同：
- 企業微信：4KB
- 飛書：20KB
- 釘釘：20KB

**解決方案**：
1. **自動分塊**：最新版本已實現長訊息自動切割
2. **單股推送模式**：設定 `SINGLE_STOCK_NOTIFY=true`，每分析完一隻股票立即推送
3. **精簡報告**：設定 `REPORT_TYPE=simple` 使用精簡格式

---

### Q9: Telegram 推送收不到訊息？

**解決方案**：
1. 確認 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 都已配置
2. 獲取 Chat ID 方法：
   - 給 Bot 傳送任意訊息
   - 訪問 `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 在返回的 JSON 中找到 `chat.id`
3. 確保 Bot 已被新增到目標群組（如果是群聊）
4. 本地執行時需要能訪問 Telegram API（可能需要代理）

---

### Q10: 企業微信 Markdown 格式顯示不正常？

**解決方案**：
1. 企業微信對 Markdown 支援有限，可嘗試設定：
   ```bash
   WECHAT_MSG_TYPE=text
   ```
2. 這將傳送純文字格式的訊息

---

## 🤖 AI 模型相關

### Q11: Gemini API 返回 429 錯誤（請求過多）？

**現象**：日誌顯示 `Resource has been exhausted` 或 `429 Too Many Requests`

**解決方案**：
1. Gemini 免費版有速率限制（約 15 RPM）
2. 減少同時分析的股票數量
3. 增加請求延遲：
   ```bash
   GEMINI_REQUEST_DELAY=5
   ANALYSIS_DELAY=10
   ```
4. 或切換到 OpenAI 相容 API 作為備選

---

### Q12: 如何使用 DeepSeek 等國產模型？

**配置方法**：

```bash
# 不需要配置 GEMINI_API_KEY
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
# 思考模式：deepseek-reasoner、deepseek-r1、qwq 等自動識別；deepseek-chat 系統按模型名自動啟用
```

支援的模型服務：
- DeepSeek: `https://api.deepseek.com/v1`
- 通義千問: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Moonshot: `https://api.moonshot.cn/v1`

---

## 🐳 Docker 相關

### Q13: Docker 容器啟動後立即退出？

**解決方案**：
1. 檢視容器日誌：
   ```bash
   docker logs <container_id>
   ```
2. 常見原因：
   - 環境變數未正確配置
   - `.env` 檔案格式錯誤（如有多餘空格）
   - 依賴包版本衝突

---

### Q14: Docker 中 API 服務無法訪問？

**解決方案**：
1. 確保啟動命令包含 `--host 0.0.0.0`（不能是 127.0.0.1）
2. 檢查埠對映是否正確：
   ```yaml
   ports:
     - "8000:8000"
   ```

---

### Q14.1: Docker 中網路/DNS 解析失敗（如 api.tushare.pro、searchapi.eastmoney.com 無法解析）？

**現象**：日誌顯示 `Temporary failure in name resolution` 或 `NameResolutionError`，股票資料 API 和大模型 API 均無法訪問。

**原因**：自定義 bridge 網路下，容器使用 Docker 內建 DNS，在旁路由、特定網路環境時可能解析失敗。

**解決方案**（按優先順序嘗試）：

1. **顯式配置 DNS**：在 `docker/docker-compose.yml` 的 `x-common` 下新增：
   ```yaml
   dns:
     - 223.5.5.5
     - 119.29.29.29
     - 8.8.8.8
   ```
   然後執行 `docker-compose down` 和 `docker-compose up -d --force-recreate` 重新建立容器。

2. **改用 host 網路模式**：若上述仍無效，可在 `server` 服務下新增 `network_mode: host`，並移除 `ports` 對映。使用 host 模式時，`ports` 無效，**埠由 `command` 中的 `--port` 指定**。若宿主機預設埠已佔用，可修改為其他埠（如 `.env` 中設定 `API_PORT=8080`），訪問對應 `http://localhost:8080`。

> 📌 相關 Issue: [#372](https://github.com/ZhuLinsen/daily_stock_analysis/issues/372)

---

## 🔧 其他問題

### Q15: 如何只執行大盤覆盤，不分析個股？

**方法**：
```bash
# 本地執行
python main.py --market-only

# GitHub Actions
# 手動觸發時選擇 mode: market-only
```

---

### Q16: 分析結果中買入/觀望/賣出數量統計不對？

**原因**：早期版本使用正則匹配統計，可能與實際建議不一致。

**解決方案**：已在最新版本中修復，AI 模型現在會直接輸出 `decision_type` 欄位用於準確統計。

---

### Q17: 為什麼週末在 GitHub Actions 手動觸發仍顯示“非交易日跳過”？

**現象**：已經配置了 `TRADING_DAY_CHECK_ENABLED` 或希望手動執行，但日誌仍提示“今日所有相關市場均為非交易日，跳過執行”。

**解決方案**：
1. 開啟 `Actions → 每日股票分析 → Run workflow`
2. 手動觸發時將 `force_run` 設為 `true`（單次強制執行）
3. 如果希望長期關閉交易日檢查，在 `Settings → Secrets and variables → Actions` 中設定：
   ```bash
   TRADING_DAY_CHECK_ENABLED=false
   ```

**規則說明**：
- `TRADING_DAY_CHECK_ENABLED=true` 且 `force_run=false`：非交易日跳過（預設）
- `force_run=true`：本次即使非交易日也執行
- `TRADING_DAY_CHECK_ENABLED=false`：定時和手動都不做交易日檢查

---

## 💬 還有問題？

如果以上內容沒有解決你的問題，歡迎：
1. 檢視 [完整配置指南](full-guide.md)
2. 搜尋或提交 [GitHub Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)
3. 檢視 [更新日誌](CHANGELOG.md) 瞭解最新修復

---

*最後更新：2026-02-28*
