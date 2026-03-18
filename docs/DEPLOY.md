# 🚀 部署指南

本文件介紹如何將 A股自選股智慧分析系統部署到伺服器。

## 📋 部署方案對比

| 方案 | 優點 | 缺點 | 推薦場景 |
|------|------|------|----------|
| **Docker Compose** ⭐ | 一鍵部署、環境隔離、易遷移、易升級 | 需要安裝 Docker | **推薦**：大多數場景 |
| **直接部署** | 簡單直接、無額外依賴 | 環境依賴、遷移麻煩 | 臨時測試 |
| **Systemd 服務** | 系統級管理、開機自啟 | 配置繁瑣 | 長期穩定執行 |
| **Supervisor** | 程序管理、自動重啟 | 需要額外安裝 | 多程序管理 |

**結論：推薦使用 Docker Compose，遷移最快最方便！**

---

## 🐳 方案一：Docker Compose 部署（推薦）

### 1. 安裝 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# CentOS
sudo yum install -y docker docker-compose
sudo systemctl start docker
sudo systemctl enable docker
```

### 2. 準備配置檔案

```bash
# 克隆程式碼（或上傳程式碼到伺服器）
git clone <your-repo-url> /opt/stock-analyzer
cd /opt/stock-analyzer

# 複製並編輯配置檔案
cp .env.example .env
vim .env  # 填入真實的 API Key 等配置
```

### 3. 一鍵啟動

```bash
# 構建並啟動（同時包含定時分析和 Web 介面服務）
docker-compose -f ./docker/docker-compose.yml up -d

# 檢視日誌
docker-compose -f ./docker/docker-compose.yml logs -f

# 檢視執行狀態
docker-compose -f ./docker/docker-compose.yml ps
```

啟動成功後，在瀏覽器輸入 `http://伺服器公網IP:8000` 即可開啟 Web 管理介面。如果打不開，記得先在雲伺服器控制檯的「安全組」裡放行 8000 埠。

> 不知道怎麼訪問？→ [雲伺服器 Web 介面訪問指南](deploy-webui-cloud.md)

### 4. 常用管理命令

```bash
# 停止服務
docker-compose -f ./docker/docker-compose.yml down

# 重啟服務
docker-compose -f ./docker/docker-compose.yml restart

# 更新程式碼後重新部署
git pull
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d

# 進入容器除錯
docker-compose -f ./docker/docker-compose.yml exec stock-analyzer bash

# 手動執行一次分析
docker-compose -f ./docker/docker-compose.yml exec stock-analyzer python main.py --no-notify
```

### 5. 資料持久化

資料自動儲存在宿主機目錄：
- `./data/` - 資料庫檔案
- `./logs/` - 日誌檔案
- `./reports/` - 分析報告

---

## 🖥️ 方案二：直接部署

### 1. 安裝 Python 環境

```bash
# 安裝 Python 3.10+
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip

# 建立虛擬環境
python3.10 -m venv /opt/stock-analyzer/venv
source /opt/stock-analyzer/venv/bin/activate
```

### 2. 安裝依賴

```bash
cd /opt/stock-analyzer
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 配置環境變數

```bash
cp .env.example .env
vim .env  # 填入配置
```

### 4. 執行

```bash
# 單次執行
python main.py

# 定時任務模式（前臺執行）
python main.py --schedule

# 後臺執行（使用 nohup）
nohup python main.py --schedule > /dev/null 2>&1 &

# 啟動 Web 管理介面（雲伺服器需先在 .env 中設定 WEBUI_HOST=0.0.0.0）
python main.py --webui-only

# 啟動 Web 介面（啟動時執行一次分析；需每日定時請加 --schedule 或設 SCHEDULE_ENABLED=true）
python main.py --webui
```

> 不知道怎麼訪問？→ [雲伺服器 Web 介面訪問指南](deploy-webui-cloud.md)

---

## 🔧 方案三：Systemd 服務

建立 systemd 服務檔案實現開機自啟和自動重啟：

### 1. 建立服務檔案

```bash
sudo vim /etc/systemd/system/stock-analyzer.service
```

內容：
```ini
[Unit]
Description=A股自選股智慧分析系統
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/stock-analyzer
Environment="PATH=/opt/stock-analyzer/venv/bin"
ExecStart=/opt/stock-analyzer/venv/bin/python main.py --schedule
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

### 2. 啟動服務

```bash
# 過載配置
sudo systemctl daemon-reload

# 啟動服務
sudo systemctl start stock-analyzer

# 開機自啟
sudo systemctl enable stock-analyzer

# 檢視狀態
sudo systemctl status stock-analyzer

# 檢視日誌
journalctl -u stock-analyzer -f
```

---

## ⚙️ 配置說明

### 必須配置項

| 配置項 | 說明 | 獲取方式 |
|--------|------|----------|
| `GEMINI_API_KEY` | AI 分析必需 | [Google AI Studio](https://aistudio.google.com/) |
| `STOCK_LIST` | 自選股列表 | 逗號分隔的股票程式碼 |
| `WECHAT_WEBHOOK_URL` | 微信推送 | 企業微信群機器人 |

### 可選配置項

| 配置項 | 預設值 | 說明 |
|--------|--------|------|
| `SCHEDULE_ENABLED` | `false` | 是否啟用定時任務 |
| `SCHEDULE_TIME` | `18:00` | 每日執行時間 |
| `MARKET_REVIEW_ENABLED` | `true` | 是否啟用大盤覆盤 |
| `TAVILY_API_KEYS` | - | 新聞搜尋（可選） |
| `MINIMAX_API_KEYS` | - | MiniMax 搜尋（可選） |

---

## 🌐 代理配置

如果伺服器在國內，訪問 Gemini API 需要代理：

### Docker 方式

編輯 `docker-compose.yml`：
```yaml
environment:
  - http_proxy=http://your-proxy:port
  - https_proxy=http://your-proxy:port
```

### 直接部署方式

編輯 `main.py` 頂部：
```python
os.environ["http_proxy"] = "http://your-proxy:port"
os.environ["https_proxy"] = "http://your-proxy:port"
```

---

## 📊 監控與維護

### 日誌檢視

```bash
# Docker 方式
docker-compose -f ./docker/docker-compose.yml logs -f --tail=100

# 直接部署
tail -f /opt/stock-analyzer/logs/stock_analysis_*.log
```

### 健康檢查

```bash
# 檢查程序
ps aux | grep main.py

# 檢查最近的報告
ls -la /opt/stock-analyzer/reports/
```

### 定期維護

```bash
# 清理舊日誌（保留7天）
find /opt/stock-analyzer/logs -mtime +7 -delete

# 清理舊報告（保留30天）
find /opt/stock-analyzer/reports -mtime +30 -delete
```

---

## ❓ 常見問題

### 1. Docker 構建失敗

```bash
# 清理快取重新構建
docker-compose -f ./docker/docker-compose.yml build --no-cache
```

### 2. API 訪問超時

檢查代理配置，確保伺服器能訪問 Gemini API。

### 3. 資料庫鎖定

```bash
# 停止服務後刪除 lock 檔案
rm /opt/stock-analyzer/data/*.lock
```

### 4. 記憶體不足

調整 `docker-compose.yml` 中的記憶體限制：
```yaml
deploy:
  resources:
    limits:
      memory: 1G
```

---

## 🔄 快速遷移

從一臺伺服器遷移到另一臺：

```bash
# 源伺服器：打包
cd /opt/stock-analyzer
tar -czvf stock-analyzer-backup.tar.gz .env data/ logs/ reports/

# 目標伺服器：部署
mkdir -p /opt/stock-analyzer
cd /opt/stock-analyzer
git clone <your-repo-url> .
tar -xzvf stock-analyzer-backup.tar.gz
docker-compose -f ./docker/docker-compose.yml up -d
```

---

## ☁️ 方案四：GitHub Actions 部署（免伺服器）

**最簡單的方案！** 無需伺服器，利用 GitHub 免費計算資源。

### 優勢
- ✅ **完全免費**（每月 2000 分鐘）
- ✅ **無需伺服器**
- ✅ **自動定時執行**
- ✅ **零維護成本**

### 限制
- ⚠️ 無狀態（每次執行是新環境）
- ⚠️ 定時可能有幾分鐘延遲
- ⚠️ 無法提供 HTTP API

### 部署步驟

#### 1. 建立 GitHub 倉庫

```bash
# 初始化 git（如果還沒有）
cd /path/to/daily_stock_analysis
git init
git add .
git commit -m "Initial commit"

# 建立 GitHub 倉庫並推送
# 在 GitHub 網頁上建立新倉庫後：
git remote add origin https://github.com/你的使用者名稱/daily_stock_analysis.git
git branch -M main
git push -u origin main
```

#### 2. 配置 Secrets（重要！）

開啟倉庫頁面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

新增以下 Secrets：

| Secret 名稱 | 說明 | 必填 |
|------------|------|------|
| `GEMINI_API_KEY` | Gemini AI API Key | ✅ |
| `WECHAT_WEBHOOK_URL` | 企業微信機器人 Webhook | 可選* |
| `FEISHU_WEBHOOK_URL` | 飛書機器人 Webhook | 可選* |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可選* |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選* |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID | 可選* |
| `EMAIL_SENDER` | 發件人郵箱 | 可選* |
| `EMAIL_PASSWORD` | 郵箱授權碼 | 可選* |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey | 可選* |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（多個逗號分隔） | 可選* |
| `STOCK_LIST` | 自選股列表，如 `600519,300750` | ✅ |
| `TAVILY_API_KEYS` | Tavily 搜尋 API Key | 推薦 |
| `MINIMAX_API_KEYS` | MiniMax Coding Plan Web Search | 可選 |
| `SERPAPI_API_KEYS` | SerpAPI Key | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json） | 可選 |
| `TUSHARE_TOKEN` | Tushare Token | 可選 |
| `GEMINI_MODEL` | 模型名稱（預設 gemini-2.0-flash） | 可選 |

> *注：通知渠道至少配置一個，支援多渠道同時推送

#### 3. 驗證 Workflow 檔案

確保 `.github/workflows/daily_analysis.yml` 檔案存在且已提交：

```bash
git add .github/workflows/daily_analysis.yml
git commit -m "Add GitHub Actions workflow"
git push
```

#### 4. 手動測試執行

1. 開啟倉庫頁面 → **Actions** 標籤
2. 選擇 **"每日股票分析"** workflow
3. 點選 **"Run workflow"** 按鈕
4. 選擇執行模式：
   - `full` - 完整分析（股票+大盤）
   - `market-only` - 僅大盤覆盤
   - `stocks-only` - 僅股票分析
5. 點選綠色 **"Run workflow"** 按鈕

#### 5. 檢視執行日誌

- Actions 頁面可以看到執行歷史
- 點選具體的執行記錄檢視詳細日誌
- 分析報告會作為 Artifact 儲存 30 天

### 定時說明

預設配置：**週一到週五，北京時間 18:00** 自動執行

修改時間：編輯 `.github/workflows/daily_analysis.yml` 中的 cron 表示式：

```yaml
schedule:
  - cron: '0 10 * * 1-5'  # UTC 時間，+8 = 北京時間
```

常用 cron 示例：
| 表示式 | 說明 |
|--------|------|
| `'0 10 * * 1-5'` | 週一到週五 18:00（北京時間） |
| `'30 7 * * 1-5'` | 週一到週五 15:30（北京時間） |
| `'0 10 * * *'` | 每天 18:00（北京時間） |
| `'0 2 * * 1-5'` | 週一到週五 10:00（北京時間） |

### 修改自選股

方法一：修改倉庫 Secret `STOCK_LIST`

方法二：直接修改程式碼後推送：
```bash
# 修改 .env.example 或在程式碼中設定預設值
git commit -am "Update stock list"
git push
```

### 常見問題

**Q: 為什麼定時任務沒有執行？**
A: GitHub Actions 定時任務可能有 5-15 分鐘延遲，且僅在倉庫有活動時才觸發。長時間無 commit 可能導致 workflow 被禁用。

**Q: 如何檢視歷史報告？**
A: Actions → 選擇執行記錄 → Artifacts → 下載 `analysis-reports-xxx`

**Q: 免費額度夠用嗎？**
A: 每次執行約 2-5 分鐘，一個月 22 個工作日 = 44-110 分鐘，遠低於 2000 分鐘限制。

---

## 🌐 雲伺服器上部署了，但不知道怎麼用瀏覽器訪問？

詳見 → [雲伺服器 Web 介面訪問指南](deploy-webui-cloud.md)

涵蓋：直接部署和 Docker 兩種方式的啟動與訪問、安全組/防火牆配置、常見問題排查、Nginx 反向代理（可選）。

---

**祝部署順利！🎉**

