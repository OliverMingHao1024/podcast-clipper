<div align="center">

<img src="docs/logo.svg" width="128" alt="podcast-clipper logo">

# podcast-clipper

**純音訊 Podcast 的 AI 剪輯助手：一集錄音，變成精華短片、剪好的整集與節目文案**

全程在你自己的電腦上執行・音檔不會離開本機・不用寫程式，雙擊就能用

[快速開始](#快速開始) ・ [功能](#功能) ・ [AI 工具](#ai-工具) ・ [常見問題](#常見問題) ・ [回報問題](https://github.com/OliverMingHao1024/podcast-clipper/issues)

![License](https://img.shields.io/github/license/OliverMingHao1024/podcast-clipper)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![Stars](https://img.shields.io/github/stars/OliverMingHao1024/podcast-clipper?style=flat)

</div>

---

## 這是什麼

錄完一集 Podcast，常見的後製工作是：找出值得單獨分享的片段、剪掉沉默與口誤、再寫節目說明。podcast-clipper 把這些交給「本機語音辨識 ＋ 你自己登入的 AI 命令列工具」處理，你只需要在網頁上確認結果。

- **音檔留在本機**：語音辨識用本機的 Whisper；只有逐字稿文字（開了說話者辨識的話，連講者名字）會送給你選用的 AI 工具。
- **剪輯先審後做**：整集剪輯會先列出每一刀，由你勾選再輸出，AI 不會直接動你的成品。
- **不限 AI 廠牌**：內建 Claude、Codex，也能接其他命令列工具；你用自己的帳號登入，程式不碰憑證。

## 功能

### 挑出精彩短片段

AI 讀完整份逐字稿，挑出約 1～3 分鐘、有完整問答或完整觀點的段落（不會停在半句）。每一段輸出：

| 檔案 | 說明 |
|---|---|
| `clip.mp3` | 該段音檔 |
| `clip.srt` | 對應字幕 |
| `clip.mp4` | 波形影片（直式 1080×1920，也可選方形或橫式），燒入字幕與說話者名字；不會一開始就做，確認名字後按「產生波形影片」才產生 |
| `post.txt` | 貼文用標題、說明與話題標籤 |
| `clips.json` | 所有片段的時間點清單，另保留未入選的備選片段 |

網頁上可依**用途**一鍵帶入建議的片段長度與影片形狀（直式 9:16、方形 1:1、橫式 16:9），也能自訂。這些是建議值，不是平台規則，發布前請確認該平台目前的限制。

沒選上的高分候選會留作**備選**：想要更多片段時，在網頁按「再多挑一段」（或用 `podclip more`），不必重新轉錄、也不用再呼叫 AI。

### 整集剪輯（初剪）

一次處理整集，產出剪好的整集音檔與重新對時的字幕。剪輯清單來自三個來源：

| 來源 | 內容 |
|---|---|
| 沉默 | 超過 0.8 秒的停頓縮短為 0.4 秒 |
| 贅詞 | 整句只有「嗯」「呃」「欸」「額」「唔」之類的片段 |
| AI 判斷 | 講錯重來、錄音事故、離題段落，以及口頭剪輯指令（例如「這段不能用」會剪掉被點名的前一段） |

剪點會自動對齊到附近最安靜的瞬間（最多移動 0.3 秒）；講錯重來、離題這類「內容」剪輯，接縫用 0.1 秒交叉淡化銜接，比硬切自然，沉默與贅詞維持極短的淡化。

每一刀旁有**試聽**按鈕：「聽內容」播放被剪掉的那一段，「聽剪後」播放剪掉之後的銜接（前 4 秒、跳過、後 4 秒；試聽是直接跳過，沒有淡化，成品才有），不用猜就能決定要不要剪；成品頁也能直接播放每個音檔。確認頁最上方有**段落大綱**：每個時間碼附一句話，說明這段在講什麼，方便你判斷哪些該留、哪些該剪。每一刀都能個別取消勾選（3 秒內的短停頓可整批取消），輸出時預設統一音量。

### 集數介紹文案

根據逐字稿產生簡短簡介與「【本集重點】」主題清單，可直接複製貼到節目說明；發布前請自行校對。

### 給不寫程式的人

只在本機執行的網頁介面：拖入音檔、選模式、勾選要剪的地方，成品可一鍵打包成 ZIP 下載，全程不需要打指令。

- **開始前先預估**：依音檔長度顯示語音辨識約幾分鐘、AI 約幾次呼叫（會計入訂閱用量）。辨識時間一開始是參考值，跑過幾次後會改用這台電腦的實測。
- **附上現成字幕檔**：已有 `.srt` 就能附上，直接跳過語音辨識，省下最久的一步。字幕時間要和音檔對得上。
- **環境自我檢查**：標題列的按鈕會逐項檢查 ffmpeg、語音辨識、AI 工具與硬碟空間，並告訴你缺什麼、怎麼補；「連 AI 一起測」會確認 AI 工具已登入。

### 標出誰在說話（選用）

勾選「說話者辨識」並填入人數（網頁預設 3 人；人數必須自己填，程式無法自動判斷），逐字稿與字幕就會標上「講者1、講者2…」。AI 讀得到是誰在講，選段與剪輯建議更容易抓到完整的一問一答。

- **跑完後填名字**：每個人旁邊有 3 段乾淨的樣本可以點開來聽，聽完再填是誰；字幕檔會一起改。
- **記住聲音**：勾選「記住這些人的聲音」，下次的集數會自動認出他們並直接標上名字，不夠確定的句子維持「講者N」。頁首「已記住的聲音」可以查看、刪除、匯出、匯入，也能上傳某個人單獨說話的錄音（約 20 秒以上），新增還沒出現在任何一集的來賓。
- **波形影片**：選了波形影片時不會一開始就做，確定名字後按「產生波形影片」，名字會一起燒進字幕；改名後再按一次會用新名字重做。
- **會有的錯**：程式只能分出「不同的人」，不知道誰是誰。分完後會再用每句話自己的聲音複查一次，補救被長篇發言蓋住的短插話；搶話、笑聲和背景音仍會分錯，請當作草稿。
- **隱私**：記住的是聲音特徵（無法還原成錄音，但能認出一個人），只存在這台電腦的 `podclip-work/voices.json`，不會上傳也不會進 git。請只記住已同意的人，匯出檔自行保管。標了說話者之後，名字也會跟著逐字稿送給你選用的 AI 工具。
- **花費**：第一次使用會下載約 46 MB 的模型；音檔每 10 分鐘約多花 1～1.5 分鐘（一台 16 核心 CPU 實測 58～92 秒）。
- **安裝**：`start.bat`／`start.command` 會自動安裝；網頁上這個選項是灰的的話，見下方常見問題。

## 快速開始

先把專案抓下來（`git clone`，或在 GitHub 按 Code → Download ZIP 後解壓縮）。第一次啟動會自動建立專屬環境並從網路下載所需元件，需要幾分鐘；之後直接開啟。啟動後瀏覽器會自動打開操作頁面，關掉啟動視窗即停止。

| 系統 | 事先安裝 | 啟動 |
|---|---|---|
| Windows | [Python 3.10+](https://www.python.org/downloads/)（勾選 Add python.exe to PATH）、ffmpeg（例如 `winget install ffmpeg`） | 雙擊 `start.bat` |
| macOS | Python 3.10+（`brew install python`）、ffmpeg（`brew install ffmpeg`） | 雙擊 `start.command` |

> macOS 第一次若被系統擋下，對 `start.command` 按右鍵選「打開」；若提示沒有執行權限，先在終端機執行 `chmod +x start.command`。系統內建的 Python 可能版本過舊，請另外安裝。

上傳的音檔與產出的成品都放在專案內的 `podclip-work/`。

### 命令列（進階）

```bash
pip install -e ".[asr,speakers]"        # 本機語音辨識＋說話者辨識（選用）；NVIDIA 顯示卡用 ".[gpu,speakers]"
podclip run episode.mp3                 # 挑精華片段
podclip run episode.mp3 --aspect 1:1 --min-sec 45 --max-sec 120   # 方形影片、指定長度
podclip more out                        # 從備選再切出一段
podclip videos out                      # 產生（或用新名字重做）波形影片
podclip voices list                     # 已記住的聲音（另有 forget / export / import / enroll / add）
podclip voices add 小明 --audio him.wav  # 從只有他說話的錄音新增一個人
podclip edit-plan episode.mp3           # 整集剪輯：先產生清單 plan.json / plan.md
podclip edit-render edit/plan.json      # 套用清單輸出剪好的整集
podclip notes episode_edited.srt        # 集數介紹文案
podclip web                             # 啟動網頁介面
podclip doctor --ai                     # 檢查環境，並測試 AI 工具是否已登入
podclip run episode.mp3 --srt episode.srt   # 用現成字幕，跳過語音辨識
podclip edit-plan episode.mp3 --speakers 3  # 標出誰在說話（run 也可加 --speakers；人數必填）
```

## AI 工具

AI 功能（挑片段、剪輯建議、段落大綱、介紹文案）透過你電腦上**已登入**的命令列工具完成，不需要 API key。

| 工具 | 狀態 | 說明 |
|---|---|---|
| `claude` | 內建 | 以停用所有工具的純文字模式呼叫 |
| `codex` | 內建 | 固定唯讀沙盒、不保存工作階段、不讀使用者設定 |
| 其他 | 自訂 | 任何「從標準輸入讀提示、把回答印到標準輸出」的命令 |

自訂方式：在專案資料夾建立 `podclip-backends.json`，例如 `{"mytool": ["mytool", "--stdin"]}`，重新啟動後會出現在網頁「進階設定 → AI 工具」。這個檔案只在本機讀取，網頁無法新增或修改指令。沒有任何 AI 工具時，整集剪輯仍可只處理沉默與贅詞。

## 常見問題

<details>
<summary>我的音檔會被上傳嗎？</summary>

音檔不會。語音辨識在本機執行；只有逐字稿文字（開了說話者辨識的話，連講者名字）會經由你選的 AI 命令列工具送給該廠商。若不想送出任何內容，整集剪輯可取消「AI 協助」。
</details>

<details>
<summary>需要付費的 API 嗎？</summary>

本專案不需要 API key，也不保存任何憑證。實際費用與用量上限取決於你自己的 AI 工具方案，請以該廠商最新條款為準。
</details>

<details>
<summary>AI 會不會剪過頭？</summary>

可能。所以整集剪輯一律先列清單、由你確認後才輸出；AI 的建議附有說明與逐字稿片段，不想剪的取消勾選即可。
</details>

<details>
<summary>沒有 NVIDIA 顯示卡可以用嗎？</summary>

可以，預設用 CPU，只是辨識比較慢。有 NVIDIA 顯示卡的 Windows 電腦可在進階設定開啟加速（需安裝 `.[gpu]`）。實測 65 分鐘的中文節目，用 RTX 3060 辨識約 160 秒；CPU 用標準品質約是音檔長度的 0.2 倍（一台 16 核心 CPU 實測 0.17～0.23，一小時節目約 12 分鐘），核心較少的電腦會更久。macOS 一律使用 CPU。
</details>

<details>
<summary>支援哪些語言與格式？</summary>

語音辨識使用 Whisper，語言可在進階設定選擇；目前實測以中文節目為主。音訊支援 mp3、m4a、wav、flac、ogg、aac、opus，也接受 mp4、mkv、webm（取音軌）。
</details>

<details>
<summary>說話者辨識的選項是灰的？</summary>

代表選用套件沒有裝成功。重新雙擊啟動檔會自動補裝一次；如果先前安裝失敗過，啟動檔不會每次重試，請先刪除專案裡 `.venv` 資料夾內的 `.no-speakers` 檔再啟動。仍然失敗的話，請開 Issue 並附上安裝畫面的錯誤訊息。
</details>

<details>
<summary>檔案放在哪裡？會自動清理嗎？</summary>

都在專案內的 `podclip-work/`：`uploads`（上傳的音檔副本）、`jobs`（每次處理的成品）、`models`（說話者辨識模型）、`voices.json`（記住的聲音）、`speed.json`（這台電腦的辨識速度）。不會自動清理，長節目會佔不少空間；不要的 `uploads`、`jobs` 底下的資料夾可以直接刪除。刪除 `voices.json` 就會清掉所有記住的聲音。
</details>

<details>
<summary>目前還有哪些沒驗證？</summary>

- macOS 尚未在實機測試（特別是波形影片字幕的字型、說話者辨識套件和 `start.command`）。
- 說話者辨識與記住聲音只在同一組三位講者的中文節目（兩集，各 10～20 分鐘）上抽查過，樣本很小、沒有完整的人工標註；換錄音環境或聲音相近的人可能認錯。聲紋模型以中文語料訓練，其他語言的效果未知。
- 一小時以上整集的完整流程（辨識、說話者、剪輯）還在實測中。
- 剪點對齊與交叉淡化只用合成音檔和長度驗證過，實際聽感還沒有經過人耳確認。
- Gemini 等其他廠牌的 CLI 尚未驗證，請先用自訂檔在自己的電腦上試跑。
</details>

## 開發

```bash
pip install -e ".[dev,asr,speakers]"
pytest
```

測試會用到 ffmpeg；沒有 ffmpeg 或 numpy 時，相關測試會被略過而不是失敗。

## 參與

- 發現問題或有想法：[開 Issue](https://github.com/OliverMingHao1024/podcast-clipper/issues)
- 個人維護的專案，回覆時間不固定，請見諒。

## 致謝

選段的核心概念與提示詞寫法改編自開源專案 [AutoClip](https://github.com/zhouxiaoka/autoclip)（MIT 授權）；本專案為重新實作，授權聲明見 [NOTICE.md](NOTICE.md)。語音辨識使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，說話者辨識使用 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）搭配 pyannote 分段模型（MIT）與 [3D-Speaker](https://github.com/modelscope/3D-Speaker) 聲紋模型（專案為 Apache-2.0；模型權重的條款請見其 ModelScope 頁面，我們沒有逐一查證），影音處理使用 [FFmpeg](https://ffmpeg.org/)。

## 授權

[MIT License](LICENSE)
