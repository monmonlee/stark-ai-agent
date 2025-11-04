**fastapi 介紹**
* 後端的目的：
    * 向前端提供服務功能，因此可能會有登陸、查看、下載、更改等作用
    * 核心任務：模塊化、統一接口與可擴展，根據模塊不斷拓展，使得功能變更豐富。
* 開發fastapi所需的項目：
    * 工具：需要準備「fastapi包」和「uvicorn」，安裝在虛擬空間
        * uvicorn：把它理解為「啟動http服務」的工具
    * 項目結構：
        fastapi_project/
        ├── app
        │   ├── __init__.py
        │   ├── main.py              # 主入口
        │   ├── api/                 # API 路由
        │   │   ├── __init__.py
        │   │   └── endpoints/       # 各個 API endpoint
        │   ├── models/              # 數據模型（ORM）
        │   ├── schemas/             # Pydantic 模型（驗證）
        │   ├── services/            # 業務邏輯層
        │   └── database/            # 資料庫連接
        ├── tests/                   # 測試檔案(正規開發才用得到) 
        ├── requirements.txt # pip install -r requirement.txt -> -r 就是 “read requirements from file” 的縮寫，pip 會逐行讀取這個檔案並安裝。
        └── README.md
        * 備註：這次開發的ai-agent不需要這麼正式，因為只是快速開發
    * app與服務：
        * 本地端：http://127.0.0.1:8000
        ```python

        from fastapi import FastAPI, UploadFile, File, Form

        app = FastAPI()

        # 第一個API：測試用
        @app.get("/") # 用於定義路由，當有打開是網址結尾是 /結尾時（也就是打開這個首頁），執行以下韓式：
        async def hello():
            return {"message": "Hello! API is running!"}
        ```
        * 路由.get("/")：通常指的是首頁，所以如果變成`@app.get("/about")`就會是「開啟關於頁面」後的動作，另外通常會有函式名稱和路由一致的命名習慣
    * UploadFile 相關方法：.filename(check file name), .size(check file size(bytes)), .read(load file context(bytes)), .file(原始檔案物件)


**fastapi解壓縮**
* 異步函數（async def）與資料讀取問題：
    * async def是非同步，意思就是不需要等待一個全部執行完再執行，因為api可能會是很多不同的人一起使用的，那await代表什麼？
        * async def＋await基本上就是不要讓cpu空耗在那裡，因為可以看到read之類的行為完全就是i/o的工作，所以這段時間寫出await就可以先讓cpu離開去做別的事。
    * cpu/io各自負責什麼？
        * i/o = 讀取與回應http的資料（await會出現在這裡）
        * cpu = 分配記憶體、建立虛擬物件、解壓縮、讀取內部檔案
        * 延伸：await通常都會在io要作業時出現，所以我需要很理解哪部分是i/o或cpu嗎？還是通常會加的都已經固定了不用特別背？
    * 為什麼要載入記憶體才可以處理？
        * 因為這些的處理都要靠cpu，cpu只能操作記憶體（ram）裡面的資料，所以不管是硬碟或是網路，都必須搬到記憶體上才可以處理
        * py的物件（list, class, dict）都會存在ram裡
    * 檔案在何時就變成bytes?
        * 一開始用戶上傳的是zip，但是在http傳輸時就已經被切成TCP封包了（二進位bytes），接下來都一直是bytes，樣子會是「b'PK\x03\x04...'」
        * 一整路都是bytes形式，只是傳輸中是一段段的，放到記憶體時才是一整塊bytes
    * Python 幫你管理的連續記憶體空間，是否就是我之前學習的記憶體區段？
        * 是，如下：
        ```python
            | 區段                               | 功能             | 對應到 Python                       |
            | -------------------------------- | -------------- | -------------------------------- |
            | Text segment                | 放程式碼（可執行指令）    | Python 解譯器本身的機器碼                 |
            | Data segment (static/global) | 放常數、全域變數       | 模組常數、全域物件                        |
            | Heap                         | 動態配置（執行中產生的物件） | 幾乎所有 Python 物件：list, dict, bytes |
            | Stack                        | 函式呼叫與區域變數      | 每個函式呼叫的區域變數、參數                   |
        ```    
        * 所以回傳的檔案都會放在heap
    * 「不要一直把檔案存來存去而是放在記憶體裡」是什麼意思？
        * 意思是就是我們沒有把檔案進一步存到硬碟上，而是用BytesIO直接在記憶體裡面操作，省去讀取硬碟的i/o時間，執行速度極快。
    * 為什麼在zipfile.ZipFile中要變成'io.BytesIO'物件？我看之前zipfile.ZipFile應該是直接吃zip檔案?
        * 原本吃的檔案：原本的`zipfile.ZipFile('my_archive.zip')`吃的是一個檔案路徑，處理的時候「位於磁碟」，因此python打開時會用os讀取實體檔案，一邊讀檔與解析
        * api的檔案：在fastapi裡面，檔案是存在ram而非磁碟，也就是`content = await code_zip.read()`不會有檔案路徑只有原始內容
        * 作法：`io.BytesIO()` ＝ in-memory binary stream，就是存在記憶體裡的虛擬檔案，可以把一串的bytes包裝成「檔案樣子的物件」，這樣zipfile.ZipFile會以為是正常檔案，可以照常處理。


**辨識檔案名稱**
* 檢索邏輯：建立黑名單＆白名單辨識的def，黑名單包含不需要的測試路徑等關鍵字＆不是程式碼的檔案，白名單是大概的程式碼副檔名（參考github linguist）
    * 此 def 最後用any()+ generator comprehension來對應解壓縮的逐一檔名
    * generator comprehension 語法：
        ```python
        # 假設a, b都是list，要比對b是否對應到a
        generator_comprehen = (i in b for i in a)
        # output: <generator object <genexpr> at 0x120234660>
        # 如果要進一步辨識 generator結果：
        for i in list_comprehen # any()期待的物件類別

        list_comprehen = [i in b for i in a]
        # output: [True, False, True, True]
        ```
    * `any()`邏輯：any 吃 generator物件，會返回布林值，處理方式是or（只要有一個是true返回true）
    * 條件流程：
       * 目標是要找「有對應的程式副檔名」，所以白名單的篩選先放前面且結果要返回true（因此要另外設立沒有的話返回false），如果這個是false就可以直接結束條件
       * 目標不希望看到黑名單有返回true的，所以如果true就反回false
       * 三個都有返回true，條件達成，這個檔案可以返回
* 解壓縮檔遍歷：
    * 使用`zf.namelist()`遍歷壓縮檔檔案
    * 每一個迭代物件都送進def read_file_or_not，返回True的就appened到清單中
    