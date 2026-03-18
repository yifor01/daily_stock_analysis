<div align="center">

# 📈 股票智慧分析系統

[![GitHub stars](https://img.shields.io/github/stars/ZhuLinsen/daily_stock_analysis?style=social)](https://github.com/ZhuLinsen/daily_stock_analysis/stargazers)
[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/)

<p>
  <a href="https://trendshift.io/repositories/18527" target="_blank"><img src="https://trendshift.io/api/badge/repositories/18527" alt="ZhuLinsen%2Fdaily_stock_analysis | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
  <a href="https://hellogithub.com/repository/ZhuLinsen/daily_stock_analysis" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=6daa16e405ce46ed97b4a57706aeb29f&claim_uid=pfiJMqhR9uvDGlT&theme=neutral" alt="Featured｜HelloGitHub" style="width: 250px; height: 54px;" width="250" height="54" /></a>
</p>

> 🤖 基於 AI 大模型的 A股/港股/美股自選股智慧分析系統，每日自動分析並推送「決策儀表盤」到企業微信/飛書/Telegram/Discord/郵箱

[**功能特性**](#-功能特性) · [**快速開始**](#-快速開始) · [**推送效果**](#-推送效果) · [**完整指南**](docs/full-guide.md) · [**常見問題**](docs/FAQ.md) · [**更新日誌**](docs/CHANGELOG.md)

簡體中文 | [English](docs/README_EN.md) | [繁體中文](docs/README_CHT.md)

</div>

## 💖 贊助商 (Sponsors)
<div align="center">
  <a href="https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis" target="_blank">
    <img src="./sources/serpapi_banner_zh.png" alt="輕鬆抓取搜尋引擎上的實時金融新聞資料 - SerpApi" height="160">
  </a>
</div>
<br>


## ✨ 功能特性

| 模組 | 功能 | 說明 |
|------|------|------|
| AI | 決策儀表盤 | 一句話核心結論 + 精確買賣點位 + 操作檢查清單 |
| 分析 | 多維度分析 | 技術面（盤中實時 MA/多頭排列）+ 籌碼分佈 + 輿情情報 + 實時行情 |
| 市場 | 全球市場 | 支援 A股、港股、美股及美股指數（SPX、DJI、IXIC 等） |
| 基本面 | 結構化聚合 | 新增 `fundamental_context`（valuation/growth/earnings/institution/capital_flow/dragon_tiger/boards，其中 `earnings.data` 新增 `financial_report` 與 `dividend`，`boards` 表示板塊漲跌榜），主鏈路 fail-open 降級 |
| 策略 | 市場策略系統 | 內建 A股「三段式覆盤策略」與美股「Regime Strategy」，輸出進攻/均衡/防守或 risk-on/neutral/risk-off 計劃，並附“僅供參考，不構成投資建議”提示 |
| 覆盤 | 大盤覆盤 | 每日市場概覽、板塊漲跌；支援 cn(A股)/us(美股)/both(兩者) 切換 |
| 智慧匯入 | 多源匯入 | 支援圖片、CSV/Excel 檔案、剪貼簿貼上；Vision LLM 提取程式碼+名稱；置信度分層確認；名稱→程式碼解析（本地+拼音+AkShare） |
| 歷史記錄 | 批次管理 | 支援多選、全選及批次刪除歷史分析記錄，最佳化管理效率與 UI/UX 體驗 |
| 回測 | AI 回測驗證 | 自動評估歷史分析準確率，方向勝率、止盈止損命中率 |
| **Agent 問股** | **策略對話** | **多輪策略問答，支援均線金叉/纏論/波浪等 11 種內建策略，Web/Bot/API 全鏈路** |
| 推送 | 多渠道通知 | 企業微信、飛書、Telegram、Discord、釘釘、郵件、Pushover |
| 自動化 | 定時執行 | GitHub Actions 定時執行，無需伺服器 |

> 歷史報告詳情會優先展示 AI 返回的原始「狙擊點位」文字，避免區間價、條件說明等複雜內容在歷史回看時被壓縮成單個數字。

> Web 管理認證支援執行時開關；如果系統中已保留管理員密碼，重新開啟認證時必須提供當前密碼，避免在認證關閉視窗內直接獲取新的管理員會話。
> 多程序/多 worker 部署時，認證開關僅在當前程序即時生效；需重啟或滾動重啟全部 worker 以統一狀態。

> 持倉管理補充說明：賣出錄入現在會在寫入前校驗可用持倉，超售會直接拒絕；如果歷史裡誤錄了交易 / 資金流水 / 公司行為，可在 Web `/portfolio` 頁的事件列表中直接刪除後恢復快照。

### 技術棧與資料來源

| 型別 | 支援 |
|------|------|
| AI 模型 | [AIHubMix](https://aihubmix.com/?aff=CfMq)、Gemini、OpenAI 相容、DeepSeek、通義千問、Claude 等（統一透過 [LiteLLM](https://github.com/BerriAI/litellm) 呼叫，支援多 Key 負載均衡）|
| 行情資料 | AkShare、Tushare、Pytdx、Baostock、YFinance |
| 新聞搜尋 | Tavily、SerpAPI、Bocha、Brave、MiniMax |
| 社交輿情 | [Stock Sentiment API](https://api.adanos.org/docs)（Reddit / X / Polymarket，僅美股，可選） |

> 注：美股歷史資料與實時行情統一使用 YFinance，確保復權一致性

### 內建交易紀律

| 規則 | 說明 |
|------|------|
| 嚴禁追高 | 乖離率超閾值（預設 5%，可配置）自動提示風險；強勢趨勢股自動放寬 |
| 趨勢交易 | MA5 > MA10 > MA20 多頭排列 |
| 精確點位 | 買入價、止損價、目標價 |
| 檢查清單 | 每項條件以「滿足 / 注意 / 不滿足」標記 |
| 新聞時效 | 可配置新聞最大時效（預設 3 天），避免使用過時資訊 |

## 🚀 快速開始

### 方式一：GitHub Actions（推薦）

> 5 分鐘完成部署，零成本，無需伺服器。


#### 1. Fork 本倉庫

點選右上角 `Fork` 按鈕（順便點個 Star⭐ 支援一下）

#### 2. 配置 Secrets

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**AI 模型配置（至少配置一個）**

> 詳細配置說明見 [LLM 配置指南](docs/LLM_CONFIG_GUIDE.md)（三層配置、渠道模式、YAML高階配置、Vision、Agent、排錯），GitHub Actions使用者也可以實現YAML高階配置。進階使用者可配置 `LITELLM_MODEL`、`LITELLM_FALLBACK_MODELS` 或 `LLM_CHANNELS` 多渠道模式。

> 現在推薦把多模型配置統一寫成 `LLM_CHANNELS + LLM_<NAME>_PROTOCOL/BASE_URL/API_KEY/MODELS/ENABLED`。Web 設定頁和 `.env` 使用同一套欄位，便於相互切換。

> 💡 **推薦 [AIHubMix](https://aihubmix.com/?aff=CfMq)**：一個 Key 即可使用 Gemini、GPT、Claude、DeepSeek 等全球主流模型，無需科學上網，含免費模型（glm-5、gpt-4o-free 等），付費模型高穩定性無限併發。本專案可享 **10% 充值優惠**。

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `AIHUBMIX_KEY` | [AIHubMix](https://aihubmix.com/?aff=CfMq) API Key，一 Key 切換使用全系模型，免費模型可用 | 可選 |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) 獲取免費 Key（需科學上網） | 可選 |
| `ANTHROPIC_API_KEY` | [Anthropic Claude](https://console.anthropic.com/) API Key | 可選 |
| `ANTHROPIC_MODEL` | Claude 模型（如 `claude-3-5-sonnet-20241022`） | 可選 |
| `OPENAI_API_KEY` | OpenAI 相容 API Key（支援 DeepSeek、通義千問等） | 可選 |
| `OPENAI_BASE_URL` | OpenAI 相容 API 地址（如 `https://api.deepseek.com/v1`） | 可選 |
| `OPENAI_MODEL` | 模型名稱（如 `gemini-3.1-pro-preview`、`gemini-3-flash-preview`、`gpt-5.2`） | 可選 |
| `OPENAI_VISION_MODEL` | 圖片識別專用模型（部分第三方模型不支援影象；不填則用 `OPENAI_MODEL`） | 可選 |

> 注：AI 優先順序 Gemini > Anthropic > OpenAI（含 AIHubmix），至少配置一個。`AIHUBMIX_KEY` 無需配置 `OPENAI_BASE_URL`，系統自動適配。圖片識別需 Vision 能力模型。DeepSeek 思考模式（deepseek-reasoner、deepseek-r1、qwq、deepseek-chat）按模型名自動識別，無需額外配置。

<details>
<summary><b>通知渠道配置</b>（點選展開，至少配置一個）</summary>


| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書 Webhook URL | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 獲取） | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `TELEGRAM_MESSAGE_THREAD_ID` | Telegram Topic ID (用於傳送到子話題) | 可選 |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL | 可選 |
| `DISCORD_BOT_TOKEN` | Discord Bot Token（與 Webhook 二選一） | 可選 |
| `DISCORD_MAIN_CHANNEL_ID` | Discord Channel ID（使用 Bot 時需要） | 可選 |
| `EMAIL_SENDER` | 發件人郵箱（如 `xxx@qq.com`） | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登入密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（多個用逗號分隔，留空則發給自己） | 可選 |
| `EMAIL_SENDER_NAME` | 郵件發件人顯示名稱（預設：daily_stock_analysis股票分析助手，支援中文並自動編碼郵件頭） | 可選 |
| `STOCK_GROUP_N` / `EMAIL_GROUP_N` | 股票分組發往不同郵箱（如 `STOCK_GROUP_1=600519,300750` `EMAIL_GROUP_1=user1@example.com`） | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（[獲取地址](https://www.pushplus.plus)，國內推送服務） | 可選 |
| `PUSHPLUS_TOPIC` | PushPlus 群組編碼（一對多推送，配置後訊息推送給群組所有訂閱使用者） | 可選 |
| `SERVERCHAN3_SENDKEY` | Server醬³ Sendkey（[獲取地址](https://sc3.ft07.com/)，手機APP推送服務） | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（支援釘釘等，多個用逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook 的 Bearer Token（用於需要認證的 Webhook） | 可選 |
| `WEBHOOK_VERIFY_SSL` | Webhook HTTPS 證書校驗（預設 true）。設為 false 可支援自簽名證書。警告：關閉有嚴重安全風險，僅限可信內網 | 可選 |
| `SCHEDULE_RUN_IMMEDIATELY` | 定時模式啟動時是否立即執行一次分析 | 可選 |
| `RUN_IMMEDIATELY` | 非定時模式啟動時是否立即執行一次分析 | 可選 |
| `SINGLE_STOCK_NOTIFY` | 單股推送模式：設為 `true` 則每分析完一隻股票立即推送 | 可選 |
| `REPORT_TYPE` | 報告型別：`simple`(精簡)、`full`(完整)、`brief`(3-5句概括)，Docker環境推薦設為 `full` | 可選 |
| `REPORT_SUMMARY_ONLY` | 僅分析結果摘要：設為 `true` 時只推送彙總，不含個股詳情 | 可選 |
| `REPORT_TEMPLATES_DIR` | Jinja2 模板目錄（相對專案根，預設 `templates`） | 可選 |
| `REPORT_RENDERER_ENABLED` | 啟用 Jinja2 模板渲染（預設 `false`，保證零迴歸） | 可選 |
| `REPORT_INTEGRITY_ENABLED` | 啟用報告完整性校驗，缺失必填欄位時重試或佔位補全（預設 `true`） | 可選 |
| `REPORT_INTEGRITY_RETRY` | 完整性校驗重試次數（預設 `1`，`0` 表示僅佔位不重試） | 可選 |
| `REPORT_HISTORY_COMPARE_N` | 歷史訊號對比條數，`0` 關閉（預設），`>0` 啟用 | 可選 |
| `ANALYSIS_DELAY` | 個股分析和大盤分析之間的延遲（秒），避免API限流，如 `10` | 可選 |
| `MAX_WORKERS` | 非同步分析任務佇列併發執行緒數（預設 `3`）；儲存後佇列空閒時自動應用，繁忙時延後生效 | 可選 |
| `MERGE_EMAIL_NOTIFICATION` | 個股與大盤覆盤合併推送（預設 false），減少郵件數量 | 可選 |
| `MARKDOWN_TO_IMAGE_CHANNELS` | 將 Markdown 轉為圖片傳送的渠道（逗號分隔）：`telegram,wechat,custom,email` | 可選 |
| `MARKDOWN_TO_IMAGE_MAX_CHARS` | 超過此長度不轉圖片，避免超大圖片（預設 `15000`） | 可選 |
| `MD2IMG_ENGINE` | 轉圖引擎：`wkhtmltoimage`（預設）或 `markdown-to-file`（emoji 更好） | 可選 |

> 至少配置一個渠道，配置多個則同時推送。圖片傳送與引擎安裝細節請參考 [完整指南](docs/full-guide.md)

</details>

**其他配置**

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `STOCK_LIST` | 自選股程式碼，如 `600519,hk00700,AAPL,TSLA` | ✅ |
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 搜尋 API（新聞搜尋） | 推薦 |
| `MINIMAX_API_KEYS` | [MiniMax](https://platform.minimaxi.com/) Coding Plan Web Search（結構化搜尋結果） | 可選 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis) 全渠道搜尋 | 可選 |
| `BOCHA_API_KEYS` | [博查搜尋](https://open.bocha.cn/) Web Search API（中文搜尋最佳化，支援AI摘要，多個key用逗號分隔） | 可選 |
| `BRAVE_API_KEYS` | [Brave Search](https://brave.com/search/api/) API（隱私優先，美股最佳化，多個key用逗號分隔） | 可選 |
| `SEARXNG_BASE_URLS` | SearXNG 自建例項（無配額兜底，需在 settings.yml 啟用 format: json） | 可選 |
| `SOCIAL_SENTIMENT_API_KEY` | [Stock Sentiment API](https://api.adanos.org/docs)（Reddit/X/Polymarket 社交輿情，僅美股） | 可選 |
| `SOCIAL_SENTIMENT_API_URL` | 自定義社交輿情 API 地址（預設 `https://api.adanos.org`） | 可選 |
| `TUSHARE_TOKEN` | [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) Token | 可選 |
| `PREFETCH_REALTIME_QUOTES` | 實時行情預取開關：設為 `false` 可禁用全市場預取（預設 `true`） | 可選 |
| `WECHAT_MSG_TYPE` | 企微訊息型別，預設 markdown，支援配置 text 型別，傳送純 markdown 文字 | 可選 |
| `NEWS_STRATEGY_PROFILE` | 新聞策略視窗檔位：`ultra_short`(1天) / `short`(3天) / `medium`(7天) / `long`(30天)，預設 `short` | 可選 |
| `NEWS_MAX_AGE_DAYS` | 新聞最大時效上限（天），預設 3；實際視窗 `effective_days = min(profile_days, NEWS_MAX_AGE_DAYS)`，例如 `ultra_short(1)` + `7` 仍為 `1` 天 | 可選 |
| `BIAS_THRESHOLD` | 乖離率閾值（%），預設 5.0，超過提示不追高；強勢趨勢股自動放寬 | 可選 |
| `AGENT_MODE` | 開啟 Agent 策略問股模式（`true`/`false`，預設 false） | 可選 |
| `AGENT_SKILLS` | 啟用的策略（逗號分隔），`all` 啟用全部 11 個；不配置時預設 4 個，詳見 `.env.example` | 可選 |
| `AGENT_MAX_STEPS` | Agent 最大推理步數（預設 10） | 可選 |
| `AGENT_STRATEGY_DIR` | 自定義策略目錄（預設內建 `strategies/`） | 可選 |
| `TRADING_DAY_CHECK_ENABLED` | 交易日檢查（預設 `true`）：非交易日跳過執行；設為 `false` 或使用 `--force-run` 強制執行 | 可選 |
| `ENABLE_CHIP_DISTRIBUTION` | 啟用籌碼分佈（Actions 預設 false；需籌碼資料時在 Variables 中設為 true，介面可能不穩定） | 可選 |
| `ENABLE_FUNDAMENTAL_PIPELINE` | 基本面聚合總開關；關閉時保持主流程不變 | 可選 |
| `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` | 基本面階段總預算（秒） | 可選 |
| `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS` | 單能力源呼叫超時（秒） | 可選 |
| `FUNDAMENTAL_RETRY_MAX` | 基本面能力重試次數（包含首次） | 可選 |
| `FUNDAMENTAL_CACHE_TTL_SECONDS` | 基本面快取 TTL（秒） | 可選 |
| `FUNDAMENTAL_CACHE_MAX_ENTRIES` | 基本面快取最大條目數（避免長時間執行記憶體增長） | 可選 |

> 基本面超時語義（P0）：
> - 當前採用 `best-effort` 軟超時（fail-open），超時會立即降級並繼續主流程；
> - 不承諾嚴格硬中斷第三方呼叫執行緒，因此 `P95 <= 1.5s` 是階段目標而非硬 SLA；
> - 若業務需要硬 SLA，可在後續階段升級為“子程序隔離 + kill”的硬超時方案。
> - 欄位契約：
>   - `fundamental_context.boards.data` = `sector_rankings`（板塊漲跌榜，結構 `{top, bottom}`）；
>   - `fundamental_context.earnings.data.financial_report` = 財報摘要（報告期、營收、歸母淨利潤、經營現金流、ROE）；
>   - `fundamental_context.earnings.data.dividend` = 分紅指標（僅現金分紅稅前口徑，含 `events`、`ttm_cash_dividend_per_share`、`ttm_dividend_yield_pct`）；
>   - `get_stock_info.belong_boards` = 個股所屬板塊列表；
>   - `get_stock_info.boards` 為相容別名，值與 `belong_boards` 相同（未來僅在大版本考慮移除）；
>   - `get_stock_info.sector_rankings` 與 `fundamental_context.boards.data` 保持一致。
> - 板塊漲跌榜採用固定回退順序：`AkShare(EM->Sina) -> Tushare -> efinance`。

#### 3. 啟用 Actions

`Actions` 標籤 → `I understand my workflows, go ahead and enable them`

#### 4. 手動測試

`Actions` → `每日股票分析` → `Run workflow` → `Run workflow`

#### 完成

預設每個**工作日 18:00（北京時間）**自動執行，也可手動觸發。預設非交易日（含 A/H/US 節假日）不執行。

> 💡 **關於跳過交易日檢查的兩種機制：**
> | 機制 | 配置方式 | 生效範圍 | 適用場景 |
> |------|----------|----------|----------|
> | `TRADING_DAY_CHECK_ENABLED=false` | 環境變數/Secrets | 全域性、長期有效 | 測試環境、長期關閉檢查 |
> | `force_run` (UI 勾選) | Actions 手動觸發時選擇 | 單次執行 | 臨時在非交易日執行一次 |
>
> - **環境變數方式**：在 `.env` 或 GitHub Secrets 中設定，影響所有執行方式（定時觸發、手動觸發、本地執行）
> - **UI 勾選方式**：僅在 GitHub Actions 手動觸發時可見，不影響定時任務，適合臨時需求

### 方式二：本地執行 / Docker 部署

```bash
# 克隆專案
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git && cd daily_stock_analysis

# 安裝依賴
pip install -r requirements.txt

# 配置環境變數
cp .env.example .env && vim .env

# 執行分析
python main.py
```

如果你不用 Web，推薦直接在 `.env` 裡按條寫渠道：

```env
LLM_CHANNELS=primary
LLM_PRIMARY_PROTOCOL=openai
LLM_PRIMARY_BASE_URL=https://api.deepseek.com/v1
LLM_PRIMARY_API_KEY=sk-xxxxxxxx
LLM_PRIMARY_MODELS=deepseek-chat
LITELLM_MODEL=openai/deepseek-chat
```

儲存後也可以在 Web 設定頁繼續編輯同一組欄位；不會要求額外配置檔案。

如果同時啟用了 `LITELLM_CONFIG`，YAML 仍然是執行時主模型 / fallback / Vision 的唯一來源；渠道編輯器只儲存渠道條目，不會覆蓋 YAML 的執行時選擇。

> Docker 部署、定時任務配置請參考 [完整指南](docs/full-guide.md)
> 桌面客戶端打包請參考 [桌面端打包說明](docs/desktop-package.md)

## 📱 推送效果

### 決策儀表盤
```
🎯 2026-02-08 決策儀表盤
共分析3只股票 | 🟢買入:0 🟡觀望:2 🔴賣出:1

📊 分析結果摘要
⚪ 中鎢高新(000657): 觀望 | 評分 65 | 看多
⚪ 永鼎股份(600105): 觀望 | 評分 48 | 震盪
🟡 新萊應材(300260): 賣出 | 評分 35 | 看空

⚪ 中鎢高新 (000657)
📰 重要資訊速覽
💭 輿情情緒: 市場關注其AI屬性與業績高增長，情緒偏積極，但需消化短期獲利盤和主力流出壓力。
📊 業績預期: 基於輿情資訊，公司2025年前三季度業績同比大幅增長，基本面強勁，為股價提供支撐。

🚨 風險警報:

風險點1：2月5日主力資金大幅淨賣出3.63億元，需警惕短期拋壓。
風險點2：籌碼集中度高達35.15%，表明籌碼分散，拉昇阻力可能較大。
風險點3：輿情中提及公司歷史違規記錄及重組相關風險提示，需保持關注。
✨ 利好催化:

利好1：公司被市場定位為AI伺服器HDI核心供應商，受益於AI產業發展。
利好2：2025年前三季度扣非淨利潤同比暴漲407.52%，業績表現強勁。
📢 最新動態: 【最新訊息】輿情顯示公司是AI PCB微鑽領域龍頭，深度繫結全球頭部PCB/載板廠。2月5日主力資金淨賣出3.63億元，需關注後續資金流向。

---
生成時間: 18:00
```

### 大盤覆盤
```
🎯 2026-01-10 大盤覆盤

📊 主要指數
- 上證指數: 3250.12 (🟢+0.85%)
- 深證成指: 10521.36 (🟢+1.02%)
- 創業板指: 2156.78 (🟢+1.35%)

📈 市場概況
上漲: 3920 | 下跌: 1349 | 漲停: 155 | 跌停: 3

🔥 板塊表現
領漲: 網際網路服務、文化傳媒、小金屬
領跌: 保險、航空機場、光伏裝置
```
## ⚙️ 配置說明

> 📖 完整環境變數、定時任務配置請參考 [完整配置指南](docs/full-guide.md)
> 郵件通知當前基於 SMTP 授權碼/基礎認證；若 Outlook / Exchange 賬號或租戶強制 OAuth2，當前版本暫不支援。


## 🖥️ Web 介面

![img.png](sources/fastapi_server.png)

包含完整的配置管理、任務監控和手動分析功能。

**可選密碼保護**：在 `.env` 中設定 `ADMIN_AUTH_ENABLED=true` 可啟用 Web 登入，首次訪問在網頁設定初始密碼，保護 Settings 中的 API 金鑰等敏感配置。系統設定現支援執行時開啟或關閉認證；關閉認證不會刪除已儲存密碼，後續可直接重新啟用。認證開啟時，`POST /api/v1/auth/logout` 也需要有效會話；如果會話已經過期，前端會直接回到登入頁。詳見 [完整指南](docs/full-guide.md)。

### 智慧匯入

在 **設定 → 基礎設定** 中找到「智慧匯入」區塊，支援三種方式新增自選股：

1. **圖片**：拖拽或選擇自選股截圖（如 APP 持倉頁、行情列表），Vision AI 自動識別程式碼+名稱，並給出置信度
2. **檔案**：上傳 CSV 或 Excel (.xlsx)，自動解析程式碼/名稱列
3. **貼上**：從 Excel 或表格複製後貼上，點選「解析」即可

**預覽與合併**：高置信度預設勾選，中/低置信度需手動勾選；支援按程式碼去重、清空、全選；僅合併已勾選且解析成功的項。

**配置與限制**：
- 圖片需配置 Vision API（`GEMINI_API_KEY`、`ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY` 至少一個）
- 圖片：JPG/PNG/WebP/GIF，≤5MB；檔案：≤2MB；貼上文字：≤100KB

**API**：`POST /api/v1/stocks/extract-from-image`（圖片）、`POST /api/v1/stocks/parse-import`（檔案/貼上）。詳見 [完整指南](docs/full-guide.md)。

**LLM 用量查詢**：`GET /api/v1/usage/summary?period=today|month|all`，返回按呼叫型別和模型分組的 token 消耗彙總（`total_calls`、`total_tokens`、`by_call_type`、`by_model`）。

**分析 API 說明**：`POST /api/v1/analysis/analyze` 在 `async_mode=false` 時僅支援單隻股票；批次 `stock_codes` 需要 `async_mode=true`。非同步 `202` 響應對單股返回 `task_id`，對批次返回 `accepted` / `duplicates` 彙總結構；空白股票程式碼會在服務端過濾，若過濾後為空則返回 `400`。未知 `/api` 路徑（含 `/api` 本身）返回 JSON `404`，不再回退到前端頁面。詳見 [API 規範](docs/architecture/api_spec.json)。

### 歷史報告詳情

在首頁歷史記錄中選擇一條分析記錄後，點選「詳細報告」按鈕可在右側抽屜中檢視與推送通知格式一致的完整 Markdown 分析報告，包含輿情情報、核心結論、資料透視、作戰計劃等完整內容。

### 🤖 Agent 策略問股

在 `.env` 中設定 `AGENT_MODE=true` 後啟動服務，訪問 `/chat` 頁面即可開始多輪策略問答。

- **選擇策略**：均線金叉、纏論、波浪理論、多頭趨勢等 11 種內建策略
- **自然語言提問**：如「用纏論分析 600519」，Agent 自動呼叫實時行情、K線、技術指標、新聞等工具
- **流式進度反饋**：實時展示 AI 思考路徑（行情獲取 → 技術分析 → 新聞搜尋 → 生成結論）
- **多輪對話**：支援追問上下文，會話歷史持久化儲存
- **匯出與傳送**：可將會話匯出為 .md 檔案，或傳送到已配置的通知渠道
- **後臺執行**：切換頁面不中斷分析，完成時 Dock 問股圖示顯示角標
- **Bot 命令**：`/ask` 策略分析（支援多股對比）、`/chat` 自由對話
- **自定義策略**：在 `strategies/` 目錄下新建 YAML 檔案即可新增策略，無需寫程式碼
- **多 Agent 架構**（實驗性）：設定 `AGENT_ARCH=multi` 啟用 Technical → Intel → Risk → Strategy → Decision 多 Agent 級聯編排，透過 `AGENT_ORCHESTRATOR_MODE` 控制深度（quick/standard/full/strategy）。超時或中間階段 JSON 解析失敗時，系統會優先保留已完成階段結果並降級生成最小可用儀表盤，避免整份報告直接退回預設佔位。詳見 [完整配置指南](docs/full-guide.md)

> **注意**：配置了任意 AI API Key 後，Agent 對話功能自動可用，無需手動設定 `AGENT_MODE=true`。如需顯式關閉可設定 `AGENT_MODE=false`。每次對話會產生 LLM API 呼叫費用。若你手動修改了 `.env` 中的模型主備配置（如 `LITELLM_MODEL` / `LITELLM_FALLBACK_MODELS` / `LLM_CHANNELS`），需要重啟服務或觸發配置過載後，新程序才會按新模型生效。

### 啟動方式

1. **啟動服務**（預設會自動編譯前端）
   ```bash
   python main.py --webui       # 啟動 Web 介面 + 執行定時分析
   python main.py --webui-only  # 僅啟動 Web 介面
   ```
   啟動時會在 `apps/dsa-web` 自動執行 `npm install && npm run build`。
   如需關閉自動構建，設定 `WEBUI_AUTO_BUILD=false`，並改為手動執行：
   ```bash
   cd ./apps/dsa-web
   npm install && npm run build
   cd ../..
   ```

訪問 `http://127.0.0.1:8000` 即可使用。

> 在雲伺服器上部署後，不知道瀏覽器該輸入什麼地址？請看 [雲伺服器 Web 介面訪問指南](docs/deploy-webui-cloud.md)。

> 也可以使用 `python main.py --serve` (等效命令)

## 🗺️ Roadmap

檢視已支援的功能和未來規劃：[更新日誌](docs/CHANGELOG.md)

> 有建議？歡迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)

> ⚠️ **UI 調整提示**：專案當前正在持續進行 Web UI 調整與升級，部分頁面在過渡階段可能仍存在樣式、互動或相容性問題。歡迎透過 [Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 反饋問題，或直接提交 [Pull Request](https://github.com/ZhuLinsen/daily_stock_analysis/pulls) 一起完善。
---

## ☕ 支援專案

如果本專案對你有幫助，歡迎支援專案的持續維護與迭代，感謝支援 🙏  
讚賞可備註聯絡方式，祝股市長虹

| 支付寶 (Alipay) | 微信支付 (WeChat) | Ko-fi |
| :---: | :---: | :---: |
| <img src="./sources/alipay.jpg" width="200" alt="Alipay"> | <img src="./sources/wechatpay.jpg" width="200" alt="WeChat Pay"> | <a href="https://ko-fi.com/mumu157" target="_blank"><img src="./sources/ko-fi.png" width="200" alt="Ko-fi"></a> |

---

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

詳見 [貢獻指南](docs/CONTRIBUTING.md)

### 本地門禁（建議先跑）

```bash
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh
```

如修改前端（`apps/dsa-web`）：

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

## 📄 License
[MIT License](LICENSE) © 2026 ZhuLinsen

如果你在專案中使用或基於本專案進行二次開發，
非常歡迎在 README 或文件中註明來源並附上本倉庫連結。
這將有助於專案的持續維護和社群發展。

## 📬 聯絡與合作
- GitHub Issues：[提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)
- 合作郵箱：zhuls345@gmail.com

## ⭐ Star History
**如果覺得有用，請給個 ⭐ Star 支援一下！**

<a href="https://star-history.com/#ZhuLinsen/daily_stock_analysis&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
 </picture>
</a>

## ⚠️ 免責宣告

本專案僅供學習和研究使用，不構成任何投資建議。股市有風險，投資需謹慎。作者不對使用本專案產生的任何損失負責。

---
