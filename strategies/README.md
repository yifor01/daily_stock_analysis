# 交易策略目錄 / Trading Strategies

本目錄存放 **自然語言策略檔案**（YAML 格式）。系統啟動時自動載入此目錄下所有 `.yaml` 檔案。

## 如何編寫自定義策略

只需建立一個 `.yaml` 檔案，用中文（或任意語言）描述你的交易策略即可，**無需編寫任何程式碼**。

### 最簡模板

```yaml
name: my_strategy          # 唯一標識（英文，下劃線連線）
display_name: 我的策略      # 顯示名稱（中文）
description: 簡短描述策略用途

instructions: |
  你的策略描述...
  用自然語言寫出判斷標準、入場條件、出場條件等。
  可以引用工具名稱（如 get_daily_history、analyze_trend）來指導 AI 使用哪些資料。
```

### 完整模板

```yaml
name: my_strategy
display_name: 我的策略
description: 簡短描述策略適用的市場場景

# 策略分類：trend（趨勢）、pattern（形態）、reversal（反轉）、framework（框架）
category: trend

# 關聯的核心交易理念編號（1-7），可選
core_rules: [1, 2]

# 策略需要使用的工具列表，可選
# 可用工具：get_daily_history, analyze_trend, get_realtime_quote,
#           get_sector_rankings, search_stock_news
required_tools:
  - get_daily_history
  - analyze_trend

# 策略詳細說明（自然語言，支援 Markdown 格式）
instructions: |
  **我的策略名稱**

  判斷標準：

  1. **條件一**：
     - 使用 `analyze_trend` 檢查均線排列。
     - 描述你期望看到的趨勢特徵...

  2. **條件二**：
     - 描述量能要求...

  評分調整：
  - 滿足條件時建議的 sentiment_score 調整
  - 在 `buy_reason` 中註明策略名稱
```

### 核心交易理念參考

| 編號 | 理念 |
|------|------|
| 1 | 嚴進策略：乖離率 < 5% 才考慮入場 |
| 2 | 趨勢交易：MA5 > MA10 > MA20 多頭排列 |
| 3 | 效率優先：量能確認趨勢有效性 |
| 4 | 買點偏好：優先回踩均線支撐 |
| 5 | 風險排查：利空新聞一票否決 |
| 6 | 量價配合：成交量驗證價格運動 |
| 7 | 強勢趨勢股放寬：龍頭股可適當放寬標準 |

## 自定義策略目錄

除了本目錄（內建策略），你還可以透過環境變數指定額外的自定義策略目錄：

```env
AGENT_STRATEGY_DIR=./my_strategies
```

系統會同時載入內建策略和自定義策略。如果名稱衝突，自定義策略覆蓋內建策略。
