# 貢獻指南

感謝你對本專案的關注！歡迎任何形式的貢獻。

## 🐛 報告 Bug

1. 先搜尋 [Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 確認問題未被報告
2. 使用 Bug Report 模板建立新 Issue
3. 提供詳細的復現步驟和環境資訊

## 💡 功能建議

1. 先搜尋 Issues 確認建議未被提出
2. 使用 Feature Request 模板建立新 Issue
3. 詳細描述你的使用場景和期望功能

## 🔧 提交程式碼

### 開發環境

```bash
# 克隆倉庫
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安裝依賴
pip install -r requirements.txt

# 配置環境變數
cp .env.example .env
```

### 提交流程

1. Fork 本倉庫
2. 建立特性分支：`git checkout -b feature/your-feature`
3. 提交改動：`git commit -m 'feat: add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 建立 Pull Request

### Commit 規範

使用 [Conventional Commits](https://www.conventionalcommits.org/) 規範：

```
feat: 新功能
fix: Bug 修復
docs: 文件更新
style: 程式碼格式（不影響功能）
refactor: 重構
perf: 效能最佳化
test: 測試相關
chore: 構建/工具相關
```

示例：
```
feat: 新增釘釘機器人支援
fix: 修復 429 限流重試邏輯
docs: 更新 README 部署說明
```

### 程式碼規範

- Python 程式碼遵循 PEP 8
- 函式和類需要新增 docstring
- 重要邏輯新增註釋
- 新功能需要更新相關文件

### CI 自動檢查

提交 PR 後，CI 會自動執行以下檢查：

| 檢查項 | 說明 | 必須透過 |
|--------|------|:--------:|
| backend-gate | `scripts/ci_gate.sh`（py_compile + flake8 嚴重錯誤 + 本地核心指令碼 + offline pytest） | ✅ |
| docker-build | Docker 映象構建與關鍵模組匯入 smoke | ✅ |
| web-gate | 前端變更時執行 `npm run lint` + `npm run build` | ✅（觸發時） |
| network-smoke | 定時/手動執行 `pytest -m network` + `test.sh quick`（非阻斷） | ❌（觀測項） |

**本地執行檢查：**

```bash
# backend gate（推薦）
pip install -r requirements.txt
pip install flake8 pytest
./scripts/ci_gate.sh

# 前端 gate（如修改了 apps/dsa-web）
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

## 📋 優先貢獻方向

檢視 [Roadmap](README.md#-roadmap) 瞭解當前需要的功能：

- 🔔 新通知渠道（釘釘、飛書、Telegram）
- 🤖 新 AI 模型支援（GPT-4、Claude）
- 📊 新資料來源接入
- 🐛 Bug 修復和效能最佳化
- 📖 文件完善和翻譯

## ❓ 問題解答

如有任何問題，歡迎：
- 建立 Issue 討論
- 檢視已有 Issue 和 Discussion

再次感謝你的貢獻！ 🎉
