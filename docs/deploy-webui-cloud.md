# 雲伺服器 Web 介面訪問指南

如果你已經把專案部署到雲伺服器，但不知道在瀏覽器裡輸入什麼地址才能開啟 Web 管理介面，這篇教程就是為你準備的。

> 其實就兩步：讓服務監聽外網，再在瀏覽器裡輸入地址。

---

## 目錄

- [方式一：直接部署（pip + python）](#方式一直接部署pip--python)
- [方式二：Docker Compose](#方式二docker-compose)
- [如何在瀏覽器裡開啟介面](#如何在瀏覽器裡開啟介面)
- [訪問不了？先檢查這幾項](#訪問不了先檢查這幾項)
- [可選：Nginx 反向代理（繫結域名 / 80 埠）](#可選nginx-反向代理繫結域名--80-埠)
- [安全建議](#安全建議)

---

## 方式一：直接部署（pip + python）

### 第一步：修改 .env 中的監聽地址

用編輯器開啟 `.env`（在專案根目錄，即包含 `main.py` 的目錄），找到這一行：

```env
WEBUI_HOST=127.0.0.1
```

把 `127.0.0.1` 改成 `0.0.0.0`：

```env
WEBUI_HOST=0.0.0.0
```

> `127.0.0.1` 表示只有本機能訪問，`0.0.0.0` 表示允許任何來源訪問。雲伺服器必須改成 `0.0.0.0` 才能從外網開啟介面。

> **注意**：`.env` 裡的 `WEBUI_HOST` 優先順序高於命令列引數。所以即使你在命令里加了 `--host 0.0.0.0`，如果 `.env` 裡還是 `127.0.0.1`，外網照樣訪問不了。請務必先改 `.env`。

### 第二步：啟動服務

在專案根目錄執行：

```bash
# 只啟動 Web 介面（不自動執行分析）
python main.py --webui-only

# 或者：啟動 Web 介面（啟動時執行一次分析；需每日定時分析請加 --schedule 或設 SCHEDULE_ENABLED=true）
python main.py --webui
```

啟動成功後，終端會輸出類似：

```
FastAPI 服務已啟動: http://0.0.0.0:8000
```

如果你想讓服務在退出終端後繼續執行，可以用 `nohup`：

```bash
nohup python main.py --webui-only > /dev/null 2>&1 &
```

> 日誌檔案會由程式自動寫入 `logs/` 目錄，用 `tail -f logs/stock_analysis_*.log` 檢視。

### 修改埠（可選）

預設埠是 8000。如果想改用其他埠，在 `.env` 裡設定：

```env
WEBUI_PORT=8888
```

然後重啟服務。

---

## 方式二：Docker Compose

### 第一步：確認已有 .env 配置

專案的 `docker/docker-compose.yml` 在容器內部已經自動設定了 `WEBUI_HOST=0.0.0.0`，你不需要在 `.env` 裡再改監聽地址，Docker 會自動處理。

### 第二步：啟動服務

在專案根目錄執行：

```bash
# 同時啟動定時分析 + Web 介面（推薦）
docker-compose -f ./docker/docker-compose.yml up -d

# 或者只啟動 Web 介面服務
docker-compose -f ./docker/docker-compose.yml up -d server
```

啟動後檢視狀態：

```bash
docker-compose -f ./docker/docker-compose.yml ps
```

看到 `server` 服務狀態為 `running` 就說明 Web 介面已經在執行了。

### 修改埠（可選）

預設埠是 8000。如果想改用其他埠，在 `.env` 裡設定：

```env
API_PORT=8888
```

然後重新啟動容器：

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml up -d
```

---

## 如何在瀏覽器裡開啟介面

服務啟動後，在瀏覽器位址列輸入：

```
http://你的伺服器公網IP:8000
```

例如，如果你的伺服器 IP 是 `1.2.3.4`，就輸入：

```
http://1.2.3.4:8000
```

如果你的域名已經解析到這臺伺服器，也可以直接用域名訪問：

```
http://your-domain.com:8000
```

> **在哪裡查公網 IP？** 登入你的雲伺服器控制檯（阿里雲/騰訊雲/AWS 等），在例項列表裡可以看到「公網 IP」或「彈性 IP」。

---

## 訪問不了？先檢查這幾項

### 1. 安全組 / 防火牆沒有放行埠

這是最常見的原因。雲伺服器預設只開放 22（SSH）埠，需要手動放行 8000（或你改的埠）。

**操作方法**（以阿里云為例）：
1. 登入阿里雲控制檯 → 雲伺服器 ECS → 找到你的例項
2. 點選「安全組」→「配置規則」→「新增安全組規則」
3. 方向選「入方向」，埠範圍填 `8000/8000`，授權物件填 `0.0.0.0/0`，點選「確定」

騰訊雲、AWS 等雲廠商操作類似，找到「安全組」或「防火牆規則」，新增一條允許 TCP 8000 埠的入站規則即可。

### 2. 伺服器系統防火牆攔截了

如果你的系統開啟了 `ufw` 或 `firewalld`，也需要放行埠：

```bash
# Ubuntu / Debian（ufw）
sudo ufw allow 8000

# CentOS / RHEL（firewalld）
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 直接部署時 .env 裡的 WEBUI_HOST 沒改

這是第二常見原因。`.env` 裡預設是 `WEBUI_HOST=127.0.0.1`，這樣服務只監聽本機，外網根本連不上。

改法：開啟 `.env`，把 `WEBUI_HOST=127.0.0.1` 改成 `WEBUI_HOST=0.0.0.0`，然後重啟服務。

> Docker 方式不需要改這個，可以跳過。

### 4. 埠號對不上

檢查訪問地址裡的埠是否和 `.env` / 啟動命令裡設定的埠一致。

- 直接部署：預設 8000，可透過 `WEBUI_PORT=xxxx` 修改
- Docker：預設 8000，可透過 `API_PORT=xxxx` 修改

---

## 可選：Nginx 反向代理（繫結域名 / 80 埠）

如果你有域名，或者不想在地址裡帶 `:8000`，可以用 Nginx 做反向代理，把 80/443 埠流量轉發給後端服務。

### 安裝 Nginx

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y nginx

# CentOS
sudo yum install -y nginx
```

### 配置檔案示例

新建檔案 `/etc/nginx/conf.d/stock-analyzer.conf`，內容如下（把 `your-domain.com` 改成你的域名或 IP）：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支援 WebSocket（Agent 對話頁面需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 啟用配置並重啟 Nginx

```bash
sudo nginx -t            # 檢查配置有沒有語法錯誤
sudo systemctl reload nginx
```

配置成功後，直接用 `http://your-domain.com` 訪問即可，不需要帶埠號。

> **使用 Nginx 後的注意事項**：
> - 如果你開啟了 Web 登入認證（`ADMIN_AUTH_ENABLED=true`），建議在 `.env` 中把 `TRUST_X_FORWARDED_FOR=true` 一併開啟，否則系統可能無法正確識別真實 IP。
> - 如需 HTTPS，可以用 [Certbot](https://certbot.eff.org/) 自動申請免費的 Let's Encrypt 證書。

---

## 安全建議

把 Web 介面暴露到公網之前，強烈建議開啟登入密碼保護：

在 `.env` 中設定：

```env
ADMIN_AUTH_ENABLED=true
```

重啟服務後，第一次訪問網頁時會要求設定初始密碼。設定完成後，每次開啟設定頁面都需要輸入密碼，可以防止 API Key 等敏感配置被他人看到。

> 如果忘了密碼，可以在伺服器上執行：`python -m src.auth reset_password`

---

遇到其他問題？歡迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)。
