# DDM v2 Quick Start

這份文件的目的不是完整規格，而是讓新進來的人在最短時間內把系統跑起來、知道從哪裡看、知道怎麼驗證。

## 1. 你會得到什麼

DDM v2 是一個以 FastAPI 為核心的 Phase 1 release-candidate codebase，主要包含：

- 登入與角色權限
- Master data 管理
- MOST engine 與 workspace
- SOP version 與 action 管理
- Level system sync / save / graph
- Line balance simulation 與 history
- Audit 與 JSON persistence

## 2. 最快啟動方式

```bash
cd ddm-v2
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
uvicorn ddm_v2.main:app --reload --app-dir src
```

啟動後使用：

- 主 UI: http://127.0.0.1:8000
- Control console: http://127.0.0.1:8000/control-console
- API health: http://127.0.0.1:8000/api/v1/health

## 3. Demo 帳號

- Manager: admin / admin123
- Engineer: Avery / avery
- Operator: operator1 / op123

## 4. 最重要的目錄

```text
ddm-v2/
├── src/ddm_v2/main.py                 # App factory
├── src/ddm_v2/api/routes/             # API routes
├── src/ddm_v2/services/               # 核心業務邏輯
├── src/ddm_v2/repositories/store.py   # JSON persistence
├── src/ddm_v2/seeds.py                # 預設資料與 demo accounts
├── src/ddm_v2/static/                 # validation UI 與 control console
├── tests/                             # unit / functional / e2e / regression
├── docs/phase1-functional-spec.zh-TW.md
└── docs/release-candidate-test-coverage.zh-TW.md
```

## 5. 常用指令

### 安裝依賴

```bash
pip install -e .[dev]
```

### 跑完整測試

```bash
PYTHONPATH=src pytest tests/unit tests/functional tests/e2e tests/regression
```

### 分層跑測試

```bash
PYTHONPATH=src pytest tests/unit
PYTHONPATH=src pytest tests/functional
PYTHONPATH=src pytest tests/e2e
PYTHONPATH=src pytest tests/regression
```

### 本機開發啟動

```bash
uvicorn ddm_v2.main:app --reload --app-dir src
```

## 6. 建議閱讀順序

如果你要快速理解系統，建議照這個順序：

1. README.md
2. docs/phase1-functional-spec.zh-TW.md
3. src/ddm_v2/main.py
4. src/ddm_v2/api/routes/sop.py
5. src/ddm_v2/api/routes/level.py
6. src/ddm_v2/api/routes/simulation.py
7. src/ddm_v2/services/most_service.py
8. docs/release-candidate-test-coverage.zh-TW.md

## 7. 第一次驗證建議

如果你剛把系統拉起來，先做下面這一輪：

1. 用 Avery 登入。

## 10. Linux Docker 部署

以下流程假設你的 Linux server 已能用 SSH 登入，且要直接用 Docker Compose 對外提供服務。

### Step 1. 安裝 Docker 與 Compose plugin

以 Ubuntu / Debian 為例：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
	"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
	$(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
	sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

驗證：

```bash
docker --version
docker compose version
```

### Step 2. 上傳專案到 server

可以用 git clone，或直接把目前的 ddm-v2 目錄傳上去：

```bash
scp -r ddm-v2 your-user@your-server:/opt/
ssh your-user@your-server
cd /opt/ddm-v2
```

### Step 3. 建立部署設定

先複製環境檔：

```bash
cp .env.example .env
```

建議至少修改這幾個值：

- `DDM_PORT=8000`
- `DDM_SECRET_KEY=` 改成長且隨機的值
- `DDM_CORS_ALLOW_ORIGINS=` 改成你的網域，例如 `https://ddm.example.com`

如果你之後會放在反向代理後面，也可以先保留容器內是 `8000`，由 Nginx 或 Traefik 對外轉發。

### Step 4. Build 並啟動容器

```bash
docker compose up -d --build
```

檢查狀態：

```bash
docker compose ps
docker compose logs -f
```

### Step 5. 驗證服務是否正常

在 server 本機先驗證：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

若成功，再從瀏覽器打開：

- `http://your-server-ip:8000`
- `http://your-server-ip:8000/control-console`

### Step 6. 放行防火牆

若有開 UFW：

```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

如果你是走 Nginx 反向代理，則通常只需要放行 `80` 與 `443`。

### Step 7. 更新版本

之後每次更新：

```bash
cd /opt/ddm-v2
git pull
docker compose up -d --build
```

### Step 8. 備份資料

目前 runtime data 在 Docker volume `ddm-v2-data` 中，容器內路徑是 `/app/data`。

可先匯出備份：

```bash
docker compose exec ddm-v2 sh -lc 'cp /app/data/runtime-db.json /app/data/runtime-db.backup.json'
```

如果要把 volume 內資料複製到宿主機，再做額外備份，我可以下一步直接幫你補一份可執行的 backup / restore 指令集。
2. 確認 root 頁面與 control-console 都可載入。
3. 建立一個 Draft SOP。
4. 寫入 actions。
5. sync level system。
6. 產生 graph。
7. 跑一次 line balance simulation。
8. 用 manager publish SOP。
9. 到 audit log 確認流程都有記錄。

## 8. 哪裡最常出問題

- seed 帳號與測試期待不一致時，functional / e2e / regression 會一起紅。
- MOST controlled step 若有 X_time_seconds，不能覆蓋掉其他 index contribution。
- SOP 一旦離開 Draft，就不應該再允許更新 actions。
- simulation history 的 create / delete / clear 若沒 audit，RC 追蹤性會不足。

## 9. RC 驗收時應該看什麼

至少確認這四件事：

1. 完整測試全綠。
2. SOP workflow 角色限制正確。
3. simulation history 與 audit trail 一致。
4. db reset / export / save / load 沒有權限外洩。