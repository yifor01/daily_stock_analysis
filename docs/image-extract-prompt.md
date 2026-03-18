# Image Extract Prompt (Vision LLM)

本文件記錄 `src/services/image_stock_extractor.py` 中 `EXTRACT_PROMPT` 的完整內容，便於 PR 審查時評估指令效果。

**當修改 EXTRACT_PROMPT 時**：請同步更新此檔案，並在 PR 描述中展示完整變更（before/after），以便審查者評估針對 code+name+confidence 提取的最佳化程度。

---

## 當前 Prompt（完整）

```
請分析這張股票市場截圖或圖片，提取其中所有可見的股票程式碼及名稱。

重要：若圖中同時顯示股票名稱和程式碼（如自選股列表、ETF 列表），必須同時提取兩者，每個元素必須包含 code 和 name 欄位。

輸出格式：僅返回有效的 JSON 陣列，不要 markdown、不要解釋。
每個元素為物件：{"code":"股票程式碼","name":"股票名稱","confidence":"high|medium|low"}
- code: 必填，股票程式碼（A股6位、港股5位、美股1-5字母、ETF 如 159887/512880）
- name: 若圖中有名稱則必填（如 貴州茅臺、銀行ETF、證券ETF），與程式碼一一對應；僅當圖中確實無名稱時可省略
- confidence: 必填，識別置信度，high=確定、medium=較確定、low=不確定

示例（圖中同時有名稱和程式碼時）：
- 個股：600519 貴州茅臺、300750 寧德時代
- 港股：00700 騰訊控股、09988 阿里巴巴
- 美股：AAPL 蘋果、TSLA 特斯拉
- ETF：159887 銀行ETF、512880 證券ETF、512000 券商ETF、512480 半導體ETF、515030 新能源車ETF

輸出示例：[{"code":"600519","name":"貴州茅臺","confidence":"high"},{"code":"159887","name":"銀行ETF","confidence":"high"}]

禁止只返回程式碼陣列如 ["159887","512880"]，必須使用物件格式。若未找到任何股票程式碼，返回：[]
```
