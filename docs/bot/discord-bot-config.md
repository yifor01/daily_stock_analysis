# Discord機器人配置

## Discord機器人
Discord機器人接收訊息需要使用Discord Developer Portal建立機器人應用
https://discord.com/developers/applications

Discord機器人支援兩種訊息傳送方式：
1. **Webhook模式**：配置簡單，許可權低，適合只需要傳送訊息的場景
2. **Bot API模式**：許可權高，支援接收命令，需要配置Bot Token和頻道ID

## 建立Discord機器人

### 1. 登入Discord Developer Portal
訪問 https://discord.com/developers/applications 並使用你的Discord賬號登入

### 2. 建立應用
點選"New Application"按鈕，輸入應用名稱（例如：A股智慧分析機器人），然後點選"Create"

### 3. 配置機器人
在左側導航欄中點選"Bot"，然後點選"Add Bot"按鈕，確認新增

### 4. 獲取Bot Token
在Bot頁面，點選"Reset Token"按鈕，然後複製生成的Token（這是你的`DISCORD_BOT_TOKEN`）

### 5. 配置許可權
在Bot頁面的"Privileged Gateway Intents"部分，開啟以下選項：
- Presence Intent
- Server Members Intent
- Message Content Intent

### 6. 新增到伺服器
1. 在左側導航欄中點選"OAuth2" > "URL Generator"
2. 在"Scopes"中選擇：
   - `bot`
   - `applications.commands`
3. 在"Bot Permissions"中選擇：
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Use Slash Commands
4. 複製生成的URL，在瀏覽器中開啟，選擇要新增機器人的伺服器

### 7. 獲取頻道ID
1. 在Discord客戶端中，開啟開發者模式：設定 > 高階 > 開發者模式
2. 右鍵點選你想要機器人傳送訊息的頻道，選擇"Copy ID"（這是你的`DISCORD_MAIN_CHANNEL_ID`）

## 配置環境變數

將以下配置新增到你的`.env`檔案中：

```env
# Discord 機器人配置
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_MAIN_CHANNEL_ID=your-channel-id
DISCORD_WEBHOOK_URL=your-webhook-url (可選)
DISCORD_BOT_STATUS=A股智慧分析 | /help
```

## Webhook模式配置（可選）

如果你只想使用Webhook模式傳送訊息，不需要Bot Token，可以按照以下步驟配置：

1. 右鍵點選頻道，選擇"編輯頻道"
2. 點選"整合" > "Webhooks" > "新建Webhook"
3. 配置Webhook名稱和頭像
4. 複製Webhook URL（這是你的`DISCORD_WEBHOOK_URL`）

## 支援的命令

Discord機器人支援以下Slash命令：

1. `/analyze <stock_code> [full_report]` - 分析指定股票程式碼
   - `stock_code`: 股票程式碼，如 600519
   - `full_report`: 可選，是否生成完整報告（包含大盤）

2. `/market_review` - 獲取大盤覆盤報告

3. `/help` - 檢視幫助資訊

## 測試機器人

1. 確保機器人已成功新增到你的伺服器
2. 在頻道中輸入`/help`，機器人會返回幫助資訊
3. 輸入`/analyze 600519`測試股票分析功能
4. 輸入`/market_review`測試大盤覆盤功能

## 注意事項

1. 確保你的機器人有足夠的許可權在頻道中傳送訊息和使用Slash命令
2. 定期更新你的Bot Token，確保安全性
3. 不要將你的Bot Token分享給任何人
4. 如果機器人沒有響應，檢查：
   - Bot Token是否正確
   - 頻道ID是否正確
   - 機器人是否線上
   - 機器人是否有訊息傳送許可權

## 故障排除

- **機器人不響應命令**：檢查Bot Token和頻道ID是否正確，確保機器人已新增到伺服器
- **Slash命令不顯示**：等待一段時間（Discord需要同步命令），或重新新增機器人
- **訊息傳送失敗**：檢查頻道許可權，確保機器人有傳送訊息的許可權

## 相關連結

- [Discord Developer Portal](https://discord.com/developers/applications)
- [Discord Bot Documentation](https://discordpy.readthedocs.io/en/stable/)
- [Discord Slash Commands](https://discord.com/developers/docs/interactions/application-commands)
