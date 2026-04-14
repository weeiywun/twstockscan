# StockRadar 選股雷達

台股選股追蹤系統，部署於 GitHub Pages。

## 架構說明

```
index.html          ← 主應用程式（單一檔案，可獨立運作）
data/
  chips_big_holder.json   ← 千張大戶策略結果
  (未來新增其他策略 JSON)
```

## 新增選股策略步驟

1. 在 `index.html` 的 `STRATEGIES` 陣列加入新策略物件
2. 將結果 JSON 放到 `data/` 資料夾
3. 在 `DATA` 物件中加入對應的 `dataKey`（或改用 fetch 動態載入）

## 自動更新

搭配 GAS（Google Apps Script）每週五執行：
1. 抓取集保開放資料 + TWSE 成交量
2. 計算篩選條件
3. 更新 GitHub repo 中的 JSON 資料檔

## 部署

1. Fork 此 repo
2. Settings → Pages → Source: main branch / root
3. 完成
