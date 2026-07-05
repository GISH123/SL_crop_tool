# Poker Crop Tool 使用說明 / Boss Usage README

本工具目前拆成 3 個 EXE，但建議放在同一個資料夾中交付，方便使用者不用到處搬檔案。

建議交付資料夾結構：

```text
Poker_Crop_Tool/
  Step1_Annotation_Tool.exe
  Step2_Crop_By_Annotation.exe
  Step4_Build_Classified_Labels.exe
  README_USAGE.md
  outputs/
  videos/
  datasets/
  ...PyInstaller dependencies
```

---

## 最推薦的工作流

```text
1. Step1_Annotation_Tool.exe
   -> 選影片 / 圖片
   -> 手動畫 ROI
   -> 輸出 XML annotation
   -> 建議存到 outputs/annotations/xxx.xml

2. Step2_Crop_By_Annotation.exe
   -> 選原始影片
   -> 選 Step 1 產生的 XML
   -> 選輸出資料夾，例如 outputs/
   -> 產生 cropped_images_xxx
   -> 可同時建立 original_dataset_xxx/0~52/99 空資料夾

3. 人工分類
   -> 把 cropped_images_xxx 裡的圖片人工放到 original_dataset_xxx/0~52/99 對應資料夾

4. Step4_Build_Classified_Labels.exe
   -> 選人工分類完成的 original_dataset_xxx 資料夾
   -> 自動更新 / 建立每張圖片對應的 LabelMe JSON
```

---

## 重要說明：XML 需不需要手動搬到 Step 2 資料夾？

**不需要。**

新版 `Step2_Crop_By_Annotation.exe` 會開啟檔案選擇視窗，讓你直接選 Step 1 產出的 XML，所以 XML 可以放在任何位置。

不過為了方便管理，建議統一存放在同一個工具資料夾底下，例如：

```text
Poker_Crop_Tool/outputs/annotations/20260604_BAC.xml
```

這樣 Step 2 選檔案時比較不容易找錯。

---

## Step 1：建立 XML Annotation

執行：

```text
Step1_Annotation_Tool.exe
```

用途：

- 選擇影片 / 圖片 / stream URL
- 手動畫每個 ROI 區域
- 儲存 XML annotation

建議輸出位置：

```text
Poker_Crop_Tool/outputs/annotations/xxx.xml
```

如果沒有 `annotations` 資料夾，可以自己建立。

Step 1 完成後會得到類似：

```text
outputs/annotations/20260604_BAC.xml
```

---

## Step 2：根據 XML 裁圖

執行：

```text
Step2_Crop_By_Annotation.exe
```

用途：

- 選擇原始影片
- 選擇 Step 1 產出的 XML annotation
- 根據 XML 裡的 ROI 裁圖
- 自動產生 crop image 和對應 JSON
- 可自動建立 `original_dataset_xxx/0~52/99` 分類資料夾

建議輸出位置：

```text
Poker_Crop_Tool/outputs/
```

Step 2 完成後通常會產生：

```text
outputs/
  cropped_images_<video_name>_<date>/
    image_000001.jpg
    image_000001.json
    image_000002.jpg
    image_000002.json
    ...

  original_dataset_<video_name>_<date>/
    0/
    1/
    2/
    ...
    52/
    99/
```

`cropped_images_xxx` 是裁圖結果。

`original_dataset_xxx` 是人工分類用資料夾。

---

## Step 3：人工分類圖片

目前這一步不是 EXE，自行用檔案總管操作。

把 `cropped_images_xxx` 裡面的圖片，依照正確類別人工搬到：

```text
original_dataset_xxx/0/
original_dataset_xxx/1/
...
original_dataset_xxx/52/
original_dataset_xxx/99/
```

說明：

- `0~52`：正常牌類別
- `99`：不確定 / 錯誤 / 不要的圖片，可依目前專案規則使用

注意：

- 圖片旁邊的 `.json` 可以一起搬，也可以之後讓 Step 4 重新建立 / 修正。
- 最重要的是：圖片最後要放在正確的 folder name 裡，因為 Step 4 會用 folder name 當 label。

---

## Step 4：根據分類資料夾建立 / 修正 LabelMe JSON

執行：

```text
Step4_Build_Classified_Labels.exe
```

用途：

- 選擇人工分類完成的 `original_dataset_xxx` 資料夾
- 自動掃描 `0~52` 和 `99` 子資料夾
- 將每張圖片對應的 JSON label 改成資料夾名稱
- 如果圖片沒有 JSON，會自動建立
- 如果 JSON 已存在，會更新 label、imagePath、imageWidth、imageHeight

完成後，每張圖片旁邊都應該有同名 `.json`：

```text
original_dataset_xxx/12/
  abc_001.jpg
  abc_001.json   <- label 會是 "12"
```

---

## 常見問題

### Q1. Step 1 的 XML 一定要放進 Step 2 的資料夾嗎？

不用。Step 2 會讓你自己選 XML 檔案。

但是建議都放在：

```text
outputs/annotations/
```

比較好管理。

### Q2. 為什麼要把三個 EXE 放同一個資料夾？

比較方便交付和管理。主管只要解壓縮一個 `Poker_Crop_Tool` 資料夾，就能依序執行三個工具。

### Q3. 可以只傳三個 `.exe` 嗎？

不建議。

這是 PyInstaller `onedir` 打包，資料夾裡還有很多 `.dll` 和 dependency。只傳 `.exe` 很可能不能執行。

請傳整個資料夾：

```text
Poker_Crop_Tool/
```

### Q4. EXE 開起來閃退怎麼辦？

請用 debug console 版本重新打包，或從 CMD 執行 EXE 看錯誤訊息。

Debug build 會讓 EXE 開啟時保留黑色 console 視窗，方便看錯誤。

### Q5. 主管電腦需要 Python 嗎？

不需要。

只要你傳的是完整 PyInstaller `dist/Poker_Crop_Tool/` 資料夾，主管電腦不需要安裝 Python。

---

## 建議資料整理方式

如果一個影片叫做：

```text
BAC_20260604.mp4
```

建議整個工作結果整理成：

```text
Poker_Crop_Tool/
  videos/
    BAC_20260604.mp4

  outputs/
    annotations/
      BAC_20260604.xml

    cropped_images_BAC_20260604_xxxxx/
      ...crop images and json...

    original_dataset_BAC_20260604_xxxxx/
      0/
      1/
      ...
      52/
      99/
```

這樣 Step 1、Step 2、Step 4 都能在同一個工具資料夾內完成，不需要來回搬 XML。
