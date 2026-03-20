# Release Candidate Test Coverage

本文件用來回答三個問題：

1. 目前哪些功能已經有自動化測試覆蓋。
2. 這些功能要怎麼手動驗證。
3. 哪些地方仍然屬於 RC 階段的已知邊界。

目前基線：最新一次完整回歸為 32 passed，執行命令為 `PYTHONPATH=src pytest tests/unit tests/functional tests/e2e tests/regression`。

## 1. 目前覆蓋範圍

### 1.1 Unit Test

| 功能域 | 覆蓋內容 | 測試檔案 |
| --- | --- | --- |
| MOST engine | General / Controlled TMU 計算、dynamic X、SIMO 摘要、collaborative 摘要、自動句子與 index string 核心邏輯 | tests/unit/test_most_service.py |
| Level system | level entry 建構、difficulty factor、effective CUB CT、排序保持 | tests/unit/test_level_service.py |
| MOST workspace | workspace payload 轉 SOP action、trace 欄位保存 | tests/unit/test_most_workspace_service.py |
| Line balance | station load、cycle time、UPH 與離子風扇提示 | tests/unit/test_simulation_service.py |
| Store / settings | JSON store 讀寫、reset、設定 fallback | tests/unit/test_store_and_settings.py |

### 1.2 Functional Test

| 功能域 | 覆蓋內容 | 測試檔案 |
| --- | --- | --- |
| Auth / Master data / Audit | 登入、manager CRUD syntax、audit 寫入與非 manager scope | tests/functional/test_auth_and_master.py |
| MOST workspace | workspace save/export、由 workspace actions 寫回 SOP | tests/functional/test_most_workspace_api.py |
| SOP / Level system | SOP actions 更新、sync level、save level、graph 生成、legacy level validate endpoint、SOP workflow 角色限制與狀態規則 | tests/functional/test_sop_and_level_api.py |
| Simulation history | 建立 simulation、history 查詢、manager delete / clear、audit trail | tests/functional/test_simulation_history_api.py |
| System / Data management | root UI、control console、health、db status、save/load/export/reset、manager-only 權限、database reset audit | tests/functional/test_system_api.py |

### 1.3 E2E Test

| 功能域 | 覆蓋內容 | 測試檔案 |
| --- | --- | --- |
| Release candidate 主流程 | 建 SOP、save actions、sync level、save level、generate graph、run simulation、publish、audit | tests/e2e/test_release_candidate_workflow.py |

### 1.4 Regression Test

| 功能域 | 覆蓋內容 | 測試檔案 |
| --- | --- | --- |
| MOST regression | MOST 計算結果與 reference fixture 比對 | tests/regression/test_most_regression.py |
| MOST workspace regression | workspace save/export / SOP trace regression | tests/regression/test_most_workspace_regression.py |

## 2. 手動驗證清單

### 2.1 Auth 與角色權限

1. 用 admin / admin123 登入。
2. 確認可以看到完整資料、audit、db 管理功能。
3. 用 engineer1 / eng123 登入，確認可以建立 SOP 與修改 draft actions，但不能 publish。
4. 用 operator1 / op123 登入，確認只能看到 Published SOP，無法 review / publish。

### 2.2 Master data

1. 以 manager 登入後新增一筆 syntax。
2. 更新該 syntax。
3. 刪除該 syntax。
4. 到 audit 頁面確認 CREATE / UPDATE / DELETE 都有記錄。

### 2.3 MOST engine

1. 建立一筆 General Move，確認 total TMU 與秒數正確。
2. 建立一筆 Controlled Move，填入 X_time_seconds。
3. 確認結果不是只剩 X，而是 A/B/G/M/I/A3 與 dynamic X 一起加總。
4. 建立 SIMO 步驟，確認 summary 有 simo_max_tmu 與 simo_seconds。
5. 建立 collaborative 步驟，確認 summary 有 collaborative_effective_tmu 與 collaborative_effective_seconds。

### 2.4 SOP workflow

1. engineer 建立新的 Draft SOP。
2. 在 Draft 狀態下更新 actions，確認成功。
3. 將狀態改為 Reviewed，確認 reviewed_by / reviewed_at 被寫入。
4. 再次更新 actions，確認被拒絕，因為非 Draft 不可改。
5. 用 engineer 嘗試 publish，應被拒絕。
6. 用 manager publish，確認 published_by / published_at 被寫入。
7. 用 operator 讀取該 SOP，確認 Published 後可見。

### 2.5 Level system

1. 先準備一個已有 actions 的 SOP。
2. 呼叫 sync level，確認 entries 生成。
3. 設定 difficulty_factor、cub_group、machine_count、operator_count。
4. 儲存後確認 effective CUB CT 與 graph 結果合理。

### 2.6 Line balance 與 simulation history

1. 用至少一個 SOP 跑 line balance simulation。
2. 確認 station_results、cycle_time、uph 有值。
3. 查 simulation history，確認可看到新紀錄。
4. 用 engineer 刪除 history，確認被拒絕。
5. 用 manager 刪除單筆 history，確認成功。
6. 再建立一筆 history，然後 clear 全部 history，確認成功。
7. 在 audit 頁面過濾 simulation-result，確認 CREATE / DELETE 有記錄。

### 2.7 Data management

1. 用 manager 開啟 db status，確認 persistent file 路徑與 collection 計數正常。
2. 執行 db save，確認回傳 success。
3. 執行 db load，確認回傳 success。
4. 執行 db export，確認回傳完整 JSON snapshot。
5. 執行 db reset，確認自訂資料被還原，且 audit 出現 RESET。
6. 用 engineer 重試 save / load / export，確認被拒絕。

### 2.8 Dashboard / Audit 檢視

1. 開啟 root page，確認 legacy validation UI 可以載入。
2. 開啟 control-console，確認 smoke-test console 可用。
3. 檢查 audit log 最新紀錄排序是否為新到舊。
4. 用 manager 與 engineer 分別查看 audit，確認非 manager 只看得到自己的紀錄。

## 3. 當前自動化覆蓋邊界

以下項目已部分覆蓋，但仍建議保留人工檢查：

- Legacy UI 的細部互動一致性，目前以 backend 規則與關鍵頁面可載入為主，尚未做到完整 browser-level UI parity。
- 前端視覺操作流程，例如拖拉、欄位互動、複雜表單行為，目前沒有 Playwright 類型測試保護。
- Docker / deployment smoke 目前是 README 與 repo memory 已驗證，未納入 pytest 自動化流程。
- Audit 目前對重要寫操作已有覆蓋，但不是每個 master-data collection 都各自有完整 CRUD functional matrix。

## 4. 建議執行方式

每次 RC 驗收至少做兩件事：

1. 先跑自動化測試：PYTHONPATH=src pytest tests/unit tests/functional tests/e2e tests/regression
2. 再依本文件第 2 節做人工 spot check，特別是 SOP workflow、simulation history、db reset/export 與 legacy UI 載入。