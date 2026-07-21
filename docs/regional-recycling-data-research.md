# ReLife 地區回收量官方資料研究

> 實作狀態（2026-07-21）：ReLife 現由自有 Supabase 資料庫的
> `regional_recycling_datasets` 與 `regional_recycling_data` 表整合已驗證、
> 已發布及預先排序的地區彙總資料。本文件的官方公開資料研究只用來說明
> 資料來源限制；API 不會從 GPS、IP 或回收點數目推算回收量。

研究日期：2026-07-21。範圍只包括香港政府一手來源（DATA.GOV.HK、環境保護署及香港減廢網站）。

## 結論

截至研究日期，未找到同時具備以下三項條件的香港官方機器可讀資料集：

1. 以十八區或其他 `region`／`district` 劃分；
2. 提供實際回收量 `amount`；
3. 有清楚單位及統計期間。

最可靠的官方回收量資料只有**全港年度都市固體廢物回收量**；最可靠的地區資料則只有**回收物收集點位置**。兩者口徑不同，不能把全港回收量按回收點數目、人口或面積分攤成各區回收量。這樣的分攤值不是官方統計，也無法從現有資料推論。

因此，ReLife `/api/data` 不應把回收點數目命名為「回收垃圾量」，也不應產生看似精確的各區重量。

## 推薦的官方回收量來源

### DATA.GOV.HK：Municipal solid waste recovery quantity

- 穩定資料集識別碼：`hk-epd-statteam-solid-waste-recovery-quantity`
- [官方 package_show metadata API](https://data.gov.hk/en-data/api/3/action/package_show?id=hk-epd-statteam-solid-waste-recovery-quantity)
- [2024 英文 CSV](https://www.epd.gov.hk/epd/sites/default/files/epd/english/environmentinhk/waste/data/files/solid-waste-recovery-quantity-en-2024.csv)
- [官方資料字典 PDF](https://www.epd.gov.hk/epd/sites/default/files/epd/english/environmentinhk/waste/data/files/solid-waste-recovery-quantity-en.pdf)
- [香港減廢網站年度固體廢物統計報告](https://www.wastereduction.gov.hk/en-hk/resources-centre/waste-statistics)

CSV schema：

| 欄位 | 定義 | 單位／格式 |
| --- | --- | --- |
| `year` | 統計參考年份 | `YYYY` |
| `waste_cat_en` | 廢物類別 | 目前各列均為 `Municipal solid waste` |
| `recovery_q` | 回收量 | 公噸（tonnes），數值 |

資料範圍是 2009 至 2024 年；目前 CSV 原始順序為年份由舊至新。例：2024 年 `recovery_q` 為 `2017900` 公噸。metadata 說明更新頻率為每年一次，在年度《Monitoring of Solid Waste》報告發布後於十二月更新。

限制：資料沒有 `region`、`district`、設施或座標欄位，全部數值都是全港總量。CSV 檔名包含年份，下一次更新很可能換成新 URL；整合時應以固定的 package ID／`package_show` 取得當期 resource URL，而不是永久寫死 `...-2024.csv`。

## 最接近的地區資料：回收物收集點

### DATA.GOV.HK：Recyclable Collection Points Data

- 穩定資料集識別碼：`hk-epd-recycteam-waste-less-recyclable-collection-points-data`
- [官方 package_show metadata API](https://data.gov.hk/en-data/api/3/action/package_show?id=hk-epd-recycteam-waste-less-recyclable-collection-points-data)
- [官方下載頁](https://www.wastereduction.gov.hk/zh-hk/resources-centre/recyclable-collection-points-dataset)
- [目前 CSV（2026-07-08 版本）](https://www.wastereduction.gov.hk/sites/default/files/wasteless260708.csv)
- [CSDI 固定 dataset ID](https://portal.csdi.gov.hk/geoportal/?datasetId=epd_rcd_1630899452408_9505)
- [官方資料字典 PDF](https://www.epd.gov.hk/datagovhk/psi-Recyclable-dataDictionary-en.pdf)

目前 CSV 包含：

```text
cp_id, cp_state, district_id,
address_en, address2_en, address_tc, address2_tc, address_sc, address2_sc,
lat, lgt, waste_type, legend, accessibilty_notes,
contact_en, contact_tc, contact_sc,
openhour_en, openhour_tc, openhour_sc
```

`district_id` 是可用的地區欄位，例如 `Kwai_Tsing`、`Tuen_Mun`；`lat`／`lgt` 是位置，`waste_type` 是該收集點接受的物料。資料完全沒有重量、件數、回收交易量或統計期間欄位，因此只能用於「各區回收點數目」、「附近回收點」或「各區可接受物料覆蓋」等指標，不能用作各區回收量。

metadata 說明它只在資料擁有人通知位置有改動時不定期更新。CSV 檔名同樣帶日期，穩定整合入口應採固定 package ID、官方下載頁或 CSDI dataset ID。官方 metadata 沒有承諾資料列排序；客戶端若需要穩定次序，應以 `district_id`、`cp_id` 明確排序。

## 補充官方資料：GREEN@COMMUNITY 2021–2022

[社區回收網絡過往營運數據頁](https://www.wastereduction.gov.hk/en-hk/community-recycling-network-operation-statistics) 提供影片及一頁[官方英文摘要 PDF](https://www.wastereduction.gov.hk/sites/default/files/6green/CRN_Statistic_Video_Transcript_en.pdf)。摘要列出 GREEN@COMMUNITY 全網絡按物料的重量，例如 2021 年合計超過 14,400 公噸、2022 年合計超過 20,300 公噸。

這份資料仍是全網絡總量及物料分類，不是按區或按站數據；它也不是 CSV／JSON API，且只涵蓋 2021–2022 年。可用作歷史背景或人工匯入的全網絡指標，不適合作為 ReLife 地區 API 的持續資料源。

## 授權與可用性

上述 DATA.GOV.HK package metadata 的 `license_id`、`license_title` 均為 `null`，而 `isopen` 為 `false`。不能把資料集描述成 CC BY、CC0 或其他未被 metadata 指明的授權。使用前應以 [DATA.GOV.HK 條款及細則](https://data.gov.hk/en/terms-and-conditions) 及來源部門的最新條款為準，並在 API 文件保留來源、資料期間與擷取日期。

可用性方面，`package_show` 是目前最穩定且可自動發現最新版 resource 的 JSON 入口；實際 CSV URL 都含年份或日期，不能視為永久不變。ReLife 應設定逾時、大小上限、CSV schema 驗證與快取，來源失敗時回傳最後一次已驗證快照及其 `as_of`，不可靜默改用推算數字。

## ReLife 產品選項

### 選項 A：只回傳官方真實回收量（推薦的第一版）

`/api/data` 回傳 `region: "Hong Kong"` 的全港年度回收量，清楚標示 `unit: "tonnes"`、`period: "2024"` 及來源。這符合官方數據，但不宣稱有十八區資料。

### 選項 B：提供地區回收服務覆蓋

按 `district_id` 聚合回收點數目，欄位必須命名為 `collection_point_count`，而不是 `amount` 或 `recycled_amount`。可另按 `waste_type` 提供每區支援物料種類，這是可由官方回收點資料直接計算的指標。

### 選項 C：取得真正地區回收量後再擴充

向環保署／GREEN@COMMUNITY 索取按區或按站、按固定期間統計的原始重量資料；取得後必須保存來源、統計口徑、單位、期間及缺失值規則。只有這種資料才能正式實作「不同地區的 recycled amount」。

### 不可採用

- 不把全港總量依人口、面積或回收點數量分配到十八區。
- 不把回收點數量當成回收物重量。
- 不由使用者 GPS／IP 推算所在地區的回收量；GPS／IP 只可選取地區或附近回收點，不能提升統計資料本身的準確度。
- 不把 2021–2022 GREEN@COMMUNITY 全網絡總量誤標成全港或十八區回收量。
