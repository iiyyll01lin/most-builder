# DDM Phase 1 功能規格說明

## 1. 文件目的

本文件整理舊版 DDM Phase 1 系統的完整功能範圍，分析來源如下：

- `/tmp-ddm/ddm_p1_full.html`
- `/tmp-ddm/backend/main.py`
- `/tmp-ddm/docker-compose.yml`
- `/tmp-ddm/Dockerfile`
- `/tmp-ddm/nginx.conf`
- `/tmp-ddm/start.sh`

本規格是提供給重構與後續維護的軟體工程師使用，作為新架構重建時的功能基準與驗收依據。

## 2. 系統定位

此平台屬於工業工程與製程分析工具，核心用途如下：

1. 建立 MiniMOST 動作與工時。
2. 將動作組合成 SOP。
3. 維護 Line Balance 所需的 Level System 約束資料。
4. 進行站位與人員配置模擬。
5. 維護主資料與參考資料。
6. 保留稽核紀錄與資料持久化。

## 3. 舊版架構摘要

### 3.1 前端

- 單一 HTML 檔案。
- 以 CDN 載入 Tailwind、React 18 UMD、ReactDOM 18 UMD、Babel Standalone。
- 所有 UI、狀態、商業邏輯、helper 與 API 呼叫全部集中在同一段 script。
- 無 build pipeline、無 lint、無模組化、無前端測試。

### 3.2 後端

- 單一 FastAPI 檔案。
- 同時包含設定、種子資料、領域邏輯、持久化、Pydantic model 與所有 API route。
- 以 JSON 檔 `data/db_persistent.json` 做持久化。
- 使用 demo 帳號與 token 驗證。

### 3.3 部署

- Nginx 提供前端頁面。
- `/api/` 反向代理到 Uvicorn。
- Docker 將 nginx、backend、frontend 包在同一個 image。

## 4. 角色與權限

### 4.1 系統角色

- Manager
- Engineer
- Operator

### 4.2 權限意圖

- Manager：完整管理權限，包含刪除與 SOP 發布。
- Engineer：可建立與更新大部分工程資料，但不能執行 manager-only 操作。
- Operator：僅能查看有限範圍資料或已發布內容。

## 5. 功能模組

## 5.1 驗證與登入

### 使用者可見行為

- 登入畫面預填 demo 帳密。
- 登入後前端以 bearer token 呼叫 API。
- 登出會清除前端狀態。

### 對應 API

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

## 5.2 Global Context

### 使用者可見行為

- 可選擇 project。
- 可選擇該 project 之下的 SOP version。
- MOST、Level System、SOP Studio 的操作都依賴這個全域上下文。

### 規則

- 未選擇 project 時，MOST 無法正常寫入 SOP。
- 預設優先挑選 Draft 版本。

## 5.3 Dashboard

### 使用者可見行為

- 顯示 project 摘要。
- 顯示 SOP 版本摘要。
- 顯示最近 audit log。

## 5.4 MOST Engine

這是系統核心模組。

### 5.4.1 序列建模

支援兩種序列類型：

- General Move：`A B G A B P A`
- Controlled Move：`A B G M X I A`

### 5.4.2 參數輸入

可設定：

- A、B、G、P、M、X、I 指標
- 回程距離
- 頻率
- SIMO
- 手別
- 協同作業資訊

### 5.4.3 輔助功能

- 距離對應 A/M index 查表
- Tool action 對應規則
- P modifier 切換
- 自動產生 index string
- 自動產生中文 MI 句子
- 直接輸入 JSON 參數並驗證

### 5.4.4 物件與上下文選擇

- 物件搜尋與分類篩選
- 多選物件
- From/To/Reference point 選擇
- 依物件與動作推導手套建議

### 5.4.5 動作模板庫

- 內建常用模板
- 使用者自建模板
- 可編輯模板並拖拉進 Composer

### 5.4.6 Composer

- 拖拉建立步驟
- Timeline / List 兩種視圖
- 編輯、刪除、重排步驟
- 調整頻率
- 切換 CTQ / SIMO

### 5.4.7 MI 顯示區

- 顯示自動生成的 MI 語句
- 顯示 TMU 與秒數摘要
- 維護 WI 動作元件庫
- 支援 WI JSON 匯入匯出

### 5.4.8 MOST 計算服務

對應 API：

- `POST /api/v1/most/calculate`

計算範圍包含：

- 依參數推導 TMU
- 固定值 TMU
- X 秒數轉 TMU
- I 動作視線內外差異
- 頻率乘算
- SIMO 摘要
- 協同作業取最大 operator time
- index string 與自動句子生成
- 手套需求推導

### 5.4.9 儲存至 SOP

- 將 MOST 步驟轉成 SOP action。
- 若未找到 Draft SOP，前端會嘗試自動建立。
- 儲存後同步到 Level System。

## 5.5 Level System

### 使用者可見行為

- 讀取 project 對應的 level entries。
- 編輯每一筆 MI 的 level metadata。
- 拖拉排序。
- 儲存或上傳 level 設定。

### 可編輯欄位

- Difficulty factor
- Adjusted CT
- Number tag
- Number count
- Main sequence
- Order sequence
- Cub group
- Machine count
- Operator count
- Status label
- Sort order

### 對應 API

- `GET /api/v1/level-system/templates`
- `GET /api/v1/level-system/guidelines`
- `POST /api/v1/level-system/validate`
- `GET /api/v1/level-system/{project_id}`
- `POST /api/v1/level-system/sync`
- `POST /api/v1/level-system/save`
- `POST /api/v1/level-system/generate-graph`

### 預期邏輯

- SOP action 同步成 level entries。
- 保留工程師設定的約束資訊。
- Cub 可依 machine/operator 重新換算有效 CT。
- 生成 line-balance 使用的 precedence graph。

## 5.6 SOP Studio

### 使用者可見行為

- 顯示選定 SOP 的版本資訊。
- 顯示 time study 用的影片播放器。
- 顯示 SOP timeline 與步驟圖片。
- 匯出 SOP。
- 推進 SOP 狀態到 Reviewed / Published。

### 對應 API

- `GET /api/v1/sop/versions`
- `POST /api/v1/sop/versions`
- `GET /api/v1/sop/versions/{sop_id}`
- `PUT /api/v1/sop/versions/{sop_id}/status`
- `PUT /api/v1/sop/versions/{sop_id}/actions`

### 工作流規則

- Draft 可轉 Reviewed。
- Reviewed 可轉 Published。
- Manager 可直接從 Draft 發布。
- 只有 Draft 可以改 actions。
- Operator 只能看 Published。

## 5.7 線平衡模擬

### 使用者可見行為

- 管理站位設定。
- 指派員工到站位。
- 拖拉 action 重新分配站位。
- 執行 line-balance simulation。
- 查看 overloaded station、瓶頸、cycle time、UPH、balance rate、alerts、手套需求、CTQ、ion fan 需求。
- 顯示 Yamazumi chart。
- 查看模擬歷史。
- 匯出報表。

### 對應 API

- `GET /api/v1/master/stations`
- `POST /api/v1/master/stations`
- `PUT /api/v1/master/stations/{station_id}`
- `DELETE /api/v1/master/stations/{station_id}`
- `POST /api/v1/simulation/line-balance`
- `POST /api/v1/simulation/reassign-action`
- `GET /api/v1/simulation/history`
- `GET /api/v1/simulation/history/{sim_id}`
- `DELETE /api/v1/simulation/history/{sim_id}`
- `DELETE /api/v1/simulation/history`

### 模擬邏輯

- 依 station 彙整 SOP actions。
- 以 action seconds 計算標準工時。
- 套用 employee efficiency factor 得到實際工時。
- 檢查 takt overload。
- 檢查 novice 人員是否被分配 CTQ 動作。
- 彙整手套需求與 ion fan 需求。
- 計算 bottleneck、cycle time、UPH、balance rate。
- 儲存 simulation history。

## 5.8 主資料管理

### 可管理實體

- Syntax library
- Component library
- Tool library
- Location library
- Object library
- Employee library
- Station library

### 只讀參考資料

- From locations
- To locations
- Reference points
- Precautions
- Glove rules
- Ion-fan bindings
- MI naming rules
- Level templates
- Level guidelines

### 對應 API

- `/api/v1/master/syntax`
- `/api/v1/master/components`
- `/api/v1/master/tools`
- `/api/v1/master/locations`
- `/api/v1/master/objects`
- `/api/v1/master/employees`
- `/api/v1/master/stations`
- `/api/v1/master/from-locations`
- `/api/v1/master/to-locations`
- `/api/v1/master/reference-points`
- `/api/v1/master/precautions`
- `/api/v1/master/glove-rules`
- `/api/v1/master/ion-fan-bindings`
- `/api/v1/master/mi-naming`

### 權限規則

- Operator 不可建立或修改主資料。
- 刪除通常限定 Manager。

## 5.9 MI 命名驗證

### 使用者可見行為

- 依規則動態生成命名欄位。
- 使用者可主動觸發驗證。
- 系統回傳建議名稱。

### 對應 API

- `POST /api/v1/mi-naming/validate`

## 5.10 手套需求推導

### 使用者可見行為

- 在 MOST 編輯時預覽手套建議。
- 在 line-balance 結果中顯示手套需求。

### 對應 API

- `POST /api/v1/gloves/check`

## 5.11 稽核紀錄

### 使用者可見行為

- Dashboard 與 Audit 頁面可查看最近或過濾後的操作紀錄。

### 對應 API

- `GET /api/v1/audit/logs`

### 規則

- Manager 可看較完整範圍。
- 非 manager 僅能看自己的操作。

## 5.12 資料持久化與匯出

### 使用者可見行為

- 查看持久化狀態。
- 手動儲存資料。
- 匯出完整資料庫快照。

### 對應 API

- `POST /api/v1/db/save`
- `POST /api/v1/db/load`
- `GET /api/v1/db/status`
- `DELETE /api/v1/db/reset`
- `GET /api/v1/db/export`

## 6. 主要資料領域

舊系統的持久化核心資料包含：

- Users
- Projects
- Syntax library
- Component library
- Tool library
- Location library
- Object library
- Employees
- Stations
- SOP versions
- Level entries
- Audit logs
- Simulation results
- 其他手套、ion fan、MI naming、guideline 等參考資料

## 7. 舊版非功能性特徵

### 優點

- 原型開發速度快。
- 單一部署產物即可執行完整流程。
- 大量商業規則已具體落在程式中。

### 風險

- 前後端都為 monolith。
- 前後端邏輯重複，容易不一致。
- UI 與 API 無型別化契約。
- 難以測試。
- 狀態高度耦合。
- JSON 檔持久化不具交易能力。
- 無 migration 策略。
- 沒有 release 等級自動化測試。

## 8. 已知缺口與不一致

以下是重構時必須正視的缺口：

1. 前端呼叫 `/api/v1/most/validate-level`，但後端沒有對應 route。
2. 部分 delete endpoint 在後端程式中有不正確巢狀，可能導致 route 未如預期註冊。
3. MI naming 的自動驗證流程曾因無限呼叫而被停用。
4. 相似商業邏輯同時存在前端與後端，存在分岐風險。
5. Station 狀態一部分由前端本地管理，一部分由後端持久化，資料來源不單一。
6. 畫面、流程、計算、持久化全混在同一層級，維護成本極高。

## 9. 對新系統的重建要求

新 codebase 至少必須保留以下能力：

1. 角色感知的登入與授權。
2. MOST 步驟編輯與序列型別差異處理。
3. 正確的 TMU/時間計算，包含 frequency、SIMO、collaborative。
4. SOP 版本與狀態工作流。
5. Level System 同步、編輯與 graph generation。
6. 具備人員效率與警示邏輯的線平衡模擬。
7. 主資料 CRUD 與參考資料存取。
8. 稽核與持久化。
9. 工程師需要的匯入匯出流程。

此外，新系統應補強：

1. 模組化架構。
2. 清楚的 domain boundary。
3. Unit、functional、E2E、regression 自動化測試。
4. 可重現的本地開發流程。
5. 可作為 release candidate 的品質關卡。
