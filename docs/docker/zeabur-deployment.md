# Zeabur 部署指南

本指南詳細介紹如何在 Zeabur 上部署 A股自選股智慧分析系統，包括 WebUI 和 Discord 機器人功能。

## 目錄

- [1. 部署前準備](#1-部署前準備)
- [2. 在 Zeabur 上部署](#2-在-zeabur-上部署)
- [3. 配置啟動命令](#3-配置啟動命令)
- [4. Discord 機器人部署](#4-discord-機器人部署)
- [5. 環境變數配置](#5-環境變數配置)
- [6. 掛載配置](#6-掛載配置)
- [7. 健康檢查](#7-健康檢查)
- [8. 常見問題](#8-常見問題)

## 1. 部署前準備

### 1.1 必要條件

- Zeabur 賬號
- GitHub 賬號（用於連線倉庫）
- Discord 開發者賬號（如需部署機器人）
- 相關 API 金鑰（如 Gemini API Key、搜尋服務 API Key 等）

### 1.2 倉庫準備

確保你的倉庫包含以下檔案：

- `.github/workflows/docker-publish.yml`（已自動建立）
- `docker/Dockerfile`（已存在）
- 完整的專案程式碼

## 2. 在 Zeabur 上部署

### 2.1 連線 GitHub 倉庫

1. 登入 Zeabur 控制檯
2. 點選「新建專案」
3. 選擇「從 GitHub 匯入」
4. 選擇你的倉庫和分支（推薦使用 `main` ）
5. 點選「匯入」

### 2.2 配置構建規則

Zeabur 會自動檢測 `.github/workflows/docker-publish.yml` 檔案，並使用 GitHub Actions 構建映象。

如果沒有自動檢測到，可以手動配置：

1. 在專案頁面，點選「構建規則」
2. 選擇「Dockerfile」
3. Dockerfile 路徑填寫：`docker/Dockerfile`
4. 點選「儲存」

### 2.3 啟動服務

1. 等待映象構建完成
2. 點選「啟動服務」
3. 服務啟動後，你可以在「訪問」標籤頁獲取訪問地址

### 2.4 前端構建與靜態資源

FastAPI 會自動託管 `static/` 目錄下的前端資源。前端打包輸出位置由
`apps/dsa-web/vite.config.ts` 決定，預設輸出到專案根目錄 `static/`。

Dockerfile 已採用多階段構建，前端會在映象構建時自動打包。
如需覆蓋預設靜態資源，可在宿主機手動構建並掛載到容器內 `/app/static`。

## 3. 配置啟動命令

### 3.1 支援的啟動模式

系統支援多種啟動模式，你可以根據需要配置不同的啟動命令：

| 模式 | 啟動命令 | 描述 |
|------|----------|------|
| 定時任務模式（預設） | `python main.py --schedule` | 按計劃執行股票分析 |
| FastAPI 模式 | `python main.py --serve` | 啟動 FastAPI 並執行分析 |
| 僅 FastAPI 模式 | `python main.py --serve-only` | 僅啟動 FastAPI，不執行分析 |
| 僅大盤覆盤 | `python main.py --market-review` | 僅執行大盤覆盤分析 |

### 3.2 配置啟動命令

1. 在 Zeabur 控制檯，進入服務頁面
2. 點選「設定」
3. 找到「啟動命令」配置項
4. 輸入你需要的啟動命令，例如：
    - 啟動 FastAPI：`python main.py --serve`
    - 僅啟動 FastAPI：`python main.py --serve-only --host 0.0.0.0 --port 8000`
    - 啟動定時任務：`python main.py --schedule`
5. 點選「儲存」
6. 重啟服務

## 4. Discord 機器人部署

### 4.1 準備工作

1. 建立 Discord 應用和機器人
   - 訪問 [Discord 開發者平臺](https://discord.com/developers/applications)
   - 點選「New Application」建立新應用
   - 在「Bot」標籤頁，點選「Add Bot」建立機器人
   - 複製機器人 Token

2. 配置機器人許可權
   - 在「Bot」標籤頁，向下滾動到「Privileged Gateway Intents」
   - 啟用「Server Members Intent」和「Message Content Intent」
   - 在「OAuth2」→「URL Generator」中，選擇「bot」範圍
   - 選擇所需許可權（如「Send Messages」、「Read Messages/View Channels」等）
   - 複製生成的邀請連結，將機器人新增到你的伺服器

### 4.2 配置環境變數

在 Zeabur 控制檯的「環境變數」配置中，新增以下變數：

| 變數名 | 說明 | 示例值 |
|--------|------|--------|
| `DISCORD_BOT_TOKEN` | Discord 機器人 Token | `MTAxMjM0NTY3ODkwMTEyMzQ1Ng.GhIjKl.MnOpQrStUvWxYz1234567890` |
| `DISCORD_MAIN_CHANNEL_ID` | 主頻道 ID | `123456789012345678` |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL（可選） | `https://discord.com/api/webhooks/...` |

### 4.3 啟動機器人

機器人功能預設透過配置啟用，無需特殊啟動命令。確保你的配置檔案中包含機器人相關配置，或透過環境變數設定。

## 5. 環境變數配置

### 5.1 基本環境變數

| 變數名 | 說明 | 預設值 |
|--------|------|--------|
| `PYTHONUNBUFFERED` | 啟用 Python 無緩衝輸出 | `1` |
| `LOG_DIR` | 日誌目錄 | `/app/logs` |
| `DATABASE_PATH` | 資料庫路徑 | `/app/data/stock_analysis.db` |

### 5.2 API 服務配置

| 變數名 | 說明 | 預設值 |
|--------|------|--------|
| `API_HOST` | API 服務監聽地址 | `0.0.0.0` |
| `API_PORT` | API 服務埠 | `8000` |

> 舊版 `WEBUI_HOST`/`WEBUI_PORT`/`WEBUI_ENABLED` 環境變數仍相容，會自動轉發到 API 服務。

### 5.3 分析相關配置

| 變數名 | 說明 |
|--------|------|
| `GEMINI_API_KEY` | Gemini API 金鑰 |
| `BOCHA_API_KEYS` | Bocha API 金鑰（用逗號分隔） |
| `MINIMAX_API_KEYS` | MiniMax API 金鑰（用逗號分隔） |
| `TAVILY_API_KEYS` | Tavily API 金鑰（用逗號分隔） |
| `SERPAPI_API_KEYS` | SerpAPI 金鑰（用逗號分隔） |
| `SEARXNG_BASE_URLS` | SearXNG 例項地址（逗號分隔，無配額兜底，需在 settings.yml 啟用 format: json） |

### 5.4 配置方法

在 Zeabur 控制檯：

1. 進入服務頁面
2. 點選「環境變數」
3. 點選「新增環境變數」
4. 輸入變數名和值
5. 點選「儲存」
6. 重啟服務

## 6. 掛載配置

### 6.1 支援的掛載目錄

| 目錄 | 說明 |
|------|------|
| `/app/data` | 資料庫和資料檔案 |
| `/app/logs` | 日誌檔案 |
| `/app/reports` | 分析報告 |

### 6.2 配置掛載

1. 在 Zeabur 控制檯，進入服務頁面
2. 點選「儲存」
3. 點選「新增儲存卷」
4. 選擇「持久化儲存」
5. 配置掛載路徑：
   - 儲存卷路徑：`/app/data`
   - 容器內路徑：`/app/data`
6. 點選「儲存」
7. 對其他需要掛載的目錄重複上述步驟

### 6.3 注意事項

- 掛載後，資料會持久化儲存，不會因容器重啟而丟失
- 建議至少掛載 `/app/data` 目錄，以儲存資料庫

## 7. 健康檢查

系統內建了健康檢查機制，預設檢查：

- WebUI 模式：檢查 `http://localhost:8000/health` 端點
- FastAPI 模式：檢查 `http://localhost:8000/api/health` 端點
- 非服務模式：始終返回健康狀態

健康檢查配置如下：

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || curl -f http://localhost:8000/health \
    || python -c "import sys; sys.exit(0)"
```

## 8. 常見問題

### 8.1 API 服務無法訪問

- 檢查啟動命令是否包含 `--serve` 或 `--serve-only` 引數
- 檢查「訪問」標籤頁是否已配置域名
- 檢查防火牆設定

### 8.2 機器人不響應

- 檢查 Discord 機器人 Token 是否正確
- 檢查機器人是否已新增到伺服器
- 檢查機器人許可權是否足夠
- 檢查日誌檔案，檢視是否有錯誤資訊

### 8.3 分析任務不執行

- 檢查定時任務配置是否正確
- 檢查 API 金鑰是否有效
- 檢查日誌檔案，檢視是否有錯誤資訊

### 8.4 資料丟失

- 確保已掛載 `/app/data` 目錄
- 檢查儲存卷配置是否正確

## 9. 高階配置

### 9.1 多例項部署

你可以在 Zeabur 上部署多個例項，用於不同的功能：

1. 一個例項用於 API 服務（`python main.py --serve-only`）
2. 一個例項用於定時任務（`python main.py --schedule`）
3. 一個例項用於機器人（`python main.py --discord-bot`）

確保它們共享同一個 `/app/data` 儲存卷，以共享資料庫。

### 9.2 自定義域名

在 Zeabur 控制檯的「訪問」標籤頁，你可以：

1. 使用自動生成的域名
2. 繫結自定義域名
3. 配置 HTTPS

## 10. 更新部署

### 10.1 自動更新

當你向倉庫推送新程式碼時：

1. GitHub Actions 會自動構建新映象
2. Zeabur 會檢測到新映象
3. 你可以選擇「自動部署」或手動觸發部署

### 10.2 手動更新

1. 在 Zeabur 控制檯，進入服務頁面
2. 點選「部署歷史」
3. 選擇「重新部署」
4. 或點選「更新映象」

## 11. 監控和日誌

### 11.1 檢視日誌

在 Zeabur 控制檯，進入服務頁面，點選「日誌」標籤頁，可以檢視實時日誌和歷史日誌。

### 11.2 監控指標

Zeabur 提供了基礎的監控指標：

- CPU 使用率
- 記憶體使用率
- 網路流量
- 磁碟使用率

在「監控」標籤頁檢視詳細指標。

## 12. 故障排查

### 12.1 檢視詳細日誌

```bash
# 進入容器
zeabur exec <服務名> bash

# 檢視日誌檔案
cat /app/logs/stock_analysis_20260125.log
```

### 12.2 檢查配置

```bash
# 進入容器
zeabur exec <服務名> bash

# 檢查環境變數
printenv | grep -i discord
printenv | grep -i webui
```

### 12.3 測試連線

```bash
# 測試網路連線
zeabur exec <服務名> curl -I https://api.discord.com

# 測試 API 連線
zeabur exec <服務名> python -c "import requests; print(requests.get('https://api.discord.com').status_code)"
```

## 13. 最佳實踐

1. **使用持久化儲存**：始終掛載 `/app/data` 目錄，以儲存資料庫
2. **配置合理的健康檢查**：根據實際情況調整健康檢查引數
3. **使用環境變數管理敏感資訊**：不要將 API 金鑰硬編碼到程式碼中
4. **定期備份資料**：定期下載 `/app/data` 目錄的內容進行備份
5. **使用合適的啟動模式**：根據需求選擇合適的啟動命令
6. **監控服務狀態**：定期檢查服務狀態和日誌

## 14. 聯絡方式

如有問題，歡迎聯絡專案維護者或在 GitHub Issues 中提問。
