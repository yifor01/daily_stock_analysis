# 釘釘企業機器人配置

## 釘釘機器人
釘釘機器人接收訊息需要使用企業機器人能力
https://open.dingtalk.com/document/dingstart/configure-the-robot-application

接收訊息分為 `Http模式`（需要配置公網地址） 和 `Stream模式` 兩種, 推薦使用 `Stream模式`

建立應用步驟：https://open.dingtalk.com/document/dingstart/create-application

應用開發 > 企業內部應用 > 釘釘應用 > 建立應用 > 新增應用能力 > 機器人

### 新增機器人

![img.png](add-dingding-bot.png)

### 配置機器人使用 Stream模式

![configbot.png](configbot.png)

### 獲取應用憑證
![img.png](appkey.png)

### 配置釘釘憑證
把釘釘應用憑證配置到配置檔案中
![img.png](envconfig.png)

### 釋出應用
![img.png](img.png)

![img.png](group.png)

![img.png](add-group-bot.png)

### 往下滾動會看到增加的企業機器人
![img_1.png](img_1.png)

### 測試機器人命令
![img_3.png](img_3.png)