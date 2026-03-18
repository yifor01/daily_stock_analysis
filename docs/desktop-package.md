# 桌面端打包說明 (Electron + React UI)

本專案可打包為桌面應用，使用 Electron 作為桌面殼，`apps/dsa-web` 的 React UI 作為介面。

## 架構說明

- React UI（Vite 構建）由本地 FastAPI 服務託管
- Electron 啟動時自動拉起後端服務，等待 `/api/health` 就緒後載入 UI
- 使用者配置檔案 `.env` 和資料庫放在 exe 同級目錄（便攜模式）

## 本地開發

一鍵啟動（開發模式）：

```bash
powershell -ExecutionPolicy Bypass -File scripts\run-desktop.ps1
```

或手動執行：

1) 構建 React UI（輸出到 `static/`）

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 啟動 Electron 應用（自動拉起後端）

```bash
cd apps/dsa-desktop
npm install
npm run dev
```

首次執行時會自動從 `.env.example` 複製生成 `.env`。

## 打包 (Windows)

### 前置條件

- Node.js 18+
- Python 3.10+
- 開啟 Windows 開發者模式（electron-builder 需要建立符號連結）
  - 設定 -> 隱私和安全性 -> 開發者選項 -> 開發者模式

### 一鍵打包

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-all.ps1
```

該指令碼會依次執行：
1. 構建 React UI
2. 安裝 Python 依賴
3. PyInstaller 打包後端
4. electron-builder 打包桌面應用

## GitHub CI 自動打包併發布 Release

倉庫已支援透過 GitHub Actions 自動構建桌面端並上傳到 GitHub Releases：

- 工作流：`.github/workflows/desktop-release.yml`
- 觸發方式：
  - 推送語義化 tag（如 `v3.2.12`）後自動觸發
  - 在 Actions 頁面手動觸發並指定 `release_tag`
- 產物：
  - Windows 安裝包：`daily-stock-analysis-windows-installer-<tag>.exe`
  - Windows 免安裝包：`daily-stock-analysis-windows-noinstall-<tag>.zip`
  - macOS Intel：`daily-stock-analysis-macos-x64-<tag>.dmg`
  - macOS Apple Silicon：`daily-stock-analysis-macos-arm64-<tag>.dmg`

建議釋出流程：

1. 合併程式碼到 `main`
2. 由自動打 tag 工作流生成版本（或手動建立 tag）
3. `desktop-release` 工作流自動構建並把兩個平臺安裝包附加到對應 GitHub Release

### 分步打包

1) 構建 React UI

```bash
cd apps/dsa-web
npm install
npm run build
```

2) 打包 Python 後端

```bash
pip install pyinstaller
pip install -r requirements.txt
python -m PyInstaller --name stock_analysis --onefile --noconsole --add-data "static;static" --hidden-import=multipart --hidden-import=multipart.multipart main.py
```

將生成的 exe 複製到 `dist/backend/`：

```bash
mkdir dist\backend
copy dist\stock_analysis.exe dist\backend\stock_analysis.exe
```

3) 打包 Electron 桌面應用

```bash
cd apps/dsa-desktop
npm install
npm run build
```

打包產物位於 `apps/dsa-desktop/dist/`。

## 目錄結構

打包後使用者拿到的目錄結構（便攜模式）：

```
win-unpacked/
  Daily Stock Analysis.exe    <- 雙擊啟動
  .env                        <- 使用者配置檔案（首次啟動自動生成）
  data/
    stock_analysis.db         <- 資料庫
  logs/
    desktop.log               <- 執行日誌
  resources/
    .env.example              <- 配置模板
    backend/
      stock_analysis.exe      <- 後端服務
```

## 配置檔案說明

- `.env` 放在 exe 同目錄下
- 首次啟動時自動從 `.env.example` 複製生成
- 使用者需要編輯 `.env` 配置以下內容：
  - `GEMINI_API_KEY` 或 `OPENAI_API_KEY`：AI 分析必需
  - `STOCK_LIST`：自選股列表（逗號分隔）
  - 其他可選配置參考 `.env.example`

## 常見問題

### 啟動後一直顯示 "Preparing backend..."

1. 檢查 `logs/desktop.log` 檢視錯誤資訊
2. 確認 `.env` 檔案存在且配置正確
3. 確認埠 8000-8100 未被佔用

### 後端啟動報 ModuleNotFoundError

PyInstaller 打包時缺少模組，需要在 `scripts/build-backend.ps1` 中增加 `--hidden-import`。

### UI 載入空白

確認 `static/index.html` 存在，如不存在需重新構建 React UI。

## 分發給使用者

將 `apps/dsa-desktop/dist/win-unpacked/` 整個資料夾打包發給使用者即可。使用者只需：

1. 解壓資料夾
2. 編輯 `.env` 配置 API Key 和股票列表
3. 雙擊 `Daily Stock Analysis.exe` 啟動
