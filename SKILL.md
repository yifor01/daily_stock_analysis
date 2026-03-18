---
name: "stock_analyzer"
description: "分析股票和市場。當使用者想要分析單個或多個股票，或進行市場覆盤時呼叫。"
---

# 股票分析器

本技能基於 `analyzer_service.py` 的邏輯，提供分析股票和整體市場的功能。

## 輸出結構 (`AnalysisResult`)

分析函式返回一個 `AnalysisResult` 物件（或其列表），該物件具有豐富的結構。以下是其關鍵元件的簡要概述，並附有真實的輸出示例：

`dashboard` 屬性包含核心分析，分為四個主要部分：
1.  **`core_conclusion`**: 一句話總結、訊號型別和倉位建議。
2.  **`data_perspective`**: 技術資料，包括趨勢狀態、價格位置、量能分析和籌碼結構。
3.  **`intelligence`**: 定性資訊，如新聞、風險警報和積極催化劑。
4.  **`battle_plan`**: 可操作的策略，包括狙擊點（買/賣目標）、倉位策略和風險控制清單。

## 配置 (`Config`)

所有分析函式都可以接受一個可選的 `config` 物件。該物件包含應用程式的所有配置，例如 API 金鑰、通知設定和分析引數。

如果未提供 `config` 物件，函式將自動使用從 `.env` 檔案載入的全域性單例例項。

**參考:** [`Config`](src/config.py)

## 函式

### 1. 分析單隻股票

**描述:** 分析單隻股票並返回分析結果。

**何時使用:** 當使用者要求分析特定股票時。

**輸入:**
- `stock_code` (str): 要分析的股票程式碼。
- `config` (Config, 可選): 配置物件。預設為 `None`。
- `full_report` (bool, 可選): 是否生成完整報告。預設為 `False`。
- `notifier` (NotificationService, 可選): 通知服務物件。預設為 `None`。

**輸出:** `Optional[AnalysisResult]`
一個包含分析結果的 `AnalysisResult` 物件，如果分析失敗則為 `None`。

**示例:**

```python
from analyzer_service import analyze_stock

# 分析單隻股票
result = analyze_stock("600989")
if result:
    print(f"股票: {result.name} ({result.code})")
    print(f"情緒得分: {result.sentiment_score}")
    print(f"操作建議: {result.operation_advice}")
```

**參考:** [`analyze_stock`](./analyzer_service.py)

### 2. 分析多隻股票

**描述:** 分析一個股票列表並返回分析結果列表。

**何時使用:** 當使用者想要一次分析多隻股票時。

**輸入:**
- `stock_codes` (List[str]): 要分析的股票程式碼列表。
- `config` (Config, 可選): 配置物件。預設為 `None`。
- `full_report` (bool, 可選): 是否為每隻股票生成完整報告。預設為 `False`。
- `notifier` (NotificationService, 可選): 通知服務物件。預設為 `None`。

**輸出:** `List[AnalysisResult]`
一個 `AnalysisResult` 物件列表。

**示例:**

```python
from analyzer_service import analyze_stocks

# 分析多隻股票
results = analyze_stocks(["600989", "000001"])
for result in results:
    print(f"股票: {result.name}, 操作建議: {result.operation_advice}")
```

**參考:** [`analyze_stocks`](./analyzer_service.py)


### 3. 執行大盤覆盤

**描述:** 對整體市場進行復盤並返回一份報告。

**何時使用:** 當使用者要求市場概覽、摘要或覆盤時。

**輸入:**
- `config` (Config, 可選): 配置物件。預設為 `None`。
- `notifier` (NotificationService, 可選): 通知服務物件。預設為 `None`。

**輸出:** `Optional[str]`
一個包含市場覆盤報告的字串，如果失敗則為 `None`。

**示例:**

```python
from analyzer_service import perform_market_review

# 執行大盤覆盤
report = perform_market_review()
if report:
    print(report)
```

**參考:** [`perform_market_review`](./analyzer_service.py)
