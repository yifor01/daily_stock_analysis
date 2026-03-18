# 📖 完整配置與部署指南

本文件包含 A股智慧分析系統的完整配置說明，適合需要高階功能或特殊部署方式的使用者。

> 💡 快速上手請參考 [README.md](../README.md)，本文件為進階配置。

## 📁 專案結構

```
daily_stock_analysis/
├── main.py              # 主程式入口
├── src/                 # 核心業務邏輯
│   ├── analyzer.py      # AI 分析器
│   ├── config.py        # 配置管理
│   ├── notification.py  # 訊息推送
│   └── ...
├── data_provider/       # 多資料來源介面卡
├── bot/                 # 機器人互動模組
├── api/                 # FastAPI 後端服務
├── apps/dsa-web/        # React 前端
├── docker/              # Docker 配置
├── docs/                # 專案文件
└── .github/workflows/   # GitHub Actions
```

## 📑 目錄

- [專案結構](#專案結構)
- [GitHub Actions 詳細配置](#github-actions-詳細配置)
- [環境變數完整列表](#環境變數完整列表)
- [Docker 部署](#docker-部署)
- [本地執行詳細配置](#本地執行詳細配置)
- [定時任務配置](#定時任務配置)
- [通知渠道詳細配置](#通知渠道詳細配置)
- [資料來源配置](#資料來源配置)
- [高階功能](#高階功能)
- [回測功能](#回測功能)
- [本地 WebUI 管理介面](#本地-webui-管理介面)

---

## GitHub Actions 詳細配置

### 1. Fork 本倉庫

點選右上角 `Fork` 按鈕

### 2. 配置 Secrets

進入你 Fork 的倉庫 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

<div align="center">
  <img src="../sources/secret_config.png" alt="GitHub Secrets 配置示意圖" width="600">
</div>

#### AI 模型配置（二選一）

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) 獲取免費 Key | ✅* |
| `OPENAI_API_KEY` | OpenAI 相容 API Key（支援 DeepSeek、通義千問等） | 可選 |
| `OPENAI_BASE_URL` | OpenAI 相容 API 地址（如 `https://api.deepseek.com/v1`） | 可選 |
| `OPENAI_MODEL` | 模型名稱（如 `gemini-3.1-pro-preview`、`deepseek-chat`、`gpt-5.2`） | 可選 |

> *注：`GEMINI_API_KEY` 和 `OPENAI_API_KEY` 至少配置一個

#### 通知渠道配置（可同時配置多個，全部推送）

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書 Webhook URL | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 獲取） | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID (用於傳送到子話題) | 可選 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL（[建立方法](https://support.discord.com/hc/en-us/articles/228383668)） | 可選 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token（與 Webhook 二選一） | 可選 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID（使用 Bot 時需要） | 可選 |
| `EMAIL_SENDER` | 發件人郵箱（如 `xxx@qq.com`） | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登入密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（多個用逗號分隔，留空則發給自己） | 可選 |
| `EMAIL_SENDER_NAME` | 發件人顯示名稱（預設：daily_stock_analysis股票分析助手） | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（[獲取地址](https://www.pushplus.plus)，國內推送服務） | 可選 |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey（[獲取地址](https://sc3.ft07.com/)，手機APP推送服務） | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（支援釘釘等，多個用逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook 的 Bearer Token（用於需要認證的 Webhook） | 可選 |
| `WEBHOOK_VERIFY_SSL` | Webhook HTTPS 證書校驗（預設 true）。設為 false 可支援自簽名證書。警告：關閉有嚴重安全風險（MITM），僅限可信內網 | 可選 |

> *注：至少配置一個渠道，配置多個則同時推送

#### 推送行為配置

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `SINGLE_STOCK_NOTIFY` | 單股推送模式：設為 `true` 則每分析完一隻股票立即推送 | 可選 |
| `REPORT_TYPE` | 報告型別：`simple`(精簡)、`full`(完整)、`brief`(3-5句概括)，Docker環境推薦設為 `full` | 可選 |
| `REPORT_SUMMARY_ONLY` | 僅分析結果摘要：設為 `true` 時只推送彙總，不含個股詳情；多股時適合快速瀏覽（預設 false，Issue #262） | 可選 |
| `REPORT_TEMPLATES_DIR` | Jinja2 模板目錄（相對專案根，預設 `templates`） | 可選 |
| `REPORT_RENDERER_ENABLED` | 啟用 Jinja2 模板渲染（預設 `false`，保證零迴歸） | 可選 |
| `REPORT_INTEGRITY_ENABLED` | 啟用報告完整性校驗，缺失必填欄位時重試或佔位補全（預設 `true`） | 可選 |
| `REPORT_INTEGRITY_RETRY` | 完整性校驗重試次數（預設 `1`，`0` 表示僅佔位不重試） | 可選 |
| `REPORT_HISTORY_COMPARE_N` | 歷史訊號對比條數，`0` 關閉（預設），`>0` 啟用 | 可選 |
| `ANALYSIS_DELAY` | 個股分析和大盤分析之間的延遲（秒），避免API限流，如 `10` | 可選 |
| `MERGE_EMAIL_NOTIFICATION` | 個股與大盤覆盤合併推送（預設 false），減少郵件數量、降低垃圾郵件風險；與 `SINGLE_STOCK_NOTIFY` 互斥（單股模式下合併不生效） | 可選 |
| `MARKDOWN_TO_IMAGE_CHANNELS` | 將 Markdown 轉為圖片傳送的渠道（用逗號分隔）：telegram,wechat,custom,email；單股推送需同時配置且安裝轉圖工具 | 可選 |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | 超過此長度不轉圖片，避免超大圖片（預設 15000） | 可選 |
| `MD2IMG_ENGINE` | 轉圖引擎：`wkhtmltoimage`（預設，需 wkhtmltopdf）或 `markdown-to-file`（emoji 更好，需 `npm i -g markdown-to-file`） | 可選 |
| `PREFETCH_REALTIME_QUOTES` | 設為 `false` 可禁用實時行情預取，避免 efinance/akshare_em 全市場拉取（預設 true） | 可選 |

#### 其他配置

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `STOCK_LIST` | 自選股程式碼，如 `600519,300750,002594` | ✅ |
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 搜尋 API（新聞搜尋） | 推薦 |
| `MINIMAX_API_KEYS` | [MiniMax](https://platform.minimaxi.com/) Coding Plan Web Search（結構化搜尋結果） | 可選 |
| `BOCHA_API_KEYS` | [博查搜尋](https://open.bocha.cn/) Web Search API（中文搜尋最佳化，支援AI摘要，多個key用逗號分隔） | 可選 |
| `BRAVE_API_KEYS` | [Brave Search](https://brave.com/search/api/) API（隱私優先，美股最佳化，多個key用逗號分隔） | 可選 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis) 備用搜尋 | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json） | 可選 |
| `TUSHARE_TOKEN` | [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) Token | 可選 |
| `ENABLE_CHIP_DISTRIBUTION` | 啟用籌碼分佈（Actions 預設 false；需籌碼資料時在 Variables 中設為 true，介面可能不穩定） | 可選 |

#### ✅ 最小配置示例

如果你想快速開始，最少需要配置以下項：

1. **AI 模型**：`AIHUBMIX_KEY`（[AIHubmix](https://aihubmix.com/?aff=CfMq)，一 Key 多模型）、`GEMINI_API_KEY` 或 `OPENAI_API_KEY`
2. **通知渠道**：至少配置一個，如 `WECHAT_WEBHOOK_URL` 或 `EMAIL_SENDER` + `EMAIL_PASSWORD`
3. **股票列表**：`STOCK_LIST`（必填）
4. **搜尋 API**：`TAVILY_API_KEYS`（強烈推薦，用於新聞搜尋）

> 💡 配置完以上 4 項即可開始使用！

### 3. 啟用 Actions

1. 進入你 Fork 的倉庫
2. 點選頂部的 `Actions` 標籤
3. 如果看到提示，點選 `I understand my workflows, go ahead and enable them`

### 4. 手動測試

1. 進入 `Actions` 標籤
2. 左側選擇 `每日股票分析` workflow
3. 點選右側的 `Run workflow` 按鈕
4. 選擇執行模式
5. 點選綠色的 `Run workflow` 確認

### 5. 完成！

預設每個工作日 **18:00（北京時間）** 自動執行。

---

## 環境變數完整列表

### AI 模型配置

> 完整說明見 [LLM 配置指南](LLM_CONFIG_GUIDE.md)（三層配置、渠道模式、Vision、Agent、排錯）。

| 變數名 | 說明 | 預設值 | 必填 |
|--------|------|--------|:----:|
| `LITELLM_MODEL` | 主模型，格式 `provider/model`（如 `gemini/gemini-2.5-flash`），推薦優先使用 | - | 否 |
| `LITELLM_FALLBACK_MODELS` | 備選模型，逗號分隔 | - | 否 |
| `LLM_CHANNELS` | 渠道名稱列表（逗號分隔），配合 `LLM_{NAME}_*` 使用，詳見 [LLM 配置指南](LLM_CONFIG_GUIDE.md) | - | 否 |
| `LITELLM_CONFIG` | LiteLLM YAML 配置檔案路徑（高階） | - | 否 |
| `AIHUBMIX_KEY` | [AIHubmix](https://aihubmix.com/?aff=CfMq) API Key，一 Key 切換使用全系模型，無需額外配置 Base URL | - | 可選 |
| `GEMINI_API_KEY` | Google Gemini API Key | - | 可選 |
| `GEMINI_MODEL` | 主模型名稱（legacy，`LITELLM_MODEL` 優先） | `gemini-3-flash-preview` | 否 |
| `GEMINI_MODEL_FALLBACK` | 備選模型（legacy） | `gemini-2.5-flash` | 否 |
| `OPENAI_API_KEY` | OpenAI 相容 API Key | - | 可選 |
| `OPENAI_BASE_URL` | OpenAI 相容 API 地址 | - | 可選 |
| `OPENAI_MODEL` | OpenAI 模型名稱（legacy，AIHubmix 使用者可填如 `gemini-3.1-pro-preview`、`gpt-5.2`） | `gpt-5.2` | 可選 |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | - | 可選 |
| `ANTHROPIC_MODEL` | Claude 模型名稱 | `claude-3-5-sonnet-20241022` | 可選 |
| `ANTHROPIC_TEMPERATURE` | Claude 溫度引數（0.0-1.0） | `0.7` | 可選 |
| `ANTHROPIC_MAX_TOKENS` | Claude 響應最大 token 數 | `8192` | 可選 |

> *注：`AIHUBMIX_KEY`、`GEMINI_API_KEY`、`ANTHROPIC_API_KEY` 和 `OPENAI_API_KEY` 至少配置一個。`AIHUBMIX_KEY` 無需配置 `OPENAI_BASE_URL`，系統自動適配。

### 通知渠道配置

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信機器人 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書機器人 Webhook URL | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID | 可選 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | 可選 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token（與 Webhook 二選一） | 可選 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID（使用 Bot 時需要） | 可選 |
| `DISCORD_MAX_WORDS` | Discord 最大字數限制（預設 免費伺服器限制2000） | 可選 |
| `EMAIL_SENDER` | 發件人郵箱 | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登入密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（逗號分隔，留空發給自己） | 可選 |
| `EMAIL_SENDER_NAME` | 發件人顯示名稱 | 可選 |
| `STOCK_GROUP_N` / `EMAIL_GROUP_N` | 股票分組發往不同郵箱（Issue #268），如 `STOCK_GROUP_1=600519,300750` 與 `EMAIL_GROUP_1=user1@example.com` 配對 | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook Bearer Token | 可選 |
| `WEBHOOK_VERIFY_SSL` | Webhook HTTPS 證書校驗（預設 true）。設為 false 可支援自簽名。警告：關閉有嚴重安全風險 | 可選 |
| `PUSHOVER_USER_KEY` | Pushover 使用者 Key | 可選 |
| `PUSHOVER_API_TOKEN` | Pushover API Token | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（國內推送服務） | 可選 |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey | 可選 |

#### 飛書雲文件配置（可選，解決訊息截斷問題）

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `FEISHU_APP_ID` | 飛書應用 ID | 可選 |
| `FEISHU_APP_SECRET` | 飛書應用 Secret | 可選 |
| `FEISHU_FOLDER_TOKEN` | 飛書雲盤資料夾 Token | 可選 |

> 飛書雲文件配置步驟：
> 1. 在 [飛書開發者後臺](https://open.feishu.cn/app) 建立應用
> 2. 配置 GitHub Secrets
> 3. 建立群組並新增應用機器人
> 4. 在雲盤資料夾中新增群組為協作者（可管理許可權）

### 搜尋服務配置

| 變數名 | 說明 | 必填 |
|--------|------|:----:|
| `TAVILY_API_KEYS` | Tavily 搜尋 API Key（推薦） | 推薦 |
| `MINIMAX_API_KEYS` | MiniMax Coding Plan Web Search（結構化搜尋結果） | 可選 |
| `BOCHA_API_KEYS` | 博查搜尋 API Key（中文最佳化） | 可選 |
| `BRAVE_API_KEYS` | Brave Search API Key（美股最佳化） | 可選 |
| `SERPAPI_API_KEYS` | SerpAPI 備用搜尋 | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json） | 可選 |
| `NEWS_STRATEGY_PROFILE` | 新聞策略視窗檔位：`ultra_short`(1天)/`short`(3天)/`medium`(7天)/`long`(30天)；實際視窗取與 `NEWS_MAX_AGE_DAYS` 的最小值 | 預設 `short` |
| `NEWS_MAX_AGE_DAYS` | 新聞最大時效（天），搜尋時限制結果在近期內 | 預設 `3` |
| `BIAS_THRESHOLD` | 乖離率閾值（%），超過提示不追高；強勢趨勢股自動放寬到 1.5 倍 | 預設 `5.0` |

### 資料來源配置

| 變數名 | 說明 | 預設值 | 必填 |
|--------|------|--------|:----:|
| `TUSHARE_TOKEN` | Tushare Pro Token | - | 可選 |
| `ENABLE_REALTIME_QUOTE` | 啟用實時行情（關閉後使用歷史收盤價分析） | `true` | 可選 |
| `ENABLE_REALTIME_TECHNICAL_INDICATORS` | 盤中實時技術面：啟用時用實時價計算 MA5/MA10/MA20 與多頭排列（Issue #234）；關閉則用昨日收盤 | `true` | 可選 |
| `ENABLE_CHIP_DISTRIBUTION` | 啟用籌碼分佈分析（該介面不穩定，雲端部署建議關閉）。GitHub Actions 使用者需在 Repository Variables 中設定 `ENABLE_CHIP_DISTRIBUTION=true` 方可啟用；workflow 預設關閉。 | `true` | 可選 |
| `ENABLE_EASTMONEY_PATCH` | 東財介面補丁：東財介面頻繁失敗（如 RemoteDisconnected、連線被關閉）時建議設為 `true`，注入 NID 令牌與隨機 User-Agent 以降低被限流機率 | `false` | 可選 |
| `REALTIME_SOURCE_PRIORITY` | 實時行情資料來源優先順序（逗號分隔），如 `tencent,akshare_sina,efinance,akshare_em` | 見 .env.example | 可選 |
| `ENABLE_FUNDAMENTAL_PIPELINE` | 基本面聚合總開關；關閉時僅返回 `not_supported` 塊，不改變原分析鏈路 | `true` | 可選 |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | 基本面階段總時延預算（秒） | `1.5` | 可選 |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | 單能力源呼叫超時（秒） | `0.8` | 可選 |
| `FUNDAMENTAL_RETRY_MAX` | 基本面能力重試次數（含首次） | `1` | 可選 |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | 基本面聚合快取 TTL（秒），短快取減輕重複拉取 | `120` | 可選 |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | 基本面快取最大條目數（TTL 內按時間淘汰） | `256` | 可選 |

> 行為說明：
> - A 股：按 `valuation/growth/earnings/institution/capital_flow/dragon_tiger/boards` 聚合能力返回；
> - ETF：返回可得項，缺失能力標記為 `not_supported`，整體不影響原流程；
> - 美股/港股：返回 `not_supported` 兜底塊；
> - 任何異常走 fail-open，僅記錄錯誤，不影響技術面/新聞/籌碼主鏈路。
> - 欄位契約：
>   - `fundamental_context.boards.data` = `sector_rankings`（板塊漲跌榜，結構 `{top, bottom}`）；
>   - `fundamental_context.earnings.data.financial_report` = 財報摘要（報告期、營收、歸母淨利潤、經營現金流、ROE）；
>   - `fundamental_context.earnings.data.dividend` = 分紅指標（僅現金分紅稅前口徑，含 `events`、`ttm_cash_dividend_per_share`、`ttm_dividend_yield_pct`）；
>   - `get_stock_info.belong_boards` = 個股所屬板塊列表；
>   - `get_stock_info.boards` 為相容別名，值與 `belong_boards` 相同（未來僅在大版本考慮移除）；
>   - `get_stock_info.sector_rankings` 與 `fundamental_context.boards.data` 保持一致。
> - 板塊漲跌榜使用資料來源順序：與全域性 priority 一致。
> - 超時控制為 `best-effort` 軟超時：階段會按預算快速降級繼續執行，但不保證硬中斷底層三方呼叫。
> - `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS=1.5` 表示新增基本面階段的目標預算，不是嚴格硬 SLA。
> - 若要硬 SLA，請在後續版本升級為子程序隔離執行並在超時後強制終止。

### 其他配置

| 變數名 | 說明 | 預設值 |
|--------|------|--------|
| `STOCK_LIST` | 自選股程式碼（逗號分隔） | - |
| `ADMIN_AUTH_ENABLED` | Web 登入：設為 `true` 啟用密碼保護；首次訪問在網頁設定初始密碼，可在「系統設定 > 修改密碼」修改；忘記密碼執行 `python -m src.auth reset_password` | `false` |
| `TRUST_X_FORWARDED_FOR` | 反向代理部署時設為 `true`，從 `X-Forwarded-For` 獲取真實 IP（限流等）；直連公網時保持 `false` 防偽造 | `false` |
| `MAX_WORKERS` | 併發執行緒數 | `3` |
| `MARKET_REVIEW_ENABLED` | 啟用大盤覆盤 | `true` |
| `MARKET_REVIEW_REGION` | 大盤覆盤市場區域：cn(A股)、us(美股)、both(兩者)，us 適合僅關注美股的使用者 | `cn` |
| `TRADING_DAY_CHECK_ENABLED` | 交易日檢查：預設 `true`，非交易日跳過執行；設為 `false` 或使用 `--force-run` 可強制執行（Issue #373） | `true` |
| `SCHEDULE_ENABLED` | 啟用定時任務 | `false` |
| `SCHEDULE_TIME` | 定時執行時間 | `18:00` |
| `LOG_DIR` | 日誌目錄 | `./logs` |

---

## Docker 部署

Dockerfile 使用多階段構建，前端會在構建映象時自動打包並內建到 `static/`。
如需覆蓋靜態資源，可掛載本地 `static/` 到容器內 `/app/static`。

### 快速啟動

```bash
# 1. 克隆倉庫
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 2. 配置環境變數
cp .env.example .env
vim .env  # 填入 API Key 和配置

# 3. 啟動容器
docker-compose -f ./docker/docker-compose.yml up -d server     # Web 服務模式（推薦，提供 API 與 WebUI）
docker-compose -f ./docker/docker-compose.yml up -d analyzer   # 定時任務模式
docker-compose -f ./docker/docker-compose.yml up -d            # 同時啟動兩種模式

# 4. 訪問 WebUI
# http://localhost:8000

# 5. 檢視日誌
docker-compose -f ./docker/docker-compose.yml logs -f server
```

### 執行模式說明

| 命令 | 說明 | 埠 |
|------|------|------|
| `docker-compose -f ./docker/docker-compose.yml up -d server` | Web 服務模式，提供 API 與 WebUI | 8000 |
| `docker-compose -f ./docker/docker-compose.yml up -d analyzer` | 定時任務模式，每日自動執行 | - |
| `docker-compose -f ./docker/docker-compose.yml up -d` | 同時啟動兩種模式 | 8000 |

### Docker Compose 配置

`docker-compose.yml` 使用 YAML 錨點複用配置：

```yaml
version: '3.8'

x-common: &common
  build:
    context: ..
    dockerfile: docker/Dockerfile
  restart: unless-stopped
  env_file:
    - ../.env
  environment:
    - TZ=Asia/Shanghai
  volumes:
    - ../data:/app/data
    - ../logs:/app/logs
    - ../reports:/app/reports
    - ../.env:/app/.env

services:
  # 定時任務模式
  analyzer:
    <<: *common
    container_name: stock-analyzer

  # FastAPI 模式
  server:
    <<: *common
    container_name: stock-server
    command: ["python", "main.py", "--serve-only", "--host", "0.0.0.0", "--port", "8000"]
    ports:
      - "8000:8000"
```

### 常用命令

```bash
# 檢視執行狀態
docker-compose -f ./docker/docker-compose.yml ps

# 檢視日誌
docker-compose -f ./docker/docker-compose.yml logs -f server

# 停止服務
docker-compose -f ./docker/docker-compose.yml down

# 重建映象（程式碼更新後）
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d server
```

### 手動構建映象

```bash
docker build -f docker/Dockerfile -t stock-analysis .
docker run -d --env-file .env -p 8000:8000 -v ./data:/app/data stock-analysis python main.py --serve-only --host 0.0.0.0 --port 8000
```

---

## 本地執行詳細配置

### 安裝依賴

```bash
# Python 3.10+ 推薦
pip install -r requirements.txt

# 或使用 conda
conda create -n stock python=3.10
conda activate stock
pip install -r requirements.txt
```

**智慧匯入依賴**：`pypinyin`（名稱→程式碼拼音匹配）和 `openpyxl`（Excel .xlsx 解析）已包含在 `requirements.txt` 中，執行上述 `pip install -r requirements.txt` 時會自動安裝。若使用智慧匯入（圖片/CSV/Excel/剪貼簿）功能，請確保依賴已正確安裝；缺失時可能報 `ModuleNotFoundError`。

### 命令列引數

```bash
python main.py                        # 完整分析（個股 + 大盤覆盤）
python main.py --market-review        # 僅大盤覆盤
python main.py --no-market-review     # 僅個股分析
python main.py --stocks 600519,300750 # 指定股票
python main.py --dry-run              # 僅獲取資料，不 AI 分析
python main.py --no-notify            # 不傳送推送
python main.py --schedule             # 定時任務模式
python main.py --force-run            # 非交易日也強制執行（Issue #373）
python main.py --debug                # 除錯模式（詳細日誌）
python main.py --workers 5            # 指定併發數
```

---

## 定時任務配置

### GitHub Actions 定時

編輯 `.github/workflows/daily_analysis.yml`:

```yaml
schedule:
  # UTC 時間，北京時間 = UTC + 8
  - cron: '0 10 * * 1-5'   # 週一到週五 18:00（北京時間）
```

常用時間對照：

| 北京時間 | UTC cron 表示式 |
|---------|----------------|
| 09:30 | `'30 1 * * 1-5'` |
| 12:00 | `'0 4 * * 1-5'` |
| 15:00 | `'0 7 * * 1-5'` |
| 18:00 | `'0 10 * * 1-5'` |
| 21:00 | `'0 13 * * 1-5'` |

#### GitHub Actions 非交易日手動執行（Issue #461 / #466）

`daily_analysis.yml` 支援兩種控制方式：

- `TRADING_DAY_CHECK_ENABLED`：倉庫級配置（`Settings → Secrets and variables → Actions`），預設 `true`
- `workflow_dispatch.force_run`：手動觸發時的單次開關，預設 `false`

推薦優先順序理解：

| 配置組合 | 非交易日行為 |
|---------|-------------|
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=false` | 跳過執行（預設行為） |
| `TRADING_DAY_CHECK_ENABLED=true` + `force_run=true` | 本次強制執行 |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=false` | 始終執行（定時和手動都不檢查交易日） |
| `TRADING_DAY_CHECK_ENABLED=false` + `force_run=true` | 始終執行 |

手動觸發步驟：

1. 開啟 `Actions → 每日股票分析 → Run workflow`
2. 選擇 `mode`（`full` / `market-only` / `stocks-only`）
3. 若當天是非交易日且希望仍執行，將 `force_run` 設為 `true`
4. 點選 `Run workflow`

### 本地定時任務

內建的定時任務排程器支援每天在指定時間（預設 18:00）執行分析。

#### 命令列方式

```bash
# 啟動定時模式（啟動時立即執行一次，隨後每天 18:00 執行）
python main.py --schedule

# 啟動定時模式（啟動時不執行，僅等待下次定時觸發）
python main.py --schedule --no-run-immediately
```

#### 環境變數方式

你也可以透過環境變數配置定時行為（適用於 Docker 或 .env）：

| 變數名 | 說明 | 預設值 | 示例 |
|--------|------|:-------:|:-----:|
| `SCHEDULE_ENABLED` | 是否啟用定時任務 | `false` | `true` |
| `SCHEDULE_TIME` | 每日執行時間 (HH:MM) | `18:00` | `09:30` |
| `SCHEDULE_RUN_IMMEDIATELY` | 啟動服務時是否立即執行一次 | `true` | `false` |
| `TRADING_DAY_CHECK_ENABLED` | 交易日檢查：非交易日跳過執行；設為 `false` 可強制執行 | `true` | `false` |

例如在 Docker 中配置：

```bash
# 設定啟動時不立即分析
docker run -e SCHEDULE_ENABLED=true -e SCHEDULE_RUN_IMMEDIATELY=false ...
```

#### 交易日判斷（Issue #373）

預設根據自選股市場（A 股 / 港股 / 美股）和 `MARKET_REVIEW_REGION` 判斷是否為交易日：
- 使用 `exchange-calendars` 區分 A 股 / 港股 / 美股各自的交易日曆（含節假日）
- 混合持倉時，每隻股票只在其市場開市日分析，休市股票當日跳過
- 全部相關市場均為非交易日時，整體跳過執行（不啟動 pipeline、不發推送）
- 覆蓋方式：`TRADING_DAY_CHECK_ENABLED=false` 或 命令列 `--force-run`

#### 使用 Crontab

如果不想使用常駐程序，也可以使用系統的 Cron：

```bash
crontab -e
# 新增：0 18 * * 1-5 cd /path/to/project && python main.py
```

---

## 通知渠道詳細配置

### 企業微信

1. 在企業微信群聊中新增"群機器人"
2. 複製 Webhook URL
3. 設定 `WECHAT_WEBHOOK_URL`

### 飛書

1. 在飛書群聊中新增"自定義機器人"
2. 複製 Webhook URL
3. 設定 `FEISHU_WEBHOOK_URL`

### Telegram

1. 與 @BotFather 對話建立 Bot
2. 獲取 Bot Token
3. 獲取 Chat ID（可透過 @userinfobot）
4. 設定 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`
5. (可選) 如需傳送到 Topic，設定 `TELEGRAM_MESSAGE_THREAD_ID` (從 Topic 連結末尾獲取)

### 郵件

1. 開啟郵箱的 SMTP 服務
2. 獲取授權碼（非登入密碼）
3. 設定 `EMAIL_SENDER`、`EMAIL_PASSWORD`、`EMAIL_RECEIVERS`

支援的郵箱：
- QQ 郵箱：smtp.qq.com:465
- 163 郵箱：smtp.163.com:465
- Gmail：smtp.gmail.com:587

**股票分組發往不同郵箱**（Issue #268，可選）：
配置 `STOCK_GROUP_N` 與 `EMAIL_GROUP_N` 可實現不同股票組的報告傳送到不同郵箱，例如多人共享分析時互不干擾。大盤覆盤會發往所有配置的郵箱。

```bash
STOCK_GROUP_1=600519,300750
EMAIL_GROUP_1=user1@example.com
STOCK_GROUP_2=002594,AAPL
EMAIL_GROUP_2=user2@example.com
```

### 自定義 Webhook

支援任意 POST JSON 的 Webhook，包括：
- 釘釘機器人
- Discord Webhook
- Slack Webhook
- Bark（iOS 推送）
- 自建服務

設定 `CUSTOM_WEBHOOK_URLS`，多個用逗號分隔。

### Discord

Discord 支援兩種方式推送：

**方式一：Webhook（推薦，簡單）**

1. 在 Discord 頻道設定中建立 Webhook
2. 複製 Webhook URL
3. 配置環境變數：

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
```

**方式二：Bot API（需要更多許可權）**

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 建立應用
2. 建立 Bot 並獲取 Token
3. 邀請 Bot 到伺服器
4. 獲取頻道 ID（開發者模式下右鍵頻道複製）
5. 配置環境變數：

```bash
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_MAIN_CHANNEL_ID=your_channel_id
```

### Pushover（iOS/Android 推送）

[Pushover](https://pushover.net/) 是一個跨平臺的推送服務，支援 iOS 和 Android。

1. 註冊 Pushover 賬號並下載 App
2. 在 [Pushover Dashboard](https://pushover.net/) 獲取 User Key
3. 建立 Application 獲取 API Token
4. 配置環境變數：

```bash
PUSHOVER_USER_KEY=your_user_key
PUSHOVER_API_TOKEN=your_api_token
```

特點：
- 支援 iOS/Android 雙平臺
- 支援通知優先順序和聲音設定
- 免費額度足夠個人使用（每月 10,000 條）
- 訊息可保留 7 天

### Markdown 轉圖片（可選）

配置 `MARKDOWN_TO_IMAGE_CHANNELS` 可將報告以圖片形式傳送至不支援 Markdown 的渠道（telegram, wechat, custom, email）。

**依賴安裝**：

1. **imgkit**：已包含在 `requirements.txt`，執行 `pip install -r requirements.txt` 時會自動安裝
2. **wkhtmltopdf**（預設引擎）：系統級依賴，需手動安裝：
   - **macOS**：`brew install wkhtmltopdf`
   - **Debian/Ubuntu**：`apt install wkhtmltopdf`
3. **markdown-to-file**（可選，emoji 支援更好）：`npm i -g markdown-to-file`，並設定 `MD2IMG_ENGINE=markdown-to-file`

未安裝或安裝失敗時，將自動回退為 Markdown 文字傳送。

**單股推送 + 圖片傳送**（Issue #455）：

單股推送模式（`SINGLE_STOCK_NOTIFY=true`）下，若希望 Telegram 等渠道以圖片形式推送，需同時配置 `MARKDOWN_TO_IMAGE_CHANNELS=telegram` 並安裝轉圖工具（wkhtmltopdf 或 markdown-to-file）。個股日報彙總同樣支援轉圖，無需額外配置。

**故障排查**：若日誌出現「Markdown 轉圖片失敗，將回退為文字傳送」，請檢查 `MARKDOWN_TO_IMAGE_CHANNELS` 配置及轉圖工具是否已正確安裝（`which wkhtmltoimage` 或 `which m2f`）。

---

## 資料來源配置

系統預設使用 AkShare（免費），也支援其他資料來源：

### AkShare（預設）
- 免費，無需配置
- 資料來源：東方財富爬蟲

### Tushare Pro
- 需要註冊獲取 Token
- 更穩定，資料更全
- 設定 `TUSHARE_TOKEN`

### Baostock
- 免費，無需配置
- 作為備用資料來源

### YFinance
- 免費，無需配置
- 支援美股/港股資料
- 美股歷史資料與實時行情均統一使用 YFinance，以避免 akshare 美股復權異常導致的技術指標錯誤

### 東財介面頻繁失敗時的處理

若日誌出現 `RemoteDisconnected`、`push2his.eastmoney.com` 連線被關閉等，多為東財限流。建議：

1. 在 `.env` 中設定 `ENABLE_EASTMONEY_PATCH=true`
2. 將 `MAX_WORKERS=1` 降低併發
3. 若已配置 Tushare，可優先使用 Tushare 資料來源

---

## 高階功能

### 港股支援

使用 `hk` 字首指定港股程式碼：

```bash
STOCK_LIST=600519,hk00700,hk01810
```

### ETF 與指數分析

針對指數跟蹤型 ETF 和美股指數（如 VOO、QQQ、SPY、510050、SPX、DJI、IXIC），分析僅關注**指數走勢、跟蹤誤差、市場流動性**，不納入基金管理人/發行方的公司層面風險（訴訟、聲譽、高管變動等）。風險警報與業績預期均基於指數成分股整體表現，避免將基金公司新聞誤判為標的本身利空。詳見 Issue #274。

### 多模型切換

配置多個模型，系統自動切換：

```bash
# Gemini（主力）
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-3-flash-preview

# OpenAI 相容（備選）
OPENAI_API_KEY=xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
# 思考模式：deepseek-reasoner、deepseek-r1、qwq 等自動識別；deepseek-chat 系統按模型名自動啟用
```

### LiteLLM 直接整合（多模型 + 多 Key 負載均衡）

詳見 [LLM 配置指南](LLM_CONFIG_GUIDE.md)。本專案透過 [LiteLLM](https://github.com/BerriAI/litellm) 統一呼叫所有 LLM，無需單獨啟動 Proxy 服務。

**兩層機制**：同一模型多 Key 輪換（Router）與跨模型降級（Fallback）分層獨立，互不干擾。

**多 Key + 跨模型降級配置示例**：

```env
# 主模型：3 個 Gemini Key 輪換，任一 429 時 Router 自動切換下一個 Key
GEMINI_API_KEYS=key1,key2,key3
LITELLM_MODEL=gemini/gemini-3-flash-preview

# 跨模型降級：主模型全部 Key 均失敗時，按序嘗試 Claude → GPT
# 需配置對應 API Key：ANTHROPIC_API_KEY、OPENAI_API_KEY
LITELLM_FALLBACK_MODELS=anthropic/claude-3-5-sonnet-20241022,openai/gpt-4o-mini
```

**預期行為**：首次請求用 `key1`；若 429，Router 下次用 `key2`；若 3 個 Key 均不可用，則切換到 Claude，再失敗則切換到 GPT。

> ⚠️ `LITELLM_MODEL` 必須包含 provider 字首（如 `gemini/`、`anthropic/`、`openai/`），
> 否則系統無法識別應使用哪組 API Key。舊格式的 `GEMINI_MODEL`（無字首）僅用於未配置 `LITELLM_MODEL` 時的自動推斷。

**依賴說明**：`requirements.txt` 中保留 `openai>=1.0.0`，因 LiteLLM 內部依賴 OpenAI SDK 作為統一介面；顯式保留可確保版本相容性，使用者無需單獨配置。

**視覺模型（圖片提取股票程式碼）**：詳見 [LLM 配置指南 - Vision](LLM_CONFIG_GUIDE.md#41-vision-模型圖片識別股票程式碼)。

從圖片提取股票程式碼（如 `/api/v1/stocks/extract-from-image`）使用 LiteLLM Vision，採用 OpenAI `image_url` 格式，支援 Gemini、Claude、OpenAI、DeepSeek 等 Vision-capable 模型。返回 `items`（code、name、confidence）及相容的 `codes` 陣列。

> 相容性說明：`/api/v1/stocks/extract-from-image` 響應在原 `codes` 基礎上新增 `items` 欄位。若下游客戶端使用嚴格 JSON Schema 且不接受未知欄位，請同步更新 schema。

**智慧匯入**：除圖片外，還支援 CSV/Excel 檔案及剪貼簿貼上（`/api/v1/stocks/parse-import`），自動解析程式碼/名稱列，名稱→程式碼解析支援本地對映、拼音匹配及 AkShare 線上 fallback。依賴 `pypinyin`（拼音匹配）和 `openpyxl`（Excel 解析），已包含在 `requirements.txt` 中。

- **AkShare 名稱解析快取**：名稱→程式碼解析使用 AkShare 線上 fallback 時，結果快取 1 小時（TTL），避免頻繁請求；首次呼叫或快取過期後會自動重新整理。
- **CSV/Excel 列名**：支援 `code`、`股票程式碼`、`程式碼`、`name`、`股票名稱`、`名稱` 等（不區分大小寫）；無表頭時預設第 1 列為程式碼、第 2 列為名稱。
- **常見解析失敗**：檔案過大（>2MB）、編碼非 UTF-8/GBK、Excel 工作表為空或損壞、CSV 分隔符/列數不一致時，API 會返回具體錯誤提示。

- **模型優先順序**：`VISION_MODEL` > `LITELLM_MODEL` > 根據已有 API Key 推斷（`OPENAI_VISION_MODEL` 已廢棄，請改用 `VISION_MODEL`）
- **Provider 回退**：主模型失敗時，按 `VISION_PROVIDER_PRIORITY`（預設 `gemini,anthropic,openai`）自動切換到下一個可用 provider
- **主模型不支援 Vision 時**：若主模型為 DeepSeek 等非 Vision 模型，可顯式配置 `VISION_MODEL=openai/gpt-4o` 或 `gemini/gemini-2.0-flash` 供圖片提取使用
- **配置校驗**：若配置了 `VISION_MODEL` 但未配置對應 provider 的 API Key，啟動時會輸出 warning，圖片提取功能將不可用

### 除錯模式

```bash
python main.py --debug
```

日誌檔案位置：
- 常規日誌：`logs/stock_analysis_YYYYMMDD.log`
- 除錯日誌：`logs/stock_analysis_debug_YYYYMMDD.log`

---

## 回測功能

回測模組自動對歷史 AI 分析記錄進行事後驗證，評估分析建議的準確性。

### 工作原理

1. 選取已過冷卻期（預設 14 天）的 `AnalysisHistory` 記錄
2. 獲取分析日之後的日線資料（前向 K 線）
3. 根據操作建議推斷預期方向，與實際走勢對比
4. 評估止盈/止損命中情況，模擬執行收益
5. 彙總為整體和單股兩個維度的表現指標

### 操作建議對映

| 操作建議 | 倉位推斷 | 預期方向 | 勝利條件 |
|---------|---------|---------|---------|
| 買入/加倉/strong buy | long | up | 漲幅 ≥ 中性帶 |
| 賣出/減倉/strong sell | cash | down | 跌幅 ≥ 中性帶 |
| 持有/hold | long | not_down | 未顯著下跌 |
| 觀望/等待/wait | cash | flat | 價格在中性帶內 |

### 配置

在 `.env` 中設定以下變數（均有預設值，可選）：

| 變數 | 預設值 | 說明 |
|------|-------|------|
| `BACKTEST_ENABLED` | `true` | 是否在每日分析後自動執行回測 |
| `BACKTEST_EVAL_WINDOW_DAYS` | `10` | 評估視窗（交易日數） |
| `BACKTEST_MIN_AGE_DAYS` | `14` | 僅回測 N 天前的記錄，避免資料不完整 |
| `BACKTEST_ENGINE_VERSION` | `v1` | 引擎版本號，升級邏輯時用於區分結果 |
| `BACKTEST_NEUTRAL_BAND_PCT` | `2.0` | 中性區間閾值（%），±2% 內視為震盪 |

### 自動執行

回測在每日分析流程完成後自動觸發（非阻塞，失敗不影響通知推送）。也可透過 API 手動觸發。

### 評估指標

| 指標 | 說明 |
|------|------|
| `direction_accuracy_pct` | 方向預測準確率（預期方向與實際一致） |
| `win_rate_pct` | 勝率（勝 / (勝+負)，不含中性） |
| `avg_stock_return_pct` | 平均股票收益率 |
| `avg_simulated_return_pct` | 平均模擬執行收益率（含止盈止損退出） |
| `stop_loss_trigger_rate` | 止損觸發率（僅統計配置了止損的記錄） |
| `take_profit_trigger_rate` | 止盈觸發率（僅統計配置了止盈的記錄） |

---

## FastAPI API 服務

FastAPI 提供 RESTful API 服務，支援配置管理和觸發分析。

### 啟動方式

| 命令 | 說明 |
|------|------|
| `python main.py --serve` | 啟動 API 服務 + 執行一次完整分析 |
| `python main.py --serve-only` | 僅啟動 API 服務，手動觸發分析 |

### 功能特性

- 📝 **配置管理** - 檢視/修改自選股列表
- 🚀 **快速分析** - 透過 API 介面觸發分析
- 📊 **實時進度** - 分析任務狀態實時更新，支援多工並行
- 📈 **回測驗證** - 評估歷史分析準確率，查詢方向勝率與模擬收益
- 🔗 **API 文件** - 訪問 `/docs` 檢視 Swagger UI

### API 介面

| 介面 | 方法 | 說明 |
|------|------|------|
| `/api/v1/analysis/analyze` | POST | 觸發股票分析 |
| `/api/v1/analysis/tasks` | GET | 查詢任務列表 |
| `/api/v1/analysis/status/{task_id}` | GET | 查詢任務狀態 |
| `/api/v1/history` | GET | 查詢分析歷史 |
| `/api/v1/backtest/run` | POST | 觸發回測 |
| `/api/v1/backtest/results` | GET | 查詢回測結果（分頁） |
| `/api/v1/backtest/performance` | GET | 獲取整體回測表現 |
| `/api/v1/backtest/performance/{code}` | GET | 獲取單股回測表現 |
| `/api/v1/stocks/extract-from-image` | POST | 從圖片提取股票程式碼（multipart，超時 60s） |
| `/api/v1/stocks/parse-import` | POST | 解析 CSV/Excel/剪貼簿（multipart file 或 JSON `{"text":"..."}`，檔案≤2MB，文字≤100KB） |
| `/api/health` | GET | 健康檢查 |
| `/docs` | GET | API Swagger 文件 |

> 說明：`POST /api/v1/analysis/analyze` 在 `async_mode=false` 時僅支援單隻股票；批次 `stock_codes` 需使用 `async_mode=true`。非同步 `202` 響應對單股返回 `task_id`，對批次返回 `accepted` / `duplicates` 彙總結構。

**呼叫示例**：
```bash
# 健康檢查
curl http://127.0.0.1:8000/api/health

# 觸發分析（A股）
curl -X POST http://127.0.0.1:8000/api/v1/analysis/analyze \
  -H 'Content-Type: application/json' \
  -d '{"stock_code": "600519"}'

# 查詢任務狀態
curl http://127.0.0.1:8000/api/v1/analysis/status/<task_id>

# 觸發回測（全部股票）
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"force": false}'

# 觸發回測（指定股票）
curl -X POST http://127.0.0.1:8000/api/v1/backtest/run \
  -H 'Content-Type: application/json' \
  -d '{"code": "600519", "force": false}'

# 查詢整體回測表現
curl http://127.0.0.1:8000/api/v1/backtest/performance

# 查詢單股回測表現
curl http://127.0.0.1:8000/api/v1/backtest/performance/600519

# 分頁查詢回測結果
curl "http://127.0.0.1:8000/api/v1/backtest/results?page=1&limit=20"
```

### 自定義配置

修改預設埠或允許區域網訪問：

```bash
python main.py --serve-only --host 0.0.0.0 --port 8888
```

### 支援的股票程式碼格式

| 型別 | 格式 | 示例 |
|------|------|------|
| A股 | 6位數字 | `600519`、`000001`、`300750` |
| 北交所 | 8/4/92 開頭 6 位 | `920748`、`838163`、`430047` |
| 港股 | hk + 5位數字 | `hk00700`、`hk09988` |
| 美股 | 1-5 字母（可選 .X 字尾） | `AAPL`、`TSLA`、`BRK.B` |
| 美股指數 | SPX/DJI/IXIC 等 | `SPX`、`DJI`、`NASDAQ`、`VIX` |

### 注意事項

- 瀏覽器訪問：`http://127.0.0.1:8000`（或您配置的埠）
- 在雲伺服器上部署後，不知道瀏覽器該輸入什麼地址？請看 [雲伺服器 Web 介面訪問指南](deploy-webui-cloud.md)
- 分析完成後自動推送通知到配置的渠道
- 此功能在 GitHub Actions 環境中會自動禁用
- 另見 [openclaw Skill 整合指南](openclaw-skill-integration.md)

---

## 常見問題

### Q: 推送訊息被截斷？
A: 企業微信/飛書有訊息長度限制，系統已自動分段傳送。如需完整內容，可配置飛書雲文件功能。

### Q: 資料獲取失敗？
A: AkShare 使用爬蟲機制，可能被臨時限流。系統已配置重試機制，一般等待幾分鐘後重試即可。

### Q: 如何新增自選股？
A: 修改 `STOCK_LIST` 環境變數，多個程式碼用逗號分隔。

### Q: GitHub Actions 沒有執行？
A: 檢查是否啟用了 Actions，以及 cron 表示式是否正確（注意是 UTC 時間）。

---

更多問題請 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)

## Portfolio P0 PR1 (Core Ledger and Snapshot)

### Scope
- Core portfolio domain models:
  - account, trade, cash ledger, corporate action, position cache, lot cache, daily snapshot, fx cache
- Core service capability:
  - account CRUD
  - event writes
  - read-time replay snapshot for one account or all active accounts

### Accounting semantics
- Cost method:
  - `fifo` (default)
  - `avg`
- Same-day event ordering:
  - `cash -> corporate action -> trade`
- Corporate action effective-date rule:
  - `effective_date` is treated as effective before market trading on that day.

### Error and stability semantics
- `trade_uid` unique conflict returns `409` (API conflict semantics).
- sell writes now validate available quantity before insert; oversell is rejected with `409 portfolio_oversell`.
- Snapshot write path is atomic for positions/lots/daily snapshot.
- FX conversion keeps fail-open behavior (fallback 1:1 with stale marker) to avoid pipeline interruption.

### Test coverage in PR1
- FIFO/AVG partial sell replay
- Dividend and split replay
- Same-day ordering (dividend/trade, split/trade)
- API account/event/snapshot contract
- API duplicate trade_uid conflict

## Portfolio P0 PR2 (Import and Risk)

### CSV import
- Supported broker ids: `huatai`, `citic`, `cmb`.
- Unified workflow: parse CSV into normalized records, then commit into portfolio trades.
- Dedup policy:
  - First key: `trade_uid` (account-scoped)
  - Fallback key: deterministic hash of date/symbol/side/qty/price/fee/tax/currency

### Risk report
- Concentration monitoring: top position weight alert by config threshold.
- Drawdown monitoring: max/current drawdown computed from daily snapshots.
- Stop-loss proximity warning: mark near-alert and triggered items with threshold echo.

### FX fail-open
- FX refresh first tries online source (YFinance).
- On online failure, fallback to latest cached rate and mark `is_stale=true`.
- Main snapshot/risk pipeline stays available even when online FX fetch is unavailable.

## Portfolio P0 PR3 (Web + Agent Consumption)

### Web consumption page
- Added Web page route: `/portfolio` (`apps/dsa-web/src/pages/PortfolioPage.tsx`).
- Data sources:
  - `GET /api/v1/portfolio/snapshot`
  - `GET /api/v1/portfolio/risk`
- Supports:
  - full portfolio / single account switch
  - cost method switch (`fifo` / `avg`)
  - concentration pie chart (Top Positions) with Recharts
  - snapshot KPI cards and risk summary cards

### Agent tool
- Added `get_portfolio_snapshot` data tool for account-aware LLM suggestions.
- Default behavior:
  - compact summary output (token-friendly)
  - includes optional compact risk block
- Optional parameters:
  - `account_id`
  - `cost_method` (`fifo` / `avg`)
  - `as_of` (`YYYY-MM-DD`)
  - `include_positions` (default `false`)
  - `include_risk` (default `true`)

### Stability and compatibility
- New capability is additive only; no removal of existing keys/routes.
- Fail-open semantics:
  - If risk block fails, snapshot is still returned.
  - If portfolio module is unavailable, tool returns structured `not_supported`.

## Portfolio P0 PR4 (Gap Closure)

### API query closure
- Added event query endpoints:
  - `GET /api/v1/portfolio/trades`
  - `GET /api/v1/portfolio/cash-ledger`
  - `GET /api/v1/portfolio/corporate-actions`
- Added event delete endpoints:
  - `DELETE /api/v1/portfolio/trades/{trade_id}`
  - `DELETE /api/v1/portfolio/cash-ledger/{entry_id}`
  - `DELETE /api/v1/portfolio/corporate-actions/{action_id}`
- Unified query parameters:
  - `account_id`, `date_from`, `date_to`, `page`, `page_size`
- Trade/cash/corporate-action specific filters:
  - trades: `symbol`, `side`
  - cash-ledger: `direction`
  - corporate-actions: `symbol`, `action_type`
- Unified response shape:
  - `items`, `total`, `page`, `page_size`

### CSV import framework
- Reworked parser logic into extensible parser registry.
- Built-in adapters remain: `huatai`, `citic`, `cmb` with alias mapping.
- Added parser discovery endpoint:
  - `GET /api/v1/portfolio/imports/csv/brokers`

### Web closure
- `/portfolio` page now includes:
  - inline account creation entry with empty-state guide and auto-switch to created account
  - manual event entry forms: trade / cash / corporate action
  - CSV parse + commit operations (supports `dry_run`)
  - event list panel with filters and pagination
  - single-account scoped event deletion for trade / cash / corporate action correction
  - broker selector fallback to built-in brokers (`huatai/citic/cmb`) when broker list API fails or returns empty

### Risk sector concentration semantics
- Added `sector_concentration` in `GET /api/v1/portfolio/risk`.
- Mapping rules:
  - CN positions try board mapping from `get_belong_boards`.
  - Non-CN or mapping failure falls back to `UNCLASSIFIED`.
  - Uses single primary board per symbol to avoid duplicate weighting.
- Fail-open:
  - board lookup errors do not interrupt risk response.
  - response returns coverage/error details for explainability.
