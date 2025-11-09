# 程式碼分析 AI Agent

這是一個基於雙重 LLM 架構的系統，能夠分析程式碼庫並生成結構化的功能實作報告。

## 概述

此 AI Agent 接收程式碼儲存庫（ZIP 檔案格式）和自然語言的問題描述，自動識別哪些檔案和函數實作了所描述的功能。系統採用雙階段架構，能有效處理大型程式碼庫並提供精確到行號的實作位置。

## 功能特色

- **智慧檔案過濾**：自動排除非程式碼檔案（測試、設定、文件），使用白名單/黑名單機制
- **雙階段分析架構**：
  - **階段一（LLM-1）**：瀏覽整個專案結構，識別數個與需求最相關的關鍵檔案
  - **階段二（LLM-2）**：對選定的檔案進行深度程式碼分析，定位精確的實作位置
- **精確行號識別**：回報每個函數實作的確切行數範圍
- **執行計畫生成**：提供執行被分析專案的實用指令
- **結構化 JSON 輸出**：以一致且可解析的格式回傳分析結果

## 架構設計
```
使用者輸入（ZIP + 需求描述）
    ↓
檔案過濾（83 個檔案 → 37 個程式碼檔案）
    ↓
LLM-1 導航（37 個檔案 → 6-8 個關鍵檔案）
    ↓
LLM-2 深度分析（精確功能定位）
    ↓
結構化 JSON 報告
```

## 環境需求

- Docker
- OpenAI API 金鑰

## 快速開始

### 方法一：使用命令列（快速測試）
```bash
# 建置 Docker 映像檔
docker build -t agent-app .

# 使用環境變數執行
docker run -p 8000:8000 -e OPENAI_API_KEY="your-api-key" agent-app
```

### 方法二：使用 .env 檔案（建議用於正式部署）
```bash
# 步驟 1：從範本建立 .env 檔案
cp .env.example .env

# 步驟 2：編輯 .env 並加入您的 OpenAI API 金鑰
# OPENAI_API_KEY=sk-your-actual-key-here

# 步驟 3：建置並執行
docker build -t agent-app .
docker run -p 8000:8000 --env-file .env agent-app
```

服務將在 `http://localhost:8000` 啟動

## API 使用說明

### 端點
```
POST /analyze
Content-Type: multipart/form-data
```

### 輸入參數

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `problem_description` | string (表單欄位) | 是 | 要分析的功能的自然語言描述 |
| `code_zip` | file (檔案上傳) | 是 | 包含完整原始碼的 ZIP 檔案 |

### 請求範例

使用 curl：
```bash
curl -X POST "http://localhost:8000/analyze" \
  -F "problem_description=建立一個多頻道論壇 API，支援建立頻道、在頻道中傳送訊息、按時間倒序列出頻道中的訊息" \
  -F "code_zip=@/path/to/your/code.zip"
```

使用 FastAPI 自動文件：
1. 前往 `http://localhost:8000/docs`
2. 找到 `POST /analyze` 端點
3. 點擊「Try it out」
4. 上傳您的 ZIP 檔案並輸入問題描述
5. 點擊「Execute」

### 輸出格式
```json
{
  "feature_analysis": [
    {
      "feature_description": "實現`建立頻道`功能",
      "implementation_location": [
        {
          "file": "src/modules/channel/channel.resolver.ts",
          "function": "createChannel",
          "lines": "12-16"
        },
        {
          "file": "src/modules/channel/channel.service.ts",
          "function": "create",
          "lines": "28-31"
        }
      ]
    }
  ],
  "execution_plan_suggestion": "要執行此專案，應首先執行 `npm install` 安裝依賴，然後執行 `npm run start:dev` 來啟動服務。"
}
```

## 技術實作

### 階段一：檔案導航（LLM-1）

**目的**：從程式碼庫中可能有數百個檔案中，有效識別最相關的檔案。

**流程**：
1. 套用白名單過濾（14 種程式語言副檔名）
2. 套用黑名單過濾（測試檔案、node_modules、建置產物）
3. 將過濾後的檔案清單發送給 GPT-4o-mini
4. 接收數個最可能包含實作的關鍵檔案

**設計理念**：此階段透過聚焦於相關檔案，防止 token 溢出並降低 API 成本。

### 階段二：深度程式碼分析（LLM-2）

**目的**：對選定的檔案進行詳細分析，定位確切的實作位置。

**流程**：
1. 為每個程式碼檔案加上行號
2. 將格式化且帶行號的程式碼發送給 GPT-4o-mini
3. 接收包含精確檔案/函數/行號位置的結構化 JSON

**關鍵特性**：
- 行號標註確保位置回報的準確性
- 模糊路徑比對處理沒有根目錄前綴的檔案
- JSON 驗證與錯誤處理提升穩健性

### 檔案過濾策略

**白名單**（14 種副檔名）：
- 程式語言：.py, .js, .ts, .jsx, .tsx, .java, .go, .cpp, .c, .rs, .rb, .php, .swift, .kt
- Schema 檔案：.gql, .graphql, .proto

**黑名單**（排除）：
- 測試檔案：.test., .spec.
- 相依套件：node_modules/, __pycache__/
- 建置產物：.min.js
- 文件檔案：.md, .txt, .pdf
- 設定檔：.json, .yaml, .env
- 二進位檔案：圖片、影片、壓縮檔

## 錯誤處理

系統包含全面的錯誤處理機制：

- **檔案解碼錯誤**：跳過無法以 UTF-8 解碼的檔案
- **JSON 解析錯誤**：驗證 LLM 輸出並提供清楚的錯誤訊息
- **路徑比對問題**：使用 `endswith()` 模糊比對來處理路徑變化
- **API 失敗**：捕捉並回報 OpenAI API 錯誤

## 專案結構
```
.
├── app.py                 # FastAPI 端點的主應用程式
├── Dockerfile            # Docker 設定檔
├── requirements.txt      # Python 相依套件
├── .env.example         # 環境變數範本
├── .gitignore           # Git 忽略規則
└── README.md            # 本檔案
```

## 開發指南

### 本地開發環境設置
```bash
# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows 系統：venv\Scripts\activate

# 安裝相依套件
pip install -r requirements.txt

# 建立 .env 檔案
cp .env.example .env
# 編輯 .env 並加入您的 API 金鑰

# 本地執行
python app.py
```

### 測試

測試基本連線：
```bash
curl http://localhost:8000/
# 預期結果：{"message": "Hello! API is running!"}
```

## 設計考量

### Prompt Engineering

1. **清楚的角色定義**：系統提示將 LLM 設定為「軟體專案分析專家」
2. **結構化輸出需求**：在提示中提供明確的 JSON schema
3. **上下文管理**：階段一的輸出作為階段二的輸入，保持連貫性
4. **行號強調**：提示中明確要求完整的函數行數範圍

### 工作流程設計

1. **漸進式過濾**：在每個階段縮小搜尋範圍
2. **上下文保留**：在階段之間傳遞必要資訊
3. **驗證檢查點**：每次 LLM 呼叫後進行 JSON schema 驗證
4. **優雅降級**：即使個別檔案失敗也能繼續處理

### 可擴展性考量

- 有效處理擁有 80 個以上檔案的程式碼庫
- 透過雙階段架構優化 token 使用
- 藉由限制上下文至相關檔案來降低成本

## 限制與未來改進

**目前限制**：
- 支援 14 種程式語言（可擴充）
- 每次分析的最大 token 限制：每階段 1500 tokens
- 需要有效的 UTF-8 編碼原始檔案

**潛在增強功能**：
- 支援更多程式語言
- 針對多個功能描述進行批次處理
- 整合版本控制系統
- 自動化測試生成（需求中的加分項目）

## 技術堆疊

- **框架**：FastAPI 0.115.4
- **LLM 提供商**：OpenAI（gpt-4o-mini）
- **語言**：Python 3.11
- **主要套件**：
  - openai 2.7.1
  - uvicorn 0.32.0
  - python-multipart 0.0.12
  - python-dotenv 1.0.1

## 授權

本專案為技術評估的一部分而開發。

## 聯絡方式

如有問題或疑慮，請參考程式碼註解或 `/docs` 的 API 文件。