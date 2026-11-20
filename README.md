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

- **音檔留在本機**：語音辨識用本機的 Whisper；只有逐字稿文字會送給你選用的 AI 工具。
- **剪輯先審後做**：整集剪輯會先列出每一刀，由你勾選再輸出，AI 不會直接動你的成品。
- **不限 AI 廠牌**：內建 Claude、Codex，也能接其他命令列工具；你用自己的帳號登入，程式不碰憑證。

## 功能

### 挑出精彩短片段

AI 讀完整份逐字稿，挑出約 1～3 分鐘、有完整問答或完整觀點的段落（不會停在半句）。每一段輸出：

| 檔案 | 說明 |
|---|---|
| `clip.mp3` | 該段音檔 |
| `clip.srt` | 對應字幕 |
| `clip.mp4` | 1080×1920 直式波形影片，燒入字幕 |
| `post.txt` | 貼文用標題與推薦理由 |
| `clips.json` | 所有片段的時間點清單 |

### 整集剪輯（初剪）

一次處理整集，產出剪好的整集音檔與重新對時的字幕。剪輯清單來自三個來源：

| 來源 | 內容 |
|---|---|
| 沉默 | 超過 0.8 秒的停頓縮短為 0.4 秒 |
| 贅詞 | 整句只有「嗯」「呃」「欸」的片段 |
| AI 判斷 | 講錯重來、錄音事故、離題段落，以及口頭剪輯指令（例如「這段不能用」會剪掉被點名的前一段） |

確認頁最上方有**段落大綱**：每個時間碼附一句話，說明這段在講什麼，方便你判斷哪些該留、哪些該剪。每一刀都能個別取消勾選，輸出時預設統一音量。

### 集數介紹文案

根據逐字稿產生簡短簡介與「【本集重點】」主題清單，可直接複製貼到節目說明；發布前請自行校對。

### 給不寫程式的人

只在本機執行的網頁介面：拖入音檔、選模式、勾選要剪的地方、下載成品，全程不需要打指令。

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
pip install -e ".[asr]"                 # 本機語音辨識；NVIDIA 顯示卡用 ".[gpu]"
podclip run episode.mp3                 # 挑精華片段
podclip edit-plan episode.mp3           # 整集剪輯：先產生清單 plan.json / plan.md
podclip edit-render edit/plan.json      # 套用清單輸出剪好的整集
podclip notes episode_edited.srt        # 集數介紹文案
podclip web                             # 啟動網頁介面
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

音檔不會。語音辨識在本機執行；只有逐字稿文字會經由你選的 AI 命令列工具送給該廠商。若不想送出任何內容，整集剪輯可取消「AI 協助」。
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

可以，預設用 CPU，只是辨識比較慢。有 NVIDIA 顯示卡的 Windows 電腦可在進階設定開啟加速（需安裝 `.[gpu]`）。實測 65 分鐘的中文節目，用 RTX 3060 辨識約 160 秒；CPU 的完整耗時尚未量測。macOS 一律使用 CPU。
</details>

<details>
<summary>支援哪些語言與格式？</summary>

語音辨識使用 Whisper，語言可在進階設定選擇；目前實測以中文節目為主。音訊支援 mp3、m4a、wav、flac、ogg、aac、opus，也接受 mp4、mkv、webm（取音軌）。
</details>

<details>
<summary>目前還有哪些沒驗證？</summary>

macOS 尚未在實機測試（特別是波形影片字幕的字型）、Gemini 等其他廠牌的 CLI 尚未驗證，請先用自訂檔在自己的電腦上試跑。
</details>

## 參與

- 發現問題或有想法：[開 Issue](https://github.com/OliverMingHao1024/podcast-clipper/issues)
- 個人維護的專案，回覆時間不固定，請見諒。

## 致謝

選段的核心概念與提示詞寫法改編自開源專案 [AutoClip](https://github.com/zhouxiaoka/autoclip)（MIT 授權）；本專案為重新實作，授權聲明見 [NOTICE.md](NOTICE.md)。語音辨識使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，影音處理使用 [FFmpeg](https://ffmpeg.org/)。

## 授權

[MIT License](LICENSE)
