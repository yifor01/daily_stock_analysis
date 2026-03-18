import type { SystemConfigCategory } from '../types/systemConfig';

const categoryTitleMap: Record<SystemConfigCategory, string> = {
  base: '基礎設定',
  data_source: '資料來源',
  ai_model: 'AI 模型',
  notification: '通知渠道',
  system: '系統設定',
  agent: 'Agent 設定',
  backtest: '回測配置',
  uncategorized: '其他',
};

const categoryDescriptionMap: Partial<Record<SystemConfigCategory, string>> = {
  base: '管理自選股與基礎執行引數。',
  data_source: '管理行情資料來源與優先順序策略。',
  ai_model: '管理模型供應商、模型名稱與推理引數。',
  notification: '管理機器人、Webhook 和訊息推送配置。',
  system: '管理排程、日誌、埠等系統級引數。',
  agent: '管理 Agent 模式、策略與多 Agent 編排配置。',
  backtest: '管理回測開關、評估視窗和引擎引數。',
  uncategorized: '其他未歸類的配置項。',
};

const fieldTitleMap: Record<string, string> = {
  STOCK_LIST: '自選股列表',
  TUSHARE_TOKEN: 'Tushare Token',
  BOCHA_API_KEYS: 'Bocha API Keys',
  TAVILY_API_KEYS: 'Tavily API Keys',
  SERPAPI_API_KEYS: 'SerpAPI API Keys',
  BRAVE_API_KEYS: 'Brave API Keys',
  SEARXNG_BASE_URLS: 'SearXNG Base URLs',
  MINIMAX_API_KEYS: 'MiniMax API Keys',
  NEWS_STRATEGY_PROFILE: '新聞策略視窗檔位',
  NEWS_MAX_AGE_DAYS: '新聞最大時效（天）',
  REALTIME_SOURCE_PRIORITY: '實時資料來源優先順序',
  ENABLE_REALTIME_TECHNICAL_INDICATORS: '盤中實時技術面',
  LITELLM_MODEL: '主模型',
  LITELLM_FALLBACK_MODELS: '備選模型',
  LITELLM_CONFIG: 'LiteLLM 配置檔案',
  LLM_CHANNELS: 'LLM 渠道列表',
  LLM_TEMPERATURE: '取樣溫度',
  AIHUBMIX_KEY: 'AIHubmix Key',
  DEEPSEEK_API_KEY: 'DeepSeek API Key',
  GEMINI_API_KEY: 'Gemini API Key',
  GEMINI_MODEL: 'Gemini 模型',
  GEMINI_TEMPERATURE: 'Gemini 溫度引數',
  OPENAI_API_KEY: 'OpenAI API Key',
  OPENAI_BASE_URL: 'OpenAI Base URL',
  OPENAI_MODEL: 'OpenAI 模型',
  WECHAT_WEBHOOK_URL: '企業微信 Webhook',
  DINGTALK_APP_KEY: '釘釘 App Key',
  DINGTALK_APP_SECRET: '釘釘 App Secret',
  PUSHPLUS_TOKEN: 'PushPlus Token',
  REPORT_SUMMARY_ONLY: '僅分析結果摘要',
  MAX_WORKERS: '最大併發執行緒數',
  SCHEDULE_TIME: '定時任務時間',
  HTTP_PROXY: 'HTTP 代理',
  LOG_LEVEL: '日誌級別',
  WEBUI_PORT: 'WebUI 埠',
  AGENT_MODE: '啟用 Agent 模式',
  AGENT_MAX_STEPS: 'Agent 最大步數',
  AGENT_SKILLS: 'Agent 啟用策略',
  AGENT_STRATEGY_DIR: 'Agent 策略目錄',
  AGENT_ARCH: 'Agent 架構模式',
  AGENT_ORCHESTRATOR_MODE: '編排模式',
  AGENT_ORCHESTRATOR_TIMEOUT_S: '編排超時（秒）',
  AGENT_RISK_OVERRIDE: '風控 Agent 否決',
  AGENT_STRATEGY_AUTOWEIGHT: '策略自動加權',
  AGENT_STRATEGY_ROUTING: '策略路由模式',
  AGENT_MEMORY_ENABLED: '記憶與校準',
  BACKTEST_ENABLED: '啟用回測',
  BACKTEST_EVAL_WINDOW_DAYS: '回測評估視窗（交易日）',
  BACKTEST_MIN_AGE_DAYS: '回測最小歷史天數',
  BACKTEST_ENGINE_VERSION: '回測引擎版本',
  BACKTEST_NEUTRAL_BAND_PCT: '回測中性區間閾值（%）',
};

const fieldDescriptionMap: Record<string, string> = {
  STOCK_LIST: '使用逗號分隔股票程式碼，例如：600519,300750。',
  TUSHARE_TOKEN: '用於接入 Tushare Pro 資料服務的憑據。',
  BOCHA_API_KEYS: '用於新聞檢索的 Bocha 金鑰，支援逗號分隔多個（最高優先順序）。',
  TAVILY_API_KEYS: '用於新聞檢索的 Tavily 金鑰，支援逗號分隔多個。',
  SERPAPI_API_KEYS: '用於新聞檢索的 SerpAPI 金鑰，支援逗號分隔多個。',
  BRAVE_API_KEYS: '用於新聞檢索的 Brave Search 金鑰，支援逗號分隔多個。',
  SEARXNG_BASE_URLS: 'SearXNG 自建例項地址（逗號分隔，無配額兜底，需在 settings.yml 啟用 format: json）。',
  MINIMAX_API_KEYS: '用於新聞檢索的 MiniMax 金鑰，支援逗號分隔多個（最低優先順序）。',
  NEWS_STRATEGY_PROFILE: '新聞視窗檔位：ultra_short=1天，short=3天，medium=7天，long=30天。',
  NEWS_MAX_AGE_DAYS: '新聞最大時效上限。實際視窗 = min(策略檔位天數, NEWS_MAX_AGE_DAYS)。例如 ultra_short + 7 仍為 1 天。',
  REALTIME_SOURCE_PRIORITY: '按逗號分隔填寫資料來源呼叫優先順序。',
  ENABLE_REALTIME_TECHNICAL_INDICATORS: '盤中分析時用實時價計算 MA5/MA10/MA20 與多頭排列（Issue #234）；關閉則用昨日收盤。',
  LITELLM_MODEL: '主模型，格式 provider/model（如 gemini/gemini-2.5-flash）。配置渠道後自動推斷。',
  LITELLM_FALLBACK_MODELS: '備選模型，逗號分隔，主模型失敗時按序嘗試。',
  LITELLM_CONFIG: 'LiteLLM YAML 配置檔案路徑（高階用法），優先順序最高。',
  LLM_CHANNELS: '渠道名稱列表（逗號分隔）。推薦使用上方渠道編輯器管理。',
  LLM_TEMPERATURE: '控制模型輸出隨機性，0 為確定性輸出，2 為最大隨機性，推薦 0.7。',
  AIHUBMIX_KEY: 'AIHubmix 一站式金鑰，自動指向 aihubmix.com/v1。',
  DEEPSEEK_API_KEY: 'DeepSeek 官方 API 金鑰。填寫後自動使用 deepseek-chat 模型。',
  GEMINI_API_KEY: '用於 Gemini 服務呼叫的金鑰。',
  GEMINI_MODEL: '設定 Gemini 分析模型名稱。',
  GEMINI_TEMPERATURE: '控制模型輸出隨機性，範圍通常為 0.0 到 2.0。',
  OPENAI_API_KEY: '用於 OpenAI 相容服務呼叫的金鑰。',
  OPENAI_BASE_URL: 'OpenAI 相容 API 地址，例如 https://api.deepseek.com/v1。',
  OPENAI_MODEL: 'OpenAI 相容模型名稱，例如 gpt-4o-mini、deepseek-chat。',
  WECHAT_WEBHOOK_URL: '企業微信機器人 Webhook 地址。',
  DINGTALK_APP_KEY: '釘釘應用模式 App Key。',
  DINGTALK_APP_SECRET: '釘釘應用模式 App Secret。',
  PUSHPLUS_TOKEN: 'PushPlus 推送令牌。',
  REPORT_SUMMARY_ONLY: '僅推送分析結果摘要，不包含個股詳情。多股時適合快速瀏覽。',
  MAX_WORKERS: '非同步任務佇列最大併發數。配置儲存後，佇列空閒時會自動應用；繁忙時延後生效。',
  SCHEDULE_TIME: '每日定時任務執行時間，格式為 HH:MM。',
  HTTP_PROXY: '網路代理地址，可留空。',
  LOG_LEVEL: '設定日誌輸出級別。',
  WEBUI_PORT: 'Web 頁面服務監聽埠。',
  AGENT_MODE: '是否啟用 ReAct Agent 進行股票分析。',
  AGENT_MAX_STEPS: 'Agent 思考和呼叫工具的最大步數。',
  AGENT_SKILLS: '逗號分隔的交易策略列表，例如：bull_trend,ma_golden_cross,shrink_pullback。',
  AGENT_STRATEGY_DIR: '存放 Agent 策略 YAML 檔案的目錄路徑。',
  AGENT_ARCH: "選擇 Agent 執行架構。single 為經典單 Agent；multi 為多 Agent 編排（實驗性）。",
  AGENT_ORCHESTRATOR_MODE: "Multi-Agent 編排深度。quick（技術→決策）、standard（技術→情報→決策）、full（含風控）、strategy（含策略評估）。",
  AGENT_ORCHESTRATOR_TIMEOUT_S: "Multi-Agent 編排總超時預算（秒），0 表示不限制。",
  AGENT_RISK_OVERRIDE: "允許風控 Agent 在發現關鍵風險時否決買入訊號。",
  AGENT_STRATEGY_AUTOWEIGHT: "根據回測表現自動調整策略權重。",
  AGENT_STRATEGY_ROUTING: "策略選擇方式。auto 按市場狀態自動選擇，manual 使用 AGENT_SKILLS 列表。",
  AGENT_MEMORY_ENABLED: "啟用記憶與校準系統，追蹤歷史分析準確率並自動調節置信度。",
  BACKTEST_ENABLED: '是否啟用回測功能（true/false）。',
  BACKTEST_EVAL_WINDOW_DAYS: '回測評估視窗長度，單位為交易日。',
  BACKTEST_MIN_AGE_DAYS: '僅回測早於該天數的分析記錄。',
  BACKTEST_ENGINE_VERSION: '回測引擎版本標識，用於區分結果版本。',
  BACKTEST_NEUTRAL_BAND_PCT: '中性區間閾值百分比，例如 2 表示 -2%~+2%。',
};

export function getCategoryTitleZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryTitleMap[category] || fallback || category;
}

export function getCategoryDescriptionZh(category: SystemConfigCategory, fallback?: string): string {
  return categoryDescriptionMap[category] || fallback || '';
}

export function getFieldTitleZh(key: string, fallback?: string): string {
  return fieldTitleMap[key] || fallback || key;
}

export function getFieldDescriptionZh(key: string, fallback?: string): string {
  return fieldDescriptionMap[key] || fallback || '';
}
