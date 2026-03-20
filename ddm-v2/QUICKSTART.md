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
- Engineer: engineer1 / eng123
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

1. 用 engineer1 登入。
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