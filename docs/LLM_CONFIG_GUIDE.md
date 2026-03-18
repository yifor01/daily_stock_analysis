# LLM (大模型) 配置指南

歡迎！無論你是剛接觸 AI 的新手小白，還是精通各種 API 的高玩老手，這份指南都能幫你快速把大模型（LLM）跑起來。

本專案的大模型接入基於強大且通用的 [LiteLLM](https://docs.litellm.ai/)，這意味著幾乎市面上所有的主流大模型（官方API或中轉介面）我們都支援。為了照顧不同階段的使用者，我們設計了“三層優先順序”配置，按需選擇最適合你的方式即可。

---

## 快速導航：你應該看哪一節？

1. **【新手小白】** "我只想趕緊把系統跑起來，越簡單越好！" -> [指路【方式一：極簡單模型配置】](#方式一極簡單模型配置適合新手)
2. **【進階使用者】** "我有好幾個 Key，想配置備用模型，還要改自定義網址(Base URL)。" -> [指路【方式二：渠道(Channels)模式配置】](#方式二渠道channels模式配置適合進階多模型)
3. **【高玩老手】** "我要做複雜的負載均衡、請求路由、甚至多異構平臺高可用！" -> [指路【方式三：YAML 高階配置】](#方式三yaml高階配置適合老手自定義)
4. **【視覺模型】** "我想用圖片識別股票程式碼！" -> [指路【擴充套件功能：看圖模型(Vision)配置】](#擴充套件功能看圖模型vision配置)

---

## 方式一：極簡單模型配置（適合新手）

**目標：** 只要記得填入 API Key 和對應的模型名就能立刻用。不需要折騰複雜概念。

如果你只打算用一種模型，這是最快捷的辦法。開啟專案根目錄下的 `.env` 檔案（如果沒有，複製一份 `.env.example` 並重新命名為 `.env`）。

### 示例 1：使用通用第三方平臺（相容 OpenAI 格式，推薦）

現在市面上絕大多數第三方聚合平臺（例如矽基流動、AIHubmix、阿里百鍊、智譜等）都相容 OpenAI 的介面格式。只要平臺提供了 API Key 和 Base URL，你都可以按照以下格式無腦配置：

```env
# 填入平臺提供給你的 API Key
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
# 填入平臺的介面地址 (非常重要：結尾通常必須帶有 /v1)
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
# 填入該平臺上具體的模型名稱（非常重要：注意前面必須加上 openai/ 字首幫系統識別）
LITELLM_MODEL=openai/deepseek-ai/DeepSeek-V3 
```

### 示例 2：使用 DeepSeek 官方介面
```env
# 填入你在 DeepSeek 官方平臺申請的 API Key
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```
*提示：僅需這一行，系統會自動識別並預設使用 DeepSeek 模型。*

### 示例 3：使用 Gemini 免費 API
```env
# 填入你獲取的 Google Gemini Key
GEMINI_API_KEY=AIzac...
```

> **恭喜！小白讀到這裡就可以去執行程式了！**
> 想測測看通沒通？在主目錄開啟命令列輸入：`python test_env.py --llm`

---

## 方式二：渠道(Channels)模式配置（適合進階/多模型）

**目標：** 我有多個不同平臺的 Key 想要混著用，如果主模型卡了/網路掛了，我希望它能自動切換到備用模型。

**網頁端可以直接配：** 你可以啟動程式後，在 **Web UI 的“系統設定 -> AI 模型 -> 渠道編輯器”** 中非常直觀地進行視覺化配置！

如果不方便用網頁版，在 `.env` 檔案中配置也非常絲滑，它能讓你同時管理多個第三方平臺。規則如下：

1. **先宣告你有幾個渠道**：`LLM_CHANNELS=渠道名稱1,渠道名稱2`
2. **給每個渠道分別填寫配置**（注意全大寫）：`LLM_{渠道名}_XXX`

### 示例：同時配置 DeepSeek 和某中轉平臺，並設定備用切換
```env
# 1. 開啟渠道模式，宣告這裡有兩個渠道：deepseek 和 aihubmix
LLM_CHANNELS=deepseek,aihubmix

# 2. 渠道一：配置 DeepSeek 官方
LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
LLM_DEEPSEEK_API_KEY=sk-1111111111111
LLM_DEEPSEEK_MODELS=deepseek-chat,deepseek-reasoner

# 3. 渠道二：配置一個常用的聚合中轉 API
LLM_AIHUBMIX_BASE_URL=https://api.aihubmix.com/v1
LLM_AIHUBMIX_API_KEY=sk-2222222222222
LLM_AIHUBMIX_MODELS=gpt-4o-mini,claude-3-5-sonnet

# 4. 【關鍵】指定主模型和備用模型列表
# 平時首選用 deepseek 這款模型：
LITELLM_MODEL=deepseek/deepseek-chat
# 主模型崩了立刻挨個嘗試下面這倆備用模型：
LITELLM_FALLBACK_MODELS=openai/gpt-4o-mini,anthropic/claude-3-5-sonnet
```

> **致命避坑說明**：如果你啟用了 `LLM_CHANNELS`，那麼你直接寫在外面的 `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY` 將**全部失效（系統一律無視）**！二者**選其一即可**，千萬不要既寫了新手模式又寫了渠道模式結果產生衝突。

---

## 方式三：YAML 高階配置（適合老手自定義）

**目標：** 我不在乎學習門檻，我要最高控制權，我要用原生規則做企業級高可用！

本專案完全放開了 LiteLLM 原生能力，支援高併發、自動重試、按 RPM/TPM 負載均衡等操作。

### 本地執行 / Docker 部署模式配置說明

1. 在 `.env` 中只保留一行指向宣告：
   ```env
   LITELLM_CONFIG=./litellm_config.yaml
   ```
2. 在專案根目錄建立一個 `litellm_config.yaml`（可以參考自帶的 `litellm_config.example.yaml`）。

示例 `litellm_config.yaml`：
```yaml
model_list:
  - model_name: my-smart-model
    litellm_params:
      model: openai/deepseek-chat
      api_base: https://api.deepseek.com/v1
      api_key: "os.environ/MY_CUSTOM_SECRET_KEY"  # 從環境變數讀取 Key，安全防洩漏
```

### GitHub Actions配置說明

1. `Settings` → `Secrets and variables` → `Actions` → `Secret`標籤頁下的`New repository secret` 或者 `Variables`標籤頁下的`New repository variable`

2. 按下表配置，只有全部必填配置正確配置，YAML 高階配置模式才可以生效，YAML配置檔案的寫法，可以參考自帶的 `litellm_config.example.yaml`

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `LITELLM_CONFIG` | 配置檔案路徑，通常配置`./litellm_config.yaml` | 必填 |
| `LITELLM_MODEL` | 模型名稱 | 必填 |
| `LITELLM_CONFIG_YAML` | 存放YAML配置檔案，可以不用在儲存庫中提交檔案 | 可選 |
| `LITELLM_API_KEY` | 用於儲存API Key，可在配置檔案中引用（環境變數引用方式）。由於GitHub Actions必須要指定匯入的環境變數，因此你不能像本地執行模式那樣自由命名環境變數 | 可選，必須配置到repository secret中 |
| `ANTHROPIC_API_KEY` | 如果要多個API Key，這個變數名稱也能拿來用 | 可選，必須配置到repository secret中 |
| `OPENAI_API_KEY` | 同上，可以用來儲存API Key | 可選，必須配置到repository secret中 |


> **三層配置互斥準則**：YAML 優先順序最高！只要配置了 YAML，**渠道模式** 和 **新手極簡模式** 統統被忽略。系統優先順序為：`YAML配置 > 渠道模式 > 極簡單模型`。

---

## 擴充套件功能：看圖模型 (Vision) 配置

系統中有些特定功能（比如上傳股票軟體截圖，讓 AI 提取出截圖裡的股票程式碼並放入自選股池）必須用到具備“視覺能力”的模型。你需在 `.env` 單獨給它指派一個懂圖片的模型。

```env
# 指定你看圖專用的模型名
VISION_MODEL=gemini/gemini-2.5-flash
# 別忘了填寫它對應提供商的 API KEY，如果是 gemini 就提供 GEMINI_API_KEY：
# GEMINI_API_KEY=xxx
```

**備用看圖機制：** 為了防止偶爾罷工，系統內建了切換策略。如果主視覺模型呼叫失敗，它會按照下方的順位嘗試尋找是否有其他看圖模型的 Key：
```env
# 預設的備用順序：
VISION_PROVIDER_PRIORITY=gemini,anthropic,openai
```

---

## 檢測與排錯 (Troubleshooting)

配好了之後心驚膽戰不知道對不對？在命令列（Terminal）裡敲入下面程式碼幫你掛號問診：

- `python test_env.py --config` ：純檢測 `.env` 配置檔案裡的邏輯寫得對不對，是不是少寫了什麼。（秒出結果，不呼叫網路，純檢查本地文字拼寫）
- `python test_env.py --llm` ：系統會真的發一句問候語給大模型，讓你親眼看到他的回答。這能徹底測出你的**網路通不通、賬號有沒有欠費**。

### 常見踩坑答疑臺

| 遇到了什麼詭異報錯？ | 罪魁禍首可能是啥？ | 該怎麼收拾它？ |
|----------------------|----------------------|------------------|
| **螢幕蹦出一句 LLM_MODEL 未配置** | 系統不知道你到底想用哪家的哪個模型 | 在 `.env` 中寫上一句明白話：`LITELLM_MODEL=provider/你的模型名`。比如 `openai/gpt-4o-mini` |
| **我寫了好幾家的Key，為什麼死活只有一個生效？修改還沒用？** | 你把 **極簡模式** 和 **渠道模式** 混著寫了！ | 想好一條路走到黑——只要簡單就刪掉 `LLM_CHANNELS` 開頭的；想要豐富備用切換就要全部轉投到 `LLM_CHANNELS` 下的編制裡。 |
| **錯誤碼報 400 或 401 或 Invalid API Key** | API Key 填錯、少複製了一截、賬號充值沒到賬、或者模型名字敲錯（極度常見）。 | 1. 檢查複製的 Key 前後是否有誤填空格。<br> 2. 檢查 Base URL 最後是不是少了一個 `/v1`。<br> 3. 檢查模型名是否少寫了 `openai/` 之類的字首！ |
| **轉圈轉不停，最後報 Timeout / ConnectionRefused 等** | 1. 在國內使用國外原版（像 Google、OpenAI），沒開代理被牆了。<br>2. 你買的雲伺服器壓根不能出境。 | 非常推薦使用**國內官方**（如DeepSeek、阿里）或者各種**相容 OpenAI 的聚合中轉介面**。因為中轉站把網路問題幫你解決好了。 |

*進階老手的叮囑：如果你開啟了 **Agent (深度思考網路搜尋問股) 模式**，這裡有個經驗之談，推薦選用如 `deepseek-reasoner` 這種自帶強悍邏輯推導和思考機制的大模型。如果為了省錢用小微模型跑 Agent，它邏輯能力大機率跟不上，不僅達不到預期，還會白跑一堆空流程。*
