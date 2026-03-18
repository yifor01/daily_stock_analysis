# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> For user-friendly release highlights, see the [GitHub Releases](https://github.com/ZhuLinsen/daily_stock_analysis/releases) page.

## [Unreleased]

### 說明

- 暫無。

## [3.8.0] - 2026-03-17

### 釋出亮點

- 🎨 **Web 介面完成一輪骨架升級** — 新的 App Shell、側邊導航、主題能力、登入與系統設定流程已經串成統一體驗，桌面端載入背景也完成對齊。
- 📈 **分析上下文繼續補強** — 美股新增社交輿情情報，A 股補齊財報與分紅結構化上下文，Tushare 新接入籌碼分佈和行業板塊漲跌資料。
- 🔒 **執行穩定性與配置相容性提升** — 退出登入會立即讓舊會話失效，定時啟動相容舊配置，執行中的 `MAX_WORKERS` 調整和新聞時效視窗反饋更清晰。
- 💼 **持倉糾錯鏈路更完整** — 超售會被前置攔截，錯誤交易/資金流水/公司行為可以直接刪除回滾，便於修復髒資料。

### 新功能

- 📱 **美股社交輿情情報** — 新增 Reddit / X / Polymarket 社交媒體情緒資料來源，為美股分析提供實時社交熱度、情緒評分和提及量等補充指標；完全可選，僅在配置 `SOCIAL_SENTIMENT_API_KEY` 後對美股生效。
- 📊 **A 股財報與分紅結構化增強**（Issue #710）— `fundamental_context.earnings.data` 新增 `financial_report` 與 `dividend` 欄位；分紅統一按“僅現金分紅、稅前口徑”計算，並補充 `ttm_cash_dividend_per_share` 與 `ttm_dividend_yield_pct`；分析/歷史 API 的 `details` 追加 `financial_report`、`dividend_metrics` 可選欄位，保持 fail-open 與向後相容。
- 🔍 **接入 Tushare 籌碼與行業板塊介面** — 新增籌碼分佈、行業板塊漲跌資料獲取能力，並統一納入配置化資料來源優先順序；預設按上海時間區分盤中/盤後交易日取數，優先使用 Tushare 同花順介面，必要時降級到東財。
- 🧱 **Web UI 基礎骨架升級** — 重建共享設計令牌與通用元件，新增 App Shell、Theme Provider、側邊導航，並同步調整 Electron 載入背景，為 Web / Desktop 的統一體驗打底。
- 🔐 **登入與系統設定流程重做** — 重構 Login、Settings 與 Auth 管理流程，補上顯式的認證 setup-state 處理，並讓 Web 端與執行時認證配置 API 行為對齊。
- 🧪 **前端迴歸與冒煙覆蓋補強** — 新增並擴充套件登入、首頁、聊天、移動端 Shell、設定頁、回測入口等關鍵路徑的元件測試與 Playwright smoke coverage。

### 變更

- 🧭 **頁面接入新 Shell 佈局契約** — Home、Chat、Settings、Backtest 已統一接入新的頁面容器、抽屜和滾動約定，降低 UI 遷移期間的頁面行為不一致。
- 💾 **設定頁狀態同步更穩** — 最佳化草稿保留、直接儲存同步與衝突處理，減少模組級儲存後前後端配置狀態不一致的問題。
- 🎭 **登入頁視覺基線迴歸** — 登入頁恢復到既有 `006` 分支的視覺基線，同時保留新的認證狀態邏輯和統一表單互動模型。
- 🏛️ **AI 協作治理資產加固** — 收斂並加強 `AGENTS.md`、`CLAUDE.md`、Copilot 指令和校驗指令碼的一致性約束，降低治理資產長期漂移風險。

### 修復

- ⏰ **定時啟動立即執行相容舊配置**（Issue #726）— `SCHEDULE_RUN_IMMEDIATELY` 未設定時會回退讀取 `RUN_IMMEDIATELY`，修復升級後舊 `.env` 在定時模式下的相容性問題；同時澄清 `.env.example` / README 中兩個配置項的適用範圍，並註明 Outlook / Exchange 強制 OAuth2 暫不支援。
- 🧵 **執行期 `MAX_WORKERS` 配置生效與可解釋性增強**（#633）— 修復非同步分析佇列未按 `MAX_WORKERS` 同步的問題；新增任務佇列併發 in-place 同步機制（空閒即時生效、繁忙延後），並在設定儲存反饋與執行日誌中明確輸出 `profile/max/effective`，減少“引數未生效”誤解。
- 🔐 **退出登入立即失效現有會話** — `POST /api/v1/auth/logout` 現在會輪換 session secret，避免舊 cookie 在退出後仍可繼續訪問受保護介面；同瀏覽器標籤頁和併發頁面會被同步登出。認證開啟時，該介面也不再屬於匿名白名單，未登入請求會返回 `401`，避免匿名請求觸發全域性 session 失效。
- 🧮 **Tushare 板塊/籌碼呼叫限流與跨日快取修復** — 新增的 `trade_cal`、行業板塊排行、籌碼分佈鏈路統一接入 `_check_rate_limit()`；交易日曆快取改為按自然日重新整理，避免服務跨天執行後繼續沿用舊交易日判斷取數日期。
- 💼 **持倉超售攔截與錯誤流水恢復**（#718）— `POST /api/v1/portfolio/trades` 現在會在寫入前校驗可賣數量，超售返回 `409 portfolio_oversell`；持倉頁新增交易 / 資金流水 / 公司行為刪除能力，刪除後會同步失效倉位快取與未來快照，便於從錯誤流水中直接恢復。
- 📧 **郵件中文發件人名編碼**（#708）— 郵件通知現在會對包含中文的 `EMAIL_SENDER_NAME` 自動做 RFC 2047 編碼，並在異常路徑補充 SMTP 連線清理，修復 GitHub Actions / QQ SMTP 下 `'ascii' codec can't encode characters` 導致的傳送失敗。
- 🐛 **港股 Agent 實時行情去重與快速路由** — 統一 `HK01810` / `1810.HK` / `01810` 等港股程式碼歸一規則；港股實時行情改為直接走單次 `akshare_hk` 路徑，避免按 A 股 source priority 重複觸發同一失敗介面；Agent 執行期對顯式 `retriable=false` 的工具失敗增加短路快取，減少同輪分析中的重複失敗呼叫。
- 📰 **新聞時效硬過濾與策略分窗**（#697）— 新增 `NEWS_STRATEGY_PROFILE`（`ultra_short/short/medium/long`）並與 `NEWS_MAX_AGE_DAYS` 統一計算有效視窗；搜尋結果在返回後執行釋出時間硬過濾（時間未知剔除、超窗剔除、未來僅容忍 1 天），並在歷史 fallback 鏈路追加相同約束，避免舊聞再次進入“最新動態/風險警報”。

### 文件

- ☁️ **新增雲伺服器 Web 介面部署與訪問教程**（Fixes #686）— 補充從雲端部署到外部訪問的落地說明，降低遠端自託管門檻。
- 🌍 **補齊英文文件索引與協作文件** — 新增英文文件索引、貢獻指南、Bot 命令文件，並補充中英雙語 issue / PR 模板，方便中英文協作與外部貢獻者理解專案入口。
- 🏷️ **本地化 README 補充 Trendshift badge** — 在多語言 README 中同步補上新版能力入口標識，減少中英文說明面不一致。

## [3.7.0] - 2026-03-15

### 新功能

- 💼 **持倉管理 P0 全功能上線**（#677，對應 Issue #627）
  - **核心賬本與快照閉環**：新增賬戶、交易、現金流水、企業行為、持倉快取、每日快照等核心資料模型與 API 端點；支援 FIFO / AVG 雙成本法回放；同日事件順序固定為 `現金 → 企業行為 → 交易`；持倉快照寫入採用原子事務。
  - **券商 CSV 匯入**：支援華泰 / 中信 / 招商首批適配，含列名別名相容；兩階段介面（解析預覽 + 確認提交）；`trade_uid` 優先、key-field hash 兜底的冪等去重；前導零股票程式碼完整保留。
  - **組合風險報告**：集中度風險（Top Positions + A 股板塊口徑）、歷史回撤監控（支援回填缺失快照）、止損接近預警；多幣種統一換算 CNY 口徑；汲取失敗時回退最近成功匯率並標記 stale。
  - **Web 持倉頁**（`/portfolio`）：組合總覽、持倉明細、集中度餅圖、風險摘要、全組合 / 單賬戶切換；手工錄入交易 / 資金流水 / 企業行為；內嵌賬戶建立入口；CSV 解析 + 提交閉環與券商選擇器。
  - **Agent 持倉工具**：新增 `get_portfolio_snapshot` 資料工具，預設緊湊摘要，可選持倉明細與風險資料。
  - **事件查詢 API**：新增 `GET /portfolio/trades`、`GET /portfolio/cash-ledger`、`GET /portfolio/corporate-actions`，支援日期過濾與分頁。
  - **可擴充套件 Parser Registry**：應用級共享註冊，支援執行時註冊新券商；新增 `GET /portfolio/imports/csv/brokers` 發現介面。

- 🎨 **前端設計系統與原子元件庫**（#662）
  - 引入漸進式雙主題架構（HSL 變數化設計令牌），清理歷史 Legacy CSS；重構 Button / Card / Badge / Collapsible / Input / Select 等 20+ 核心元件；新增 `clsx` + `tailwind-merge` 類名合併工具；提升歷史記錄、LLM 配置等頁面可讀性。

- ⚡ **分析 API 非同步契約與啟動最佳化**（#656）
  - 規範 `POST /api/v1/analysis/analyze` 非同步請求的返回契約；最佳化服務啟動輔助邏輯；修復前端報告型別聯合定義與後端響應對齊問題。

### 修復

- 🔔 **Discord 環境變數向後相容**（#659）：執行時新增 `DISCORD_CHANNEL_ID` → `DISCORD_MAIN_CHANNEL_ID` 的 fallback 讀取；歷史配置使用者無需修改即可恢復 Discord Bot 通知；全部相關文件與 `.env.example` 對齊。
- 🔧 **GitHub Actions Node 24 升級**（#665）：將所有 GitHub 官方 actions 升級至 Node 24 相容版本，消除 CI 日誌中的 Node.js 20 deprecation warning（影響 2026-06-02 強制升級視窗）。
- 📅 **持倉頁預設日期本地化**：手工錄入表單預設日期改用本地時間（`getFullYear/Month/Date`），修復 UTC-N 時區使用者在當天晚間出現日期偏移的問題。
- 🔁 **CSV 匯入去重邏輯加固**：dedup hash 納入行序號作為區分因子，確保同欄位合法分筆成交不被誤摺疊；同時在 `trade_uid` 存在時也持久化 hash，防止混合來源重複寫入。

### 變更

- `POST /api/v1/portfolio/trades` 在同賬戶內 `trade_uid` 衝突時返回 `409`。
- 持倉風險響應新增 `sector_concentration` 欄位（增量擴充套件），原有 `concentration` 欄位保持不變。
- 分析 API `analyze` 介面非同步行為契約文件化；前端報告型別聯合更新。

### 測試

- 新增持倉核心服務測試（FIFO / AVG 部分賣出、同日事件順序、重複 `trade_uid` 返回 409、快照 API 契約）。
- 新增 CSV 匯入冪等性、合法分筆成交不誤去重、去重邊界、風險閾值邊界、匯率降級行為測試。
- 新增 Agent `get_portfolio_snapshot` 工具呼叫測試。
- 新增分析 API 非同步契約迴歸測試。

## [3.6.0] - 2026-03-14

### Added
- 📊 **Web UI Design System** — implemented dual-theme architecture and terminal-inspired atomic UI components
- 📊 **UI Components Refactoring** — integrated `clsx` and `tailwind-merge` for robust class composition across Web UI

- 🗑️ **History batch deletion** — Web UI now supports multi-selection and batch deletion of analysis history; added `POST /api/v1/history/batch-delete` endpoint and `ConfirmDialog` component.
- 🔐 **Auth settings API** — new `POST /api/v1/auth/settings` endpoint to enable or disable Web authentication at runtime and set the initial admin password when needed
- openclaw Skill 整合指南 — 新增 [docs/openclaw-skill-integration.md](openclaw-skill-integration.md)，說明如何透過 openclaw Skill 呼叫 DSA API
- ⚙️ **LLM channel protocol/test UX** — `.env` and Web settings now share the same channel shape (`LLM_CHANNELS` + `LLM_<NAME>_PROTOCOL/BASE_URL/API_KEY/MODELS/ENABLED`); settings page adds per-channel connection testing, primary/fallback/vision model selection, and protocol-aware model prefixing
- 🤖 **Agent architecture Phase 0+1** — shared protocols (`AgentContext`, `AgentOpinion`, `StageResult`), extracted `run_agent_loop()` runner, `AGENT_ARCH` switch (`single`/`multi`), config registry entries
- 🔍 **Bot NL routing** — two-layer natural-language routing: cheap regex pre-filter (stock codes + finance keywords) → lightweight LLM intent parsing; controlled by `AGENT_NL_ROUTING=true`; supports multi-stock and strategy extraction
- 💬 **`/ask` multi-stock analysis** — comma or `vs` separated codes (max 5), parallel thread execution with 150s timeout (preserves partial results), Markdown comparison summary table at top
- 📋 **`/history` command** — per-user session isolation via `{platform}_{user_id}:{scope}` format (colon delimiter prevents prefix collision); lists both `/chat` and `/ask` sessions; view detail or clear
- 📊 **`/strategies` command** — lists available strategy YAML files grouped by category (趨勢/形態/反轉/框架) with ✅/⬜ activation status
- 🔧 **Backtest summary tools** — `get_strategy_backtest_summary` and `get_stock_backtest_summary` registered as read-only Agent tools
- ⚙️ **Agent auto-detection** — `is_agent_available()` auto-detects from `LITELLM_MODEL`; explicit `AGENT_MODE=true/false` takes full precedence
- 🏗️ **Multi-Agent orchestrator (Phase 2)** — `AgentOrchestrator` with 4 modes (`quick`/`standard`/`full`/`strategy`); drop-in replacement for `AgentExecutor` via `AGENT_ARCH=multi`; `BaseAgent` ABC with tool subset filtering, cached data injection, and structured `AgentOpinion` output
- 🧩 **Specialised agents (Phase 2-4)** — `TechnicalAgent` (8 tools, trend/MA/MACD/volume/pattern analysis), `IntelAgent` (news & sentiment, risk flag propagation), `DecisionAgent` (synthesis into Decision Dashboard JSON), `RiskAgent` (7 risk categories, two-level severity with soft/hard override)
- 📈 **Strategy system (Phase 3)** — `StrategyAgent` (per-strategy evaluation from YAML skills), `StrategyRouter` (rule-based regime detection → strategy selection), `StrategyAggregator` (weighted consensus with backtest performance factor)
- 🔬 **Deep Research agent (Phase 5)** — `ResearchAgent` with 3-phase approach (decompose → research sub-questions → synthesise report); token budget tracking; new `/research` bot command with aliases (`/深研`, `/deepsearch`)
- 🧠 **Memory & calibration (Phase 6)** — `AgentMemory` with prediction accuracy tracking, confidence calibration (activates after minimum sample threshold), strategy auto-weighting based on historical win rate
- 📊 **Portfolio Agent (Phase 7)** — `PortfolioAgent` for multi-stock portfolio analysis (position sizing, sector concentration, correlation risk, cross-market linkage, rebalance suggestions)
- 🔔 **Event-driven alerts (Phase 7)** — `EventMonitor` with `PriceAlert`, `VolumeAlert`, `SentimentAlert` rules; async checking, callback notifications, serializable persistence
- ⚙️ **New config entries** — `AGENT_ORCHESTRATOR_MODE`, `AGENT_RISK_OVERRIDE`, `AGENT_DEEP_RESEARCH_BUDGET`, `AGENT_MEMORY_ENABLED`, `AGENT_STRATEGY_AUTOWEIGHT`, `AGENT_STRATEGY_ROUTING` — all registered in `config.py` + `config_registry.py` (WebUI-configurable)

### Changed
- 🔐 **Auth password state semantics** — stored password existence is now tracked independently from auth enablement; when auth is disabled, `/api/v1/auth/status` returns `passwordSet=false` while preserving the saved password for future re-enable
- 🔐 **Auth settings re-enable hardening** — re-enabling auth with a stored password now requires `currentPassword`, and failed session creation rolls back the auth toggle to avoid lockout
- ♻️ **AgentExecutor refactored** — `_run_loop` delegates to shared `runner.run_agent_loop()`; removed duplicated serialization/parsing/thinking-label code
- ♻️ **Unified agent switch** — Bot, API, and Pipeline all use `config.is_agent_available()` instead of divergent `config.agent_mode` checks
- 📖 **README.md** — expanded Bot commands section (ask/chat/strategies/history), added NL routing note, updated agent mode description
- 📖 **.env.example** — added `AGENT_ARCH` and `AGENT_NL_ROUTING` configuration documentation
- 🔌 **Analysis API async contract** — `POST /api/v1/analysis/analyze` now documents distinct async `202` payloads for single-stock vs batch requests, and `report_type=full` is treated consistently with the existing full-report behavior

### Fixed
- 🐛 **Analysis API blank-code guardrails** — `POST /api/v1/analysis/analyze` now drops whitespace-only entries before batch enqueue and returns `400` when no valid stock code remains
- 🐛 **Bare `/api` SPA fallback** — unknown API paths now return JSON `404` consistently for both `/api/...` and the exact `/api` path
- 🎮 **Discord channel env compatibility** — runtime now accepts legacy `DISCORD_CHANNEL_ID` as a fallback for `DISCORD_MAIN_CHANNEL_ID`, and the docs/examples now use the same variable name as the actual workflow/config implementation
- 🐛 **Session secret rotation on Windows** — use atomic replace so auth toggles invalidate existing sessions even when `.session_secret` already exists
- 🐛 **Auth toggle atomicity** — persist `ADMIN_AUTH_ENABLED` before rotating session secret; on rotation failure, roll back to the previous auth state
- 🔧 **LLM runtime selection guardrails** — YAML 模式下渠道編輯器不再覆蓋 `LITELLM_MODEL` / fallback / Vision；系統配置校驗補上全部渠道禁用後的執行時來源檢查，並修復 `vertexai/...` 這類協議別名模型被重複加字首的問題
- 🐛 **Multi-stock `/ask` follow-up regressions** — portfolio overlay now shares the same timeout budget as the per-stock phase and is skipped on timeout instead of blocking the bot reply; `/history` now stores the readable per-stock summary instead of raw dashboard JSON; condensed multi-stock output now renders numeric `sniper_points` values
- 🐛 **Decision dashboard enum compatibility** — multi-agent `DecisionAgent` now keeps `decision_type` within the legacy `buy|hold|sell` contract and normalizes stray `strong_*` outputs before risk override, pipeline conversion, and downstream統計/通知彙總
- 🛟 **Multi-Agent partial-result fallback** — `IntelAgent` now caches parsed intel for downstream reuse, shared JSON parsing tolerates lightly malformed model output, and the orchestrator preserves/synthesizes a minimal dashboard on timeout or mid-pipeline parse failure instead of always collapsing to `50/觀望/未知`
- 🐛 **Shared LiteLLM routing restored** — bot NL intent parsing and `ResearchAgent` planning/synthesis now reuse the same LiteLLM adapter / Router / fallback / `api_base` injection path as the main Agent flow, so `LLM_CHANNELS` / `LITELLM_CONFIG` / OpenAI-compatible deployments behave consistently
- 🐛 **Bot chat session backward compatibility** — `/chat` now keeps using the legacy `{platform}_{user_id}` session id when old history already exists, and `/history` can still list / view / clear those pre-migration sessions alongside the new `{platform}_{user_id}:chat` format
- 🐛 **EventMonitor unsupported rule rejection** — config validation/runtime loading now reject or skip alert types the monitor cannot actually evaluate yet, so schedule mode no longer silently accepts permanent no-op rules
- 🐛 **P0 基本面聚合穩定性修復** (#614) — 修復 `get_stock_info` 板塊語義迴歸（新增 `belong_boards` 並保留 `boards` 相容別名）、引入基本面上下文精簡返回以控制 token、為基本面快取增加最大條目淘汰，並補齊 ETF 總體狀態聚合與 NaN 板塊欄位過濾，保證 fail-open 與最小入侵。
- 🔧 **GitHub Actions 搜尋引擎環境變數補充** — 工作流新增 `MINIMAX_API_KEYS`、`BRAVE_API_KEYS`、`SEARXNG_BASE_URLS` 環境變數對映，使 GitHub Actions 使用者可配置 MiniMax、Brave、SearXNG 搜尋服務（此前 v3.5.0 已新增 provider 實現但缺少工作流配置）
- 🤖 **Multi-Agent runtime consistency** — `AGENT_MAX_STEPS` now propagates to each orchestrated sub-agent; added cooperative `AGENT_ORCHESTRATOR_TIMEOUT_S` budget to stop overlong pipelines before they cascade further
- 🔌 **Multi-Agent feature wiring** — `AGENT_RISK_OVERRIDE` now actively downgrades final dashboards on hard risk findings; `AGENT_MEMORY_ENABLED` now injects recent analysis memory + confidence calibration into specialised agents; multi-stock `/ask` now runs `PortfolioAgent` to add portfolio-level allocation and concentration guidance
- 🔔 **EventMonitor runtime wiring** — schedule mode can now load alert rules from `AGENT_EVENT_ALERT_RULES_JSON`, poll them at `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`, and send triggered alerts through the existing notification service
- 🛠️ **Follow-up stability fixes** — multi-stock `/ask` now falls back to usable text output when dashboard JSON parsing fails; EventMonitor skips semantically invalid rules instead of aborting schedule startup; background alert polling now runs independently of the main scheduled analysis loop
- 🧪 **Multi-Agent regression coverage** — added orchestrator execution tests for `run()`, `chat()`, critical-stage failure, graceful degradation, and timeout handling
- 🧹 **PortfolioAgent cleanup** — `post_process()` now reuses shared JSON parsing and removed stale unused imports
- 🚦 **Bot async dispatch** — `CommandDispatcher` now exposes `dispatch_async()`; NL intent parsing and default command execution are offloaded from the event loop, DingTalk stream awaits async handlers directly, and Feishu stream processing is moved off the SDK callback thread
- 🌐 **Async webhook handler** — new `handle_webhook_async()` function in `bot/handler.py` for use from async contexts (e.g. FastAPI); calls `dispatch_async()` directly without thread bridging
- 🧵 **Feishu stream ThreadPoolExecutor** — replaced unbounded per-message `Thread` spawning with a capped `ThreadPoolExecutor(max_workers=8)` to prevent thread explosion under message bursts
- 🔒 **EventMonitor safety** — `_check_volume()` now safely handles `get_daily_data` returning `None` (no tuple-unpacking crash); `on_trigger` callbacks support both sync and async callables via `asyncio.to_thread`/`await`
- 🧹 **ResearchAgent dedup** — `_filtered_registry()` now delegates to `BaseAgent._filtered_registry()` instead of duplicating the filtering logic
- 🧹 **Bot trailing whitespace cleanup** — removed W291/W293 whitespace issues across `bot/handler.py`, `bot/dispatcher.py`, `bot/commands/base.py`, `bot/platforms/feishu_stream.py`, `bot/platforms/dingtalk_stream.py`
- 🐛 **Dispatcher `_parse_intent_via_llm` safety** — replaced fragile `'raw' in dir()` with `'raw' in locals()` for undefined-variable guard in `JSONDecodeError` handler
- 🐛 **籌碼結構 LLM 未填寫時兜底補全** (#589) — DeepSeek 等模型未正確填寫 `chip_structure` 時，自動用資料來源已獲取的籌碼資料補全，保證各模型展示一致；普通分析與 Agent 模式均生效
- 🐛 **歷史報告狙擊點位顯示原始文字** (#452) — 歷史詳情頁現優先展示 `raw_result.dashboard.battle_plan.sniper_points` 中的原始字串，避免 `analysis_history` 數值列把區間、說明文字或複雜點位壓縮成單個數字；保留原有數值列作為回退
- 🐛 **Session prefix collision** — user ID `123` could see sessions of user `1234` via `startswith`; fixed with colon delimiter in session_id format
- 🐛 **NL pre-filter false positives** — `re.IGNORECASE` caused `[A-Z]{2,5}` to match common English words like "hello"; removed global flag, use inline `(?i:...)` only for English finance keywords
- 🐛 **Dotted ticker in strategy args** — `_get_strategy_args()` didn't recognize `BRK.B` as a stock code, leaving it in strategy text; now accepts `TICKER.CLASS` format
- ⏱️ **efinance 長呼叫掛起修復** (#660) — 為所有 efinance API 呼叫引入 `_ef_call_with_timeout()` 包裝（預設 30 秒，可透過 `EFINANCE_CALL_TIMEOUT` 配置）；使用 `executor.shutdown(wait=False)` 確保超時後不再阻塞主執行緒，徹底消除 81 分鐘掛起問題
- 🛡️ **型別安全內容完整性檢查** (#660) — `check_content_integrity()` 現在將非字串型別的 `operation_advice` / `analysis_summary` 視為缺失欄位，避免下游 `get_emoji()` 因 `dict.strip()` 崩潰
- 📄 **報告儲存與通知解耦** (#660) — `_save_local_report()` 不再依賴 `send_notification` 標誌觸發，`--no-notify` 模式下本地報告照常儲存
- 🔄 **operation_advice 字典歸一化** (#660) — Pipeline 和 BacktestEngine 現在將 LLM 返回的 `dict` 格式 `operation_advice` 透過 `decision_type`（不區分大小寫）對映為標準字串，防止因模型輸出格式變化導致崩潰
- 🛡️ **runner.py usage None 防護** (#660) — `response.usage` 為 `None` 時不再丟擲 `AttributeError`，回退為 0 token 計數
- 📋 **orchestrator 靜默失敗改為日誌警告** (#660) — `IntelAgent` / `RiskAgent` 階段失敗現在記錄 `WARNING` 而非靜默跳過，便於診斷

### Notes
- ⚠️ **Multi-worker auth toggles** — runtime auth updates are process-local; multi-worker deployments must restart/roll workers to keep auth state consistent

## [3.5.0] - 2026-03-12

### Added
- 📊 **Web UI full report drawer** (Fixes #214) — history page adds "Full Report" button to display the complete Markdown analysis report in a side drawer; new `GET /api/v1/history/{record_id}/markdown` endpoint
- 📊 **LLM cost tracking** — all LLM calls (analysis, agent, market review) recorded in `llm_usage` table; new `GET /api/v1/usage/summary?period=today|month|all` endpoint returns aggregated token usage by call type and model
- 🔍 **SearXNG search provider** (Fixes #550) — quota-free self-hosted search fallback; priority: Bocha > Tavily > Brave > SerpAPI > MiniMax > SearXNG
- 🔍 **MiniMax web search provider** — `MiniMaxSearchProvider` with circuit breaker (3 failures → 300s cooldown) and dual time-filtering; configured via `MINIMAX_API_KEYS`
- 🤖 **Agent models discovery API** — `GET /api/v1/agent/models` returns available model deployments (primary/fallback/source/api_base) for Web UI model selector
- 🤖 **Agent chat export & send** (#495) — export conversation to .md file; send to configured notification channels; new `POST /api/v1/agent/chat/send`
- 🤖 **Agent background execution** (#495) — analysis continues when switching pages; badge notification on completion; auto-cancel in-progress stream on session switch
- 📝 **Report Engine P0** — Pydantic schema validation for LLM JSON; Jinja2 templates (markdown/wechat/brief) with legacy fallback; content integrity checks with retry; brief mode (`REPORT_TYPE=brief`); history signal comparison
- 📦 **Smart import** — multi-source import from image/CSV/Excel/clipboard; Vision LLM extracts code+name+confidence; name→code resolver (local map + pinyin + AkShare); confidence-tiered confirmation
- ⚙️ **GitHub Actions LiteLLM config** — workflow supports `LITELLM_CONFIG`/`LITELLM_CONFIG_YAML` for flexible AI provider configuration
- ⚙️ **Config engine refactor & system API** (#602) — unified config registry, validation and API exposure
- 📖 **LLM configuration guide** — new `docs/LLM_CONFIG_GUIDE.md` covering 3-tier config, quick start, Vision/Agent/troubleshooting

### Fixed
- 🐛 **analyze_trend always reports No historical data** (#600) — now fetches from DB/DataFetcher instead of broken `get_analysis_context`
- 🐛 **Chip structure fallback when LLM omits it** (#589) — auto-fills from data source chip data for consistent display across models
- 🐛 **History sniper points show raw text** (#452) — prioritizes original strings over compressed numeric values
- 🐛 **GitHub Actions ENABLE_CHIP_DISTRIBUTION configurable** (#617) — no longer hardcoded, supports vars/secrets override
- 🐛 **`.env` save preserves comments and blank lines** — Web settings no longer destroys `.env` formatting
- 🐛 **Agent model discovery fixes** — legacy mode includes LiteLLM-native providers; source detection aligned with runtime; fallback deployments no longer expanded per-key
- 🐛 **Stooq US stock previous close semantics** — no longer misuses open price as previous close
- 🐛 **Stock name prefetch regression** — prioritizes local `STOCK_NAME_MAP` before remote queries
- 🐛 **AkShare limit-up/down calculation** (#555) — fixed market analysis statistics
- 🐛 **AkShare Tencent source field index & ETF quote mapping** (#579)
- 🐛 **Pytdx stock name cache pagination** (#573) — prevents cache overflow
- 🐛 **PushPlus oversized report chunking** (#489) — auto-segments long content
- 🐛 **Agent chat cancel & switch** (#495) — cancel no longer misreports as failure; fast switch no longer overwrites stream state
- 🐛 **MiniMax search status in `/status` command** (#587)
- 🐛 **config_registry duplicate BOCHA_API_KEYS** — removed duplicate dict entry that silently overwrote config

### Changed
- 🔎 **Fetcher failure observability** — logs record start/success/failure with elapsed time, failover transitions; Efinance/Akshare include upstream endpoint and classified failure categories
- ♻️ **Data source resilience & cleanup** (#602) — fallback chain optimization
- ♻️ **Image extract API response extension** — new `items` field (code/name/confidence); `codes` preserved for backward compatibility
- ♻️ **Import parse error messages** — specific failure reasons for Excel/CSV; improved logging with file type and size

### Docs
- 📖 LLM config guide refactored for clarity (#583)
- 📖 `image-extract-prompt.md` with full prompt documentation
- 📖 AkShare fallback cache TTL documentation
## [3.4.10] - 2026-03-07

### Fixed
- 🐛 **EfinanceFetcher ETF OHLCV data** (#541, #527) — switch `_fetch_etf_data` from `ef.fund.get_quote_history` (NAV-only, no OHLCV, no `beg`/`end` params) to `ef.stock.get_quote_history`; ETFs now return proper open/high/low/close/volume/amount instead of zeros; remove obsolete NAV column mappings from `_normalize_data`
- 🐛 **tiktoken 0.12.0 `Unknown encoding cl100k_base`** (#537) — pin `tiktoken>=0.8.0,<0.12.0` in requirements.txt to avoid plugin-registration regression introduced in 0.12.0
- 🐛 **Web UI API error classification** (#540) — frontend no longer treats every HTTP 400 as the same "server/network" failure; now distinguishes Agent disabled / missing params / model-tool incompatibility / upstream LLM errors / local connection failures
- 🐛 **北交所程式碼識別失敗** (#491, #533) — 8/4/92 開頭的 6 位程式碼現正確識別為北交所；Tushare/Akshare/Yfinance 等資料來源支援 .BJ 或 bj 字首；Baostock/Pytdx 對北交所程式碼顯式切換資料來源；避免誤判上海 B 股 900xxx
- 🐛 **狙擊點位解析錯誤** (#488, #532) — 理想買入/二次買入等欄位在無「元」字時誤提取括號內技術指標數字；現先截去第一個括號後內容再提取

### Added
- **Markdown-to-image for dashboard report** (#455, #535) — 個股日報彙總支援 markdown 轉圖片推送（Telegram、WeChat、Custom、Email），與大盤覆盤行為一致
- **markdown-to-file engine** (#455) — `MD2IMG_ENGINE=markdown-to-file` 可選，對 emoji 支援更好，需 `npm i -g markdown-to-file`
- **PREFETCH_REALTIME_QUOTES** (#455) — 設為 `false` 可禁用實時行情預取，避免 efinance/akshare_em 全市場拉取
- **Stock name prefetch** (#455) — 分析前預取股票名稱，減少報告中「股票xxxxx」佔位符
- 📊 **分析報告模型標記** (#528, #534) — 在分析報告 meta、報告末尾、推送內容中展示 `model_used`（完整 LLM 模型名）；Agent 多輪呼叫時記錄並展示每輪實際使用的模型（支援 fallback 切換）

### Changed
- **Enhanced markdown-to-image failure warning** (#455) — 轉圖失敗時提示具體依賴（wkhtmltopdf 或 m2f）
- **WeChat-only image routing optimization** (#455) — 僅配置企業微信圖片時，不再對完整報告做冗餘轉圖，避免誤導性失敗日誌
- **Stock name prefetch lightweight mode** (#455) — 名稱預取階段跳過 realtime quote 查詢，減少額外網路開銷

## [3.4.9] - 2026-03-06

### Added
- 🧠 **Structured config validation** — `ConfigIssue` dataclass and `validate_structured()` with severity-aware logging; `CONFIG_VALIDATE_MODE=strict` aborts startup on errors
- 🖼️ **Vision model config** — `VISION_MODEL` and `VISION_PROVIDER_PRIORITY` for image stock extraction; provider fallback (Gemini → Anthropic → OpenAI → DeepSeek) when primary fails
- 🚀 **CLI init wizard** — `python -m dsa init` 3-step interactive bootstrap (model → data source → notification), 9 provider presets, incremental merge by default
- 🔧 **Multi-channel LLM support** with visual channel editor (#494)

### Changed
- ♻️ **Vision extraction** — migrated from gemini-3 hardcode to `litellm.completion()` with configurable model and provider fallback; `OPENAI_VISION_MODEL` deprecated in favor of `VISION_MODEL`
- ♻️ **Market analyzer** — uses `Analyzer.generate_text()` for LLM calls; fixes bypass and Anthropic `AttributeError` when using non-Router path
- ♻️ **Config validation refinements** — test_env output format syncs with `validate_structured` (severity-aware ✓/✗/⚠/·); Vision key warning when `VISION_MODEL` set but no provider API key; market_analyzer test covers `generate_market_review` fallback when `generate_text` returns None
- ⚙️ **Auto-tag workflow defaults to NO tag** — only tags when commit message explicitly contains `#patch`, `#minor`, or `#major`
- ♻️ **Formatter and notification refactor** (#516)

### Fixed
- 🐛 **STOCK_LIST not refreshed on scheduled runs** — `.env` or WebUI changes to `STOCK_LIST` now hot-reload before each scheduled analysis (#529)
- 🐛 **WebUI fails to load with MIME type error** — SPA fallback route now resolves correct `Content-Type` for JS/CSS files (#520)
- 🐛 **AstrBot sender docstring misplaced** — `import time` placed before docstring in `_send_astrbot`, causing it to become dead code
- 🐛 **Telegram Markdown link escaping** — `_convert_to_telegram_markdown` escaped `[]()` characters, breaking all Markdown links in reports
- 🐛 **Duplicate `discord_bot_status` field** in Config dataclass — second declaration silently shadowed the first
- 🧹 **Unused imports** — removed `shutil`/`subprocess` from `main.py`
- 🔧 **Config validation and Vision key check** (#525)

### Docs
- 📝 Clarified GitHub Actions non-trading-day manual run controls (`TRADING_DAY_CHECK_ENABLED` + `force_run`) for Issue #461 / PR #466

## [3.4.8] - 2026-03-02

### Fixed
- 🐛 **Desktop exe crashes on startup with `FileNotFoundError`** — PyInstaller build was missing litellm's JSON data files (e.g. `model_prices_and_context_window_backup.json`). Added `--collect-data litellm` to both Windows and macOS build scripts so the files are correctly bundled in the executable.

### CI
- 🔧 Cache Electron binaries on macOS CI runners to prevent intermittent EOF download failures when fetching `electron-vX.Y.Z-darwin-*.zip` from GitHub CDN
- 🔧 Fix macOS DMG `hdiutil Resource busy` error during desktop packaging

### Docs
- 📝 Clarify non-trading-day manual run controls for GitHub Actions (`TRADING_DAY_CHECK_ENABLED` + `force_run`) (#474)

## [3.4.7] - 2026-02-28

### Added
- 🧠 **CN/US Market Strategy Blueprint System** (#395) — market review prompt injects region-specific strategy blueprints with position sizing and risk trigger recommendations

### Fixed
- 🐛 **`TRADING_DAY_CHECK_ENABLED` env var and `--force-run` for GitHub Actions** (#466)
- 🐛 **Agent pipeline preserved resolved stock names** (#464) — placeholder names no longer leak into reports
- 🐛 **Code cleanup** (#462, Fixes #422)
- 🐛 **WebUI auto-build on startup** (#460)
- 🐛 **ARCH_ARGS unbound variable** (#458)
- 🐛 **Time zone inconsistency & right panel flash** (#439)

### Docs
- 📝 Clarify potential ambiguities in code (#343)
- 📝 ENABLE_EASTMONEY_PATCH guidance for Issue #453 (#456)

## [3.4.0] - 2026-02-27

### Added
- 📡 **LiteLLM Direct Integration + Multi API Key Support** (#454, Fixes #421 #428)
  - Removed native SDKs (google-generativeai, google-genai, anthropic); unified through `litellm>=1.80.10`
  - New config: `LITELLM_MODEL`, `LITELLM_FALLBACK_MODELS`, `GEMINI_API_KEYS`, `ANTHROPIC_API_KEYS`, `OPENAI_API_KEYS`
  - Multi-key auto-builds LiteLLM Router (simple-shuffle) with 429 cooldown
  - **Breaking**: `.env` `GEMINI_MODEL` (no prefix) only for fallback; explicit config must include provider prefix

### Changed
- ♻️ **Notification Refactoring** (#435) — extracted 10 sender classes into `src/notification_sender/`

### Fixed
- 🐛 LLM NoneType crash, history API 422, sniper points extraction
- 🐛 Auto-build frontend on WebUI startup — `WEBUI_AUTO_BUILD` env var (default `true`)
- 🐛 Docker explicit project name (#448)
- 🐛 Bocha search SSL retry (#445, #446) — transient errors retry up to 3 times
- 🐛 Gemini google-genai SDK migration (Fixes #440, #444)
- 🐛 Mobile home page scrolling (Fixes #419, #433)
- 🐛 History list scroll reset (#431)
- 🐛 Settings save button false positive (fixes #417, #430)

## [3.3.22] - 2026-02-26

### Added
- 💬 **Chat History Persistence** (Fixes #400, #414) — `/chat` page survives refresh, sidebar session list
- 🎨 Project VI Assets — logo icon set, PSD, vector, banner (#425)
- 🚀 Desktop CI Auto-Release (#426) — Windows + macOS parallel builds

### Fixed
- 🐛 Agent Reasoning 400 & LiteLLM Proxy (fixes #409, #427)
- 🐛 Discord chunked sending (#413) — `DISCORD_MAX_WORDS` config
- 🐛 yfinance shared DataFrame (#412)
- 🐛 sniper_points parsing (#408)
- 🐛 Agent framework category missing (#406)
- 🐛 Date inconsistency & query id (fixes #322, #363)

## [3.3.12] - 2026-02-24

### Added
- 📈 **Intraday Realtime Technical Indicators** (Issue #234, #397) — MA calculated from realtime price, config: `ENABLE_REALTIME_TECHNICAL_INDICATORS`
- 🤖 **Agent Strategy Chat** (#367) — full ReAct pipeline, 11 YAML strategies, SSE streaming, multi-turn chat
- 📢 PushPlus Group Push — `PUSHPLUS_TOPIC` (#402)
- 📅 Trading Day Check (Issue #373, #375) — `TRADING_DAY_CHECK_ENABLED`, `--force-run`

### Fixed
- 🐛 DeepSeek reasoning mode (Issue #379, #386)
- 🐛 Agent news intel persistence (Fixes #396, #405)
- 🐛 Bare except clauses replaced with `except Exception` (#398)
- 🐛 UUID fallback for HTTP non-secure context (fixes #377, #381)
- 🐛 Docker DNS resolution (Fixes #372, #374)
- 🐛 Agent session/strategy bugs — multiple follow-up fixes for #367
- 🐛 yfinance parallel download data filtering

### Changed
- Market review strategy consistency — unified cn/us template
- Agent test assertions updated (`6 -> 11`)


## [3.2.11] - 2026-02-23

### 修復（#patch）
- 🐛 **StockTrendAnalyzer 從未執行** (Issue #357)
  - 根因：`get_analysis_context` 僅返回 2 天資料且無 `raw_data`，pipeline 中 `raw_data in context` 始終為 False
  - 修復：Step 3 直接呼叫 `get_data_range` 獲取 90 日曆天（約 60 交易日）歷史資料用於趨勢分析
  - 改善：趨勢分析失敗時用 `logger.warning(..., exc_info=True)` 記錄完整 traceback

## [3.2.10] - 2026-02-22

### 新增
- ⚙️ 支援 `RUN_IMMEDIATELY` 配置項，設為 `true` 時定時任務觸發後立即執行一次分析，無需等待首個定時點

### 修復
- 🐛 修復 Web UI 頁面居中問題
- 🐛 修復 Settings 返回 500 錯誤

## [3.2.9] - 2026-02-22

### 修復
- 🐛 **ETF 分析僅關注指數走勢**（Issue #274）
  - 美股/港股 ETF（如 VOO、QQQ）與 A 股 ETF 不再納入基金公司層面風險（訴訟、聲譽等）
  - 搜尋維度：ETF/指數專用 risk_check、earnings、industry 查詢，避免命中基金管理人新聞
  - AI 提示：指數型標的分析約束，`risk_alerts` 不得出現基金管理人公司經營風險

## [3.2.8] - 2026-02-21

### 修復
- 🐛 **BOT 與 WEB UI 股票程式碼大小寫統一**（Issue #355）
  - BOT `/analyze` 與 WEB UI 觸發分析的股票程式碼統一為大寫（如 `aapl` → `AAPL`）
  - 新增 `canonical_stock_code()`，在 BOT、API、Config、CLI、task_queue 入口處規範化
  - 歷史記錄與任務去重邏輯可正確識別同一股票（大小寫不再影響）

## [3.2.7] - 2026-02-20

### 新增
- 🔐 **Web 頁面密碼驗證**（Issue #320, #349）
  - 支援 `ADMIN_AUTH_ENABLED=true` 啟用 Web 登入保護
  - 首次訪問在網頁設定初始密碼；支援「系統設定 > 修改密碼」和 CLI `python -m src.auth reset_password` 重置

## [3.2.6] - 2026-02-20
### ⚠️ 破壞性變更（Breaking Changes）

- **歷史記錄 API 變更 (Issue #322)**
  - 路由變更：`GET /api/v1/history/{query_id}` → `GET /api/v1/history/{record_id}`
  - 引數變更：`query_id` (字串) → `record_id` (整數)
  - 新聞介面變更：`GET /api/v1/history/{query_id}/news` → `GET /api/v1/history/{record_id}/news`
  - 原因：`query_id` 在批次分析時可能重複，無法唯一標識單條歷史記錄。改用資料庫主鍵 `id` 確保唯一性
  - 影響範圍：使用舊版歷史詳情 API 的所有客戶端需同步更新

### 修復
- 修復美股（如 ADBE）技術指標矛盾：akshare 美股復權資料異常，統一美股歷史資料來源為 YFinance（Issue #311）
- 🐛 **歷史記錄查詢和顯示問題 (Issue #322)**
  - 修復歷史記錄列表查詢中日期不一致問題：使用明天作為 endDate，確保包含今天全天的資料
  - 修復伺服器 UI 報告選擇問題：原因是多條記錄共享同一 `query_id`，導致總是顯示第一條。現改用 `analysis_history.id` 作為唯一標識
  - 歷史詳情、新聞介面及前端元件已全面適配 `record_id`
  - 新增後臺輪詢（每 30s）與頁面可見性變更時靜默重新整理歷史列表，確保 CLI 發起的分析完成後前端能及時同步，使用 `silent` 模式避免觸發 loading 狀態
- 🐛 **美股指數實時行情與日線資料** (Issue #273)
  - 修復 SPX、DJI、IXIC、NDX、VIX、RUT 等美股指數無法獲取實時行情的問題
  - 新增 `us_index_mapping` 模組，將使用者輸入（如 SPX）對映為 Yahoo Finance 符號（如 ^GSPC）
  - 美股指數與美股股票日線資料直接路由至 YfinanceFetcher，避免遍歷不支援的資料來源
  - 消除重複的美股識別邏輯，統一使用 `is_us_stock_code()` 函式

### 最佳化
- 🎨 **首頁輸入欄與 Market Sentiment 佈局對齊最佳化**
  - 股票程式碼輸入框左緣與歷史記錄 glass-card 框左對齊
  - 分析按鈕右緣與 Market Sentiment 外框右對齊
  - Market Sentiment 卡片向下拉伸填滿格子，消除與 STRATEGY POINTS 之間的空隙
  - 窄屏時輸入欄填滿寬度，響應式對齊保持一致

## [3.2.5] - 2026-02-19

### 新增
- 🌍 **大盤覆盤可選區域**（Issue #299）
  - 支援 `MARKET_REVIEW_REGION` 環境變數：`cn`（A股）、`us`（美股）、`both`（兩者）
  - us 模式使用 SPX/納斯達克/道指/VIX 等指數；both 模式可同時覆盤 A 股與美股
  - 預設 `cn`，保持向後相容

## [3.2.4] - 2026-02-18

### 修復
- 🐛 **統一美股資料來源為 YFinance**（Issue #311）
  - akshare 美股復權資料異常，統一美股歷史資料來源為 YFinance
  - 修復 ADBE 等美股股票技術指標矛盾問題

## [3.2.3] - 2026-02-18

### 修復
- 🐛 **標普500實時資料缺失**（Issue #273）
  - 修復 SPX、DJI、IXIC、NDX、VIX、RUT 等美股指數無法獲取實時行情的問題
  - 新增 `us_index_mapping` 模組，將使用者輸入（如 SPX）對映為 Yahoo Finance 符號（如 `^GSPC`）
  - 美股指數與美股股票日線資料直接路由至 YfinanceFetcher，避免遍歷不支援的資料來源

## [3.2.2] - 2026-02-16

### 新增
- 📊 **PE 指標支援**（Issue #296）
  - AI System Prompt 增加 PE 估值關注
- 📰 **新聞時效性篩查**（Issue #296）
  - `NEWS_MAX_AGE_DAYS`：新聞最大時效（天），預設 3，避免使用過時資訊
- 📈 **強勢趨勢股乖離率放寬**（Issue #296）
  - `BIAS_THRESHOLD`：乖離率閾值（%），預設 5.0，可配置
  - 強勢趨勢股（多頭排列且趨勢強度 ≥70）自動放寬乖離率到 1.5 倍

## [3.2.1] - 2026-02-16

### 新增
- 🔧 **東財介面補丁可配置開關**
  - 支援 `EFINANCE_PATCH_ENABLED` 環境變數開關東財介面補丁（預設 `true`）
  - 補丁不可用時可降級關閉，避免影響主流程

## [3.2.0] - 2026-02-15

### 新增
- 🔒 **CI 門禁統一（P0）**
  - 新增 `scripts/ci_gate.sh` 作為後端門禁單一入口
  - 主 CI 改為 `backend-gate`、`docker-build`、`web-gate` 三段式
  - CI 觸發改為所有 PR，避免 Required Checks 因路徑過濾缺失而卡住合併
  - `web-gate` 支援前端路徑變更按需觸發
  - 新增 `network-smoke` 工作流承載非阻斷網路場景迴歸
- 📦 **釋出鏈路收斂（P0）**
  - `docker-publish` 調整為 tag 主觸發，並增加發布前門禁校驗
  - 手動釋出增加 `release_tag` 輸入與 semver/changelog 強校驗
  - 釋出前新增 Docker smoke（關鍵模組匯入）
- 📝 **PR 模板升級（P0）**
  - 增加背景、範圍、驗證命令與結果、回滾方案、Issue 關聯等必填項
- 🤖 **AI 審查覆蓋增強（P0）**
  - `pr-review` 納入 `.github/workflows/**` 範圍
  - 新增 `AI_REVIEW_STRICT` 開關，可選將 AI 審查失敗升級為阻斷

## [3.1.13] - 2026-02-15

### 新增
- 📊 **僅分析結果摘要**（Issue #262）
  - 支援 `REPORT_SUMMARY_ONLY` 環境變數，設為 `true` 時只推送彙總，不含個股詳情
  - 預設 `false`，多股時適合快速瀏覽

## [3.1.12] - 2026-02-15

### 新增
- 📧 **個股與大盤覆盤合併推送**（Issue #190）
  - 支援 `MERGE_EMAIL_NOTIFICATION` 環境變數，設為 `true` 時將個股分析與大盤覆盤合併為一次推送
  - 預設 `false`，減少郵件數量、降低被識別為垃圾郵件的風險

## [3.1.11] - 2026-02-15

### 新增
- 🤖 **Anthropic Claude API 支援**（Issue #257）
  - 支援 `ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL`、`ANTHROPIC_TEMPERATURE`、`ANTHROPIC_MAX_TOKENS`
  - AI 分析優先順序：Gemini > Anthropic > OpenAI
- 📷 **從圖片識別股票程式碼**（Issue #257）
  - 上傳自選股截圖，透過 Vision LLM 自動提取股票程式碼
  - API: `POST /api/v1/stocks/extract-from-image`；支援 JPEG/PNG/WebP/GIF，最大 5MB
  - 支援 `OPENAI_VISION_MODEL` 單獨配置圖片識別模型
- ⚙️ **通達信資料來源手動配置**（Issue #257）
  - 支援 `PYTDX_HOST`、`PYTDX_PORT` 或 `PYTDX_SERVERS` 配置自建通達信伺服器

## [3.1.10] - 2026-02-15

### 新增
- ⚙️ **立即執行配置**（Issue #332）
  - 支援 `RUN_IMMEDIATELY` 環境變數，`true` 時定時任務啟動後立即執行一次
- 🐛 修復 Docker 構建問題

## [3.1.9] - 2026-02-14

### 新增
- 🔌 **東財介面補丁機制**
  - 新增 `patch/eastmoney_patch.py` 修復 efinance 上游介面變更
  - 不影響其他資料來源的正常執行

## [3.1.8] - 2026-02-14

### 新增
- 🔐 **Webhook 證書校驗開關**（Issue #265）
  - 支援 `WEBHOOK_VERIFY_SSL` 環境變數，可關閉 HTTPS 證書校驗以支援自簽名證書
  - 預設保持校驗，關閉存在 MITM 風險，僅建議在可信內網使用

## [3.1.7] - 2026-02-14

### 修復
- 🐛 修復包匯入錯誤（package import error）

## [3.1.6] - 2026-02-13

### 修復
- 🐛 修復 `news_intel` 中 `query_id` 不一致問題

## [3.1.5] - 2026-02-13

### 新增
- 📷 **Markdown 轉圖片通知**（Issue #289）
  - 支援 `MARKDOWN_TO_IMAGE_CHANNELS` 配置，對 Telegram、企業微信、自定義 Webhook（Discord）、郵件傳送圖片格式報告
  - 郵件為內聯附件，增強對不支援 HTML 客戶端的相容性
  - 需安裝 `wkhtmltopdf` 和 `imgkit`

## [3.1.4] - 2026-02-12

### 新增
- 📧 **股票分組發往不同郵箱**（Issue #268）
  - 支援 `STOCK_GROUP_N` + `EMAIL_GROUP_N` 配置，不同股票組報告傳送到對應郵箱
  - 大盤覆盤發往所有配置的郵箱

## [3.1.3] - 2026-02-12

### 修復
- 🐛 修復 Docker 內執行時透過頁面修改配置報錯 `[Errno 16] Device or resource busy` 的問題

## [3.1.2] - 2026-02-11

### 修復
- 🐛 修復 Docker 一致性問題，解決關鍵批次處理與通知 Bug

## [3.1.1] - 2026-02-11

### 變更
- ♻️ `API_HOST` → `WEBUI_HOST`：Docker Compose 配置項統一

## [3.1.0] - 2026-02-11

### 新增
- 📊 **ETF 支援增強與程式碼規範化**
  - 統一各資料來源 ETF 程式碼處理邏輯
  - 新增 `canonical_stock_code()` 統一程式碼格式，確保資料來源路由正確

## [3.0.5] - 2026-02-08

### 修復
- 🐛 修復訊號 emoji 與建議不一致的問題（複合建議如"賣出/觀望"未正確對映）
- 🐛 修復 `*ST` 股票名在微信/Dashboard 中 markdown 轉義問題
- 🐛 修復 `idx.amount` 為 None 時大盤覆盤 TypeError
- 🐛 修複分析 API 返回 `report=None` 及 ReportStrategy 型別不一致問題
- 🐛 修復 Tushare 返回型別錯誤（dict → UnifiedRealtimeQuote）及 API 端點指向

### 新增
- 📊 大盤覆盤報告注入結構化資料（漲跌統計、指數表格、板塊排名）
- 🔍 搜尋結果 TTL 快取（500 條上限，FIFO 淘汰）
- 🔧 Tushare Token 存在時自動注入實時行情優先順序
- 📰 新聞摘要截斷長度 50→200 字

### 最佳化
- ⚡ 補充行情欄位請求限制為最多 1 次，減少無效請求

## [3.0.4] - 2026-02-07

### 新增
- 📈 **回測引擎** (PR #269)
  - 新增基於歷史分析記錄的回測系統，支援收益率、勝率、最大回撤等指標評估
  - WebUI 整合回測結果展示

## [3.0.3] - 2026-02-07

### 修復
- 🐛 修復狙擊點位資料解析錯誤問題 (PR #271)

## [3.0.2] - 2026-02-06

### 新增
- ✉️ 可配置郵件傳送者名稱 (PR #272)
- 🌐 外國股票支援英文關鍵詞搜尋

## [3.0.1] - 2026-02-06

### 修復
- 🐛 修復 ETF 實時行情獲取、市場資料回退、企業微信訊息分塊問題
- 🔧 CI 流程簡化

## [3.0.0] - 2026-02-06

### 移除
- 🗑️ **移除舊版 WebUI**
  - 刪除基於 `http.server.ThreadingHTTPServer` 的舊版 WebUI（`web/` 包）
  - 舊版 WebUI 的功能已完全被 FastAPI（`api/`）+ React 前端替代
  - `--webui` / `--webui-only` 命令列引數標記為棄用，自動重定向到 `--serve` / `--serve-only`
  - `WEBUI_ENABLED` / `WEBUI_HOST` / `WEBUI_PORT` 環境變數保持相容，自動轉發到 FastAPI 服務
  - `webui.py` 保留為相容入口，啟動時直接呼叫 FastAPI 後端
  - Docker Compose 中移除 `webui` 服務定義，統一使用 `server` 服務

### 變更
- ♻️ **服務層重構**
  - 將 `web/services.py` 中的非同步任務服務遷移至 `src/services/task_service.py`
  - Bot 分析命令（`bot/commands/analyze.py`）改為使用 `src.services.task_service`
  - Docker 環境變數 `WEBUI_HOST`/`WEBUI_PORT` 更名為 `API_HOST`/`API_PORT`（舊名仍相容）

## [2.3.0] - 2026-02-01

### 新增
- 🇺🇸 **增強美股支援** (Issue #153)
  - 實現基於 Akshare 的美股歷史資料獲取 (`ak.stock_us_daily()`)
  - 實現基於 Yfinance 的美股實時行情獲取（優先策略）
  - 增加對不支援資料來源（Tushare/Baostock/Pytdx/Efinance）的美股程式碼過濾和快速降級

### 修復
- 🐛 修復 AMD 等美股程式碼被誤識別為 A 股的問題 (Issue #153)

## [2.2.5] - 2026-02-01

### 新增
- 🤖 **AstrBot 訊息推送** (PR #217)
  - 新增 AstrBot 通知渠道，支援推送到 QQ 和微信
  - 支援 HMAC SHA256 簽名驗證，確保通訊安全
  - 透過 `ASTRBOT_URL` 和 `ASTRBOT_TOKEN` 配置

## [2.2.4] - 2026-02-01

### 新增
- ⚙️ **可配置資料來源優先順序** (PR #215)
  - 支援透過環境變數（如 `YFINANCE_PRIORITY=0`）動態調整資料來源優先順序
  - 無需修改程式碼即可優先使用特定資料來源（如 Yahoo Finance）

## [2.2.3] - 2026-01-31

### 修復
- 📦 更新 requirements.txt，增加 `lxml_html_clean` 依賴以解決相容性問題

## [2.2.2] - 2026-01-31

### 修復
- 🐛 修復代理配置區分大小寫問題 (fixes #211)

## [2.2.1] - 2026-01-31

### 修復
- 🐛 **YFinance 相容性修復** (PR #210, fixes #209)
  - 修復新版 yfinance 返回 MultiIndex 列名導致的資料解析錯誤

## [2.2.0] - 2026-01-31

### 新增
- 🔄 **多源回退策略增強**
  - 實現了更健壯的資料獲取回退機制 (feat: multi-source fallback strategy)
  - 最佳化了資料來源故障時的自動切換邏輯

### 修復
- 🐛 修復 analyzer 執行後無法透過改 .env 檔案的 stock_list 內容調整跟蹤的股票

## [2.1.14] - 2026-01-31

### 文件
- 📝 更新 README 和最佳化 auto-tag 規則

## [2.1.13] - 2026-01-31

### 修復
- 🐛 **Tushare 優先順序與實時行情** (Fixed #185)
  - 修復 Tushare 資料來源優先順序設定問題
  - 修復 Tushare 實時行情獲取功能

## [2.1.12] - 2026-01-30

### 修復
- 🌐 修復代理配置在某些情況下的區分大小寫問題
- 🌐 修復本地環境禁用代理的邏輯

## [2.1.11] - 2026-01-30

### 最佳化
- 🚀 **飛書訊息流最佳化** (PR #192)
  - 最佳化飛書 Stream 模式的訊息型別處理
  - 修改 Stream 訊息模式預設為關閉，防止配置錯誤執行時報錯

## [2.1.10] - 2026-01-30

### 合併
- 📦 合併 PR #154 貢獻

## [2.1.9] - 2026-01-30

### 新增
- 💬 **微信文字訊息支援** (PR #137)
  - 新增微信推送的純文字訊息型別支援
  - 新增 `WECHAT_MSG_TYPE` 配置項

## [2.1.8] - 2026-01-30

### 修復
- 🐛 修正日誌中 API 提供商顯示錯誤 (PR #197)

## [2.1.7] - 2026-01-30

### 修復
- 🌐 禁用本地環境的代理設定，避免網路連線問題

## [2.1.6] - 2026-01-29

### 新增
- 📡 **Pytdx 資料來源 (Priority 2)**
  - 新增通達信資料來源，免費無需註冊
  - 多伺服器自動切換
  - 支援實時行情和歷史資料
- 🏷️ **多源股票名稱解析**
  - DataFetcherManager 新增 `get_stock_name()` 方法
  - 新增 `batch_get_stock_names()` 批次查詢
  - 自動在多資料來源間回退
  - Tushare 和 Baostock 新增股票名稱/列表方法
- 🔍 **增強搜尋回退**
  - 新增 `search_stock_price_fallback()` 用於資料來源全部失敗時
  - 新增搜尋維度：市場分析、行業分析
  - 最大搜尋次數從 3 增加到 5
  - 改進搜尋結果格式（每維度 4 條結果）

### 改進
- 更新搜尋查詢模板以提高相關性
- 增強 `format_intel_report()` 輸出結構

## [2.1.5] - 2026-01-29

### 新增
- 📡 新增 Pytdx 資料來源和多源股票名稱解析功能

## [2.1.4] - 2026-01-29

### 文件
- 📝 更新贊助商資訊

## [2.1.3] - 2026-01-28

### 文件
- 📝 重構 README 佈局
- 🌐 新增繁體中文翻譯 (README_CHT.md)

### 修復
- 🐛 修復 WebUI 無法輸入美股程式碼問題
  - 輸入框邏輯改成所有字母都轉換成大寫
  - 支援 `.` 的輸入（如 `BRK.B`）

## [2.1.2] - 2026-01-27

### 修復
- 🐛 修復個股分析推送失敗和報告路徑問題 (fixes #166)
- 🐛 修改 CR 錯誤，確保微信訊息最大位元組配置生效

## [2.1.1] - 2026-01-26

### 新增
- 🔧 新增 GitHub Actions auto-tag 工作流
- 📡 新增 yfinance 兜底資料來源及資料缺失警告

### 修復
- 🐳 修復 docker-compose 路徑和文件命令
- 🐳 Dockerfile 補充 copy src 資料夾 (fixes #145)

## [2.1.0] - 2026-01-25

### 新增
- 🇺🇸 **美股分析支援**
  - 支援美股程式碼直接輸入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作為美股資料來源
- 📈 **MACD 和 RSI 技術指標**
  - MACD：趨勢確認、金叉死叉訊號（零軸上金叉⭐、金叉✅、死叉❌）
  - RSI：超買超賣判斷（超賣⭐、強勢✅、超買⚠️）
  - 指標訊號納入綜合評分系統
- 🎮 **Discord 推送支援** (PR #124, #125, #144)
  - 支援 Discord Webhook 和 Bot API 兩種方式
  - 透過 `DISCORD_WEBHOOK_URL` 或 `DISCORD_BOT_TOKEN` + `DISCORD_MAIN_CHANNEL_ID` 配置
- 🤖 **機器人命令互動**
  - 釘釘機器人支援 `/分析 股票程式碼` 命令觸發分析
  - 支援 Stream 長連線模式
- 🌡️ **AI 溫度引數可配置** (PR #142)
  - 支援自定義 AI 模型溫度引數
- 🐳 **Zeabur 部署支援**
  - 新增 Zeabur 映象部署工作流
  - 支援 commit hash 和 latest 雙標籤

### 重構
- 🏗️ **專案結構最佳化**
  - 核心程式碼移至 `src/` 目錄，根目錄更清爽
  - 文件移至 `docs/` 目錄
  - Docker 配置移至 `docker/` 目錄
  - 修復所有 import 路徑，保持向後相容
- 🔄 **資料來源架構升級**
  - 新增資料來源熔斷機制，單資料來源連續失敗自動切換
  - 實時行情快取最佳化，批次預取減少 API 呼叫
  - 網路代理智慧分流，國內介面自動直連
- 🤖 Discord 機器人重構為平臺介面卡架構

### 修復
- 🌐 **網路穩定性增強**
  - 自動檢測代理配置，對國內行情介面強制直連
  - 修復 EfinanceFetcher 偶發的 `ProtocolError`
  - 增加對底層網路錯誤的捕獲和重試機制
- 📧 **郵件渲染最佳化**
  - 修復郵件中表格不渲染問題 (#134)
  - 最佳化郵件排版，更緊湊美觀
- 📢 **企業微信推送修復**
  - 修復大盤覆盤推送不完整問題
  - 增強訊息分割邏輯，支援更多標題格式
  - 增加分批傳送間隔，避免限流丟失
- 👷 **CI/CD 修復**
  - 修復 GitHub Actions 中路徑引用的錯誤

## [2.0.0] - 2026-01-24

### 新增
- 🇺🇸 **美股分析支援**
  - 支援美股程式碼直接輸入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作為美股資料來源
- 🤖 **機器人命令互動** (PR #113)
  - 釘釘機器人支援 `/分析 股票程式碼` 命令觸發分析
  - 支援 Stream 長連線模式
  - 支援選擇精簡報告或完整報告
- 🎮 **Discord 推送支援** (PR #124)
  - 支援 Discord Webhook 推送
  - 新增 Discord 環境變數到工作流

### 修復
- 🐳 修復 WebUI 在 Docker 中繫結 0.0.0.0 (fixed #118)
- 🔔 修復飛書長連線通知問題
- 🐛 修復 `analysis_delay` 未定義錯誤
- 🔧 啟動時 config.py 檢測通知渠道，修復已配置自定義渠道情況下仍然提示未配置問題

### 改進
- 🔧 最佳化 Tushare 優先順序判斷邏輯，提升封裝性
- 🔧 修復 Tushare 優先順序提升後仍排在 Efinance 之後的問題
- ⚙️ 配置 TUSHARE_TOKEN 時自動提升 Tushare 資料來源優先順序
- ⚙️ 實現 4 個使用者反饋 issue (#112, #128, #38, #119)

## [1.6.0] - 2026-01-19

### 新增
- 🖥️ WebUI 管理介面及 API 支援（PR #72）
  - 全新 Web 架構：分層設計（Server/Router/Handler/Service）
  - 核心 API：支援 `/analysis` (觸發分析), `/tasks` (查詢進度), `/health` (健康檢查)
  - 互動介面：支援頁面直接輸入程式碼並觸發分析，實時展示進度
  - 執行模式：新增 `--webui-only` 模式，僅啟動 Web 服務
  - 解決了 [#70](https://github.com/ZhuLinsen/daily_stock_analysis/issues/70) 的核心需求（提供觸發分析的介面）
- ⚙️ GitHub Actions 配置靈活性增強（[#79](https://github.com/ZhuLinsen/daily_stock_analysis/issues/79)）
  - 支援從 Repository Variables 讀取非敏感配置（如 STOCK_LIST, GEMINI_MODEL）
  - 保持對 Secrets 的向下相容

### 修復
- 🐛 修復企業微信/飛書報告截斷問題（[#73](https://github.com/ZhuLinsen/daily_stock_analysis/issues/73)）
  - 移除 notification.py 中不必要的長度硬截斷邏輯
  - 依賴底層自動分片機制處理長訊息
- 🐛 修復 GitHub Workflow 環境變數缺失（[#80](https://github.com/ZhuLinsen/daily_stock_analysis/issues/80)）
  - 修復 `CUSTOM_WEBHOOK_BEARER_TOKEN` 未正確傳遞到 Runner 的問題

## [1.5.0] - 2026-01-17

### 新增
- 📲 單股推送模式（[#55](https://github.com/ZhuLinsen/daily_stock_analysis/issues/55)）
  - 每分析完一隻股票立即推送，不用等全部分析完
  - 命令列引數：`--single-notify`
  - 環境變數：`SINGLE_STOCK_NOTIFY=true`
- 🔐 自定義 Webhook Bearer Token 認證（[#51](https://github.com/ZhuLinsen/daily_stock_analysis/issues/51)）
  - 支援需要 Token 認證的 Webhook 端點
  - 環境變數：`CUSTOM_WEBHOOK_BEARER_TOKEN`

## [1.4.0] - 2026-01-17

### 新增
- 📱 Pushover 推送支援（PR #26）
  - 支援 iOS/Android 跨平臺推送
  - 透過 `PUSHOVER_USER_KEY` 和 `PUSHOVER_API_TOKEN` 配置
- 🔍 博查搜尋 API 整合（PR #27）
  - 中文搜尋最佳化，支援 AI 摘要
  - 透過 `BOCHA_API_KEYS` 配置
- 📊 Efinance 資料來源支援（PR #59）
  - 新增 efinance 作為資料來源選項
- 🇭🇰 港股支援（PR #17）
  - 支援 5 位程式碼或 HK 字首（如 `hk00700`、`hk1810`）

### 修復
- 🔧 飛書 Markdown 渲染最佳化（PR #34）
  - 使用互動卡片和格式化器修復渲染問題
- ♻️ 股票列表熱過載（PR #42 修復）
  - 分析前自動過載 `STOCK_LIST` 配置
- 🐛 釘釘 Webhook 20KB 限制處理
  - 長訊息自動分塊傳送，避免被截斷
- 🔄 AkShare API 重試機制增強
  - 新增失敗快取，避免重複請求失敗介面

### 改進
- 📝 README 精簡最佳化
  - 高階配置移至 `docs/full-guide.md`


## [1.3.0] - 2026-01-12

### 新增
- 🔗 自定義 Webhook 支援
  - 支援任意 POST JSON 的 Webhook 端點
  - 自動識別釘釘、Discord、Slack、Bark 等常見服務格式
  - 支援配置多個 Webhook（逗號分隔）
  - 透過 `CUSTOM_WEBHOOK_URLS` 環境變數配置

### 修復
- 📝 企業微信長訊息分批傳送
  - 解決自選股過多時內容超過 4096 字元限制導致推送失敗的問題
  - 智慧按股票分析塊分割，每批新增分頁標記（如 1/3, 2/3）
  - 批次間隔 1 秒，避免觸發頻率限制

## [1.2.0] - 2026-01-11

### 新增
- 📢 多渠道推送支援
  - 企業微信 Webhook
  - 飛書 Webhook（新增）
  - 郵件 SMTP（新增）
  - 自動識別渠道型別，配置更簡單

### 改進
- 統一使用 `NOTIFICATION_URL` 配置，相容舊的 `WECHAT_WEBHOOK_URL`
- 郵件支援 Markdown 轉 HTML 渲染

## [1.1.0] - 2026-01-11

### 新增
- 🤖 OpenAI 相容 API 支援
  - 支援 DeepSeek、通義千問、Moonshot、智譜 GLM 等
  - Gemini 和 OpenAI 格式二選一
  - 自動降級重試機制

## [1.0.0] - 2026-01-10

### 新增
- 🎯 AI 決策儀表盤分析
  - 一句話核心結論
  - 精確買入/止損/目標點位
  - 檢查清單（✅⚠️❌）
  - 分持倉建議（空倉者 vs 持倉者）
- 📊 大盤覆盤功能
  - 主要指數行情
  - 漲跌統計
  - 板塊漲跌榜
  - AI 生成覆盤報告
- 🔍 多資料來源支援
  - AkShare（主資料來源，免費）
  - Tushare Pro
  - Baostock
  - YFinance
- 📰 新聞搜尋服務
  - Tavily API
  - SerpAPI
- 💬 企業微信機器人推送
- ⏰ 定時任務排程
- 🐳 Docker 部署支援
- 🚀 GitHub Actions 零成本部署

### 技術特性
- Gemini AI 模型（gemini-3-flash-preview）
- 429 限流自動重試 + 模型切換
- 請求間延時防封禁
- 多 API Key 負載均衡
- SQLite 本地資料儲存

---

[Unreleased]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.8.0...HEAD
[3.8.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.7.0...v3.8.0
[3.7.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.6.0...v3.7.0
[3.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.5.0...v3.6.0
[3.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.10...v3.5.0
[3.4.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.9...v3.4.10
[3.4.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.8...v3.4.9
[3.4.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.7...v3.4.8
[3.4.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.4.0...v3.4.7
[3.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.22...v3.4.0
[3.3.22]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.3.12...v3.3.22
[3.3.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.11...v3.3.12
[3.2.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v3.2.10...v3.2.11
[2.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.5...v2.3.0
[2.2.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.14...v2.2.0
[2.1.14]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.13...v2.1.14
[2.1.13]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.12...v2.1.13
[2.1.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.11...v2.1.12
[2.1.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.10...v2.1.11
[2.1.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.9...v2.1.10
[2.1.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.8...v2.1.9
[2.1.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.7...v2.1.8
[2.1.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.6...v2.1.7
[2.1.6]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.5...v2.1.6
[2.1.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.4...v2.1.5
[2.1.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.6.0...v2.0.0
[1.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/releases/tag/v1.0.0
