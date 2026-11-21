"""The single page served by ``podclip web``. Model-written text is only inserted with textContent."""

PAGE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Podcast 剪輯工具</title>
<style>
/* Bento design tokens (typeui.sh "bento" skill, MIT): primary #FAD4C0, secondary #80A1C1, surface #FFF5E6, text #111827,
   spacing 4/8/12/16/24/32, radii 4/8 for controls (tiles use 16). Text on tinted fills always uses --ink. */
:root{--surface:#FFF5E6;--card:#FFFFFF;--ink:#111827;--mute:#4B5563;--line:#EADCC8;--primary:#FAD4C0;--secondary:#80A1C1;--link:#2F5780;
--ok:#15803D;--warn:#B45309;--bad:#B91C1C;--s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--s6:32px;--r-ctl:8px;--r-tile:16px;
--hero:color-mix(in srgb,var(--primary) 70%,var(--card));--font:Inter,system-ui,"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;--mono:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--surface:#17130F;--card:#211C17;--ink:#F6EFE6;--mute:#B5AA9B;--line:#383028;--link:#9DBBDA;--hero:color-mix(in srgb,var(--primary) 14%,var(--card));--ok:#4ADE80;--warn:#FBBF24;--bad:#F87171}}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;background:var(--surface);color:var(--ink);font:16px/1.6 var(--font)}
main{max-width:1040px;margin:0 auto;padding:var(--s5) var(--s4) 64px}
h1{font-size:32px;line-height:1.2;margin:0 0 var(--s1)}h2{font-size:20px;line-height:1.3;margin:0 0 var(--s3)}
.sub{color:var(--mute);font-size:14px;margin:0}
.label{font:12px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 var(--s2)}
.bento{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--s4)}
.bento>*{grid-column:span 12}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-tile);padding:var(--s5)}
.bento>.span7{grid-column:span 7}.bento>.span5{grid-column:span 5}
@media (max-width:760px){.bento>.span7,.bento>.span5{grid-column:span 12}}
.hero{display:flex;gap:var(--s4);align-items:center;background:linear-gradient(135deg,var(--hero),var(--card) 85%)}
.hero svg{width:72px;height:72px;flex:none;filter:drop-shadow(0 4px 8px rgba(17,24,39,.2))}
.steps{margin:0;padding-left:var(--s5);color:var(--mute);font-size:14px}.steps li{margin:var(--s2) 0}.steps b{color:var(--ink)}
.drop{border:2px dashed var(--secondary);border-radius:var(--r-tile);padding:var(--s6) var(--s4);text-align:center;color:var(--mute);cursor:pointer;background:color-mix(in srgb,var(--secondary) 10%,var(--card))}
.drop:hover,.drop.over{border-color:var(--ink);color:var(--ink)}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:var(--s4);margin-bottom:var(--s4)}
@media (max-width:560px){.modes{grid-template-columns:1fr}}
.mode{border:2px solid var(--line);border-radius:var(--r-tile);padding:var(--s4) var(--s5);cursor:pointer;display:block;background:var(--card)}
.mode input{margin-right:var(--s2)}.mode b{font-size:20px}.mode span{display:block;color:var(--mute);font-size:14px;margin-top:var(--s1)}
.mode:has(input:checked){border-color:var(--ink);background:color-mix(in srgb,var(--primary) 45%,var(--card))}
.mode:has(input:checked) span{color:var(--ink)}
label.row{display:flex;gap:var(--s3);align-items:center;margin:var(--s2) 0;flex-wrap:wrap}
label.row>span{min-width:9em;color:var(--mute);font-size:14px}
select,input[type=number]{font:inherit;padding:6px var(--s2);border:1px solid var(--line);border-radius:var(--r-ctl);background:var(--card);color:var(--ink)}
input[type=checkbox],input[type=radio]{accent-color:var(--link)}
button{font:inherit;border:1px solid var(--ink);border-radius:var(--r-ctl);padding:10px var(--s5);cursor:pointer;background:var(--primary);color:#111827;font-weight:600}
button:hover:not(:disabled){background:color-mix(in srgb,var(--primary) 82%,#000)}
button.ghost{background:transparent;color:var(--ink);border-color:var(--line);font-weight:400}
button.ghost:hover:not(:disabled){background:color-mix(in srgb,var(--primary) 30%,transparent)}
button:disabled{opacity:.5;cursor:not-allowed}
:is(button,select,input,summary,.drop,.mode):focus-visible{outline:3px solid var(--link);outline-offset:2px}
.bar{height:8px;background:var(--line);border-radius:var(--r-ctl);overflow:hidden;margin-top:var(--s3)}
.bar>i{display:block;height:100%;width:0;background:var(--secondary);transition:width .2s}
.bar.busy>i{width:40%;animation:slide 1.2s infinite ease-in-out}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
@media (prefers-reduced-motion:reduce){.bar.busy>i{animation:none;width:100%;opacity:.5}.bar>i{transition:none}}
.note{padding:var(--s3);border-radius:var(--r-ctl);border:1px solid var(--line);margin-top:var(--s3);font-size:14px;background:var(--card)}
.note.warn{border-color:var(--warn);color:var(--warn)}.note.bad{border-color:var(--bad);color:var(--bad)}
pre{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);padding:var(--s3);max-height:240px;overflow:auto;font:13px/1.5 var(--mono);white-space:pre-wrap;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:var(--s2);border-bottom:1px solid var(--line);vertical-align:top}
th{font:12px/1 var(--mono);text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
td.mute{color:var(--mute);font-family:var(--mono);font-size:13px}
.files a{display:block;padding:var(--s2) 0;color:var(--link);word-break:break-all;text-decoration-thickness:1px;text-underline-offset:3px}
.actions{display:flex;gap:var(--s3);margin-top:var(--s4);flex-wrap:wrap;align-items:center}
.outline{list-style:none;margin:0;padding:var(--s3);background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);max-height:420px;overflow:auto;font-size:14px}
.outline li{display:flex;gap:var(--s3);padding:var(--s1) 0}.outline time{font:13px var(--mono);color:var(--link);min-width:4.5em}
.noOutline>#cuts{grid-column:span 12}
.check{display:flex;gap:var(--s3);padding:var(--s2) 0;border-bottom:1px solid var(--line);align-items:baseline}.check b{min-width:1.5em;text-align:center}.check .d{color:var(--mute);font-size:14px}.check .f{display:block;color:var(--mute);font-size:13px}.check.ok b{color:var(--ok)}.check.warn b{color:var(--warn)}.check.fail b{color:var(--bad)}.estimate{background:color-mix(in srgb,var(--primary) 25%,var(--card));border-radius:var(--r-ctl);padding:var(--s3);margin-top:var(--s4);font-size:14px}.estimate small{display:block;color:var(--mute);margin-top:var(--s1)}
.mini{padding:2px 8px;font-size:13px;font-weight:400;white-space:nowrap}
.listen{display:flex;gap:var(--s3);align-items:center;flex-wrap:wrap;margin:0 0 var(--s3)}.listen audio{height:36px;max-width:100%}
.result{padding:var(--s2) 0;border-bottom:1px solid var(--line)}.result audio{display:block;width:100%;margin-top:var(--s1)}
details{margin-top:var(--s3)}summary{cursor:pointer;color:var(--mute);font-size:14px}
</style>
</head>
<body>
<main class="bento">
<header class="card hero">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="podcast-clipper"> <title>podcast-clipper</title> <defs> <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"> <stop offset="0" stop-color="#FFF8EE"/> <stop offset="1" stop-color="#FAD4C0"/> </linearGradient> </defs> <rect x="64" y="64" width="896" height="896" rx="204" fill="url(#lg)"/> <rect x="65" y="65" width="894" height="894" rx="203" fill="none" stroke="#111827" stroke-opacity=".1" stroke-width="2"/> <path d="M800 190 Q808.28 227.72 846 236 Q808.28 244.28 800 282 Q791.72 244.28 754 236 Q791.72 227.72 800 190Z" fill="#FFFFFF" stroke="#111827" stroke-width="10" stroke-linejoin="round"/> <path d="M236 300 Q241.4 324.6 266 330 Q241.4 335.4 236 360 Q230.6 335.4 206 330 Q230.6 324.6 236 300Z" fill="#FFFFFF" stroke="#111827" stroke-width="10" stroke-linejoin="round"/> <g fill="none" stroke="#111827" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"> <path d="M270 470 V520 A242 242 0 0 0 754 520 V470"/> <path d="M512 762 V826"/> </g> <rect x="396" y="818" width="232" height="52" rx="26" fill="#111827"/> <rect x="322" y="170" width="380" height="420" rx="190" fill="#80A1C1" stroke="#111827" stroke-width="22"/> <ellipse cx="408" cy="262" rx="40" ry="62" fill="#FFFFFF" fill-opacity=".28" transform="rotate(-18 408 262)"/> <ellipse cx="452" cy="366" rx="22" ry="30" fill="#111827"/> <ellipse cx="572" cy="366" rx="22" ry="30" fill="#111827"/> <circle cx="459" cy="355" r="8" fill="#FFFFFF"/> <circle cx="579" cy="355" r="8" fill="#FFFFFF"/> <ellipse cx="398" cy="430" rx="40" ry="24" fill="#F4A58A" fill-opacity=".85"/> <ellipse cx="626" cy="430" rx="40" ry="24" fill="#F4A58A" fill-opacity=".85"/> <path d="M482 424 Q512 458 542 424" fill="none" stroke="#111827" stroke-width="14" stroke-linecap="round"/> </svg>
  <div>
    <h1>Podcast 剪輯工具</h1>
    <p class="sub">全程在你自己的電腦上執行，音檔不會上傳到任何地方（AI 建議只透過你本機已登入的 AI 命令列工具取得）。</p>
  </div>
  <button class="ghost mini" id="doctorbtn" style="margin-left:auto">環境自我檢查</button>
</header>
<div id="envnote"></div>
<section class="card" id="sdoctor" hidden>
  <h2>環境自我檢查</h2>
  <div id="doctorrows"></div>
  <div class="actions"><button class="ghost" id="doctorredo">重新檢查</button><button class="ghost" id="doctorai">連 AI 一起測</button></div>
  <p class="sub" style="margin-top:8px">「連 AI 一起測」會送出一個很短的提問，確認 AI 工具已登入，會用掉極少量的用量。</p>
</section>

<section class="card span7" id="s1">
  <p class="label">步驟 1</p>
  <h2>選音檔</h2>
  <div class="drop" id="drop" tabindex="0" role="button">把音檔拖到這裡，或點一下選擇<br><small>mp3 / m4a / wav / flac / ogg / mp4 等</small></div>
  <input type="file" id="file" hidden accept="audio/*,video/mp4,video/webm,video/x-matroska,.mp3,.m4a,.wav,.flac,.ogg,.aac,.opus,.mp4,.mkv,.webm">
  <div class="bar" id="upbar" hidden><i></i></div>
  <p id="upmsg" class="sub" style="margin-top:8px" aria-live="polite"></p>
  <div id="srtbox" hidden style="margin-top:12px">
    <button class="ghost mini" id="srtbtn">附上字幕檔（選填，可跳過語音辨識）</button>
    <input type="file" id="srtfile" hidden accept=".srt">
    <span class="sub" id="srtmsg" aria-live="polite"></span>
  </div>
</section>

<aside class="card span5">
  <p class="label">流程</p>
  <h2>三步完成</h2>
  <ol class="steps">
    <li><b>選音檔</b>：拖進來就好。</li>
    <li><b>選要做什麼</b>：挑精彩片段，或整集剪輯。</li>
    <li><b>確認並下載</b>：整集剪輯會先給你勾選要剪的地方。</li>
  </ol>
</aside>

<section class="card" id="s2" hidden>
  <p class="label">步驟 2</p>
  <h2>你想做什麼？</h2>
  <div class="modes">
    <label class="mode"><input type="radio" name="mode" value="clips" checked><b>挑出精彩短片段</b><span>AI 找出約 1～3 分鐘、適合分享的段落，各自輸出音檔、字幕與影片。</span></label>
    <label class="mode"><input type="radio" name="mode" value="plan"><b>整集剪輯</b><span>去掉長沉默、嗯呃、講錯重來。先給你勾選確認，再輸出剪好的整集。</span></label>
  </div>
  <div id="optClips">
    <label class="row"><span>要輸出</span>
      <label><input type="checkbox" class="fmt" value="audio" checked> 音檔</label>
      <label><input type="checkbox" class="fmt" value="srt" checked> 字幕</label>
      <label><input type="checkbox" class="fmt" value="video"> 波形影片（先不產生，確認說話者名字後再按鈕產生）</label></label>
    <label class="row"><span>用途</span><select id="preset">
      <option value="short">直式短影音（Reels／Shorts／TikTok／抖音）</option>
      <option value="square">方形貼文（IG／Facebook／Threads）</option>
      <option value="wide">橫式影片（YouTube／Facebook）</option>
      <option value="teaser">Podcast 精華預告（較長）</option>
      <option value="custom">自訂長度與形狀</option>
    </select></label>
    <label class="row"><span>片段長度（秒）</span><input type="number" id="minSec" min="10" max="600" aria-label="最短秒數"> 到 <input type="number" id="maxSec" min="10" max="900" aria-label="最長秒數"></label>
    <label class="row"><span>影片形狀</span><select id="aspect"><option value="9:16">直式 9:16</option><option value="1:1">方形 1:1</option><option value="16:9">橫式 16:9</option></select></label>
    <label class="row"><span>最多幾段</span><input type="number" id="maxClips" value="10" min="1" max="30"></label>
  </div>
  <label class="row" id="srtrow" hidden><span>字幕檔</span><label><input type="checkbox" id="useSrt" checked> 使用我附上的字幕檔，跳過語音辨識（時間要和這個音檔對得上）</label></label>
  <label class="row" id="spkrow"><span>說話者辨識</span><label><input type="checkbox" id="useSpk"> 標出誰在說話，共 <input type="number" id="spkN" value="3" min="2" max="8" aria-label="說話的人數"> 人</label>
    <small class="sub" id="spkhint">第一次會下載約 46 MB 的模型；音檔每 10 分鐘約多花 1 分鐘。人數要填對才準。</small></label>
  <div id="optPlan" hidden>
    <label class="row"><span>AI 協助</span><label><input type="checkbox" id="useAI" checked> 讓 AI 找出講錯重來與雜音事故（需要本機已登入 AI 命令列工具）</label></label>
  </div>
  <details><summary>進階設定</summary>
    <label class="row" id="backendrow"><span>AI 工具</span><select id="backend"></select></label>
    <label class="row"><span>語音辨識品質</span><select id="whisper"><option value="tiny">最快（較不準）</option><option value="base">快</option><option value="small" selected>標準</option><option value="medium">最準（很慢）</option></select></label>
    <label class="row"><span>說話語言</span><select id="lang"><option value="">自動偵測</option><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option></select></label>
    <label class="row"><span>說明文字語言</span><select id="tlang"><option>繁體中文</option><option>简体中文</option><option>English</option><option>日本語</option></select></label>
    <label class="row" id="gpurow"><span>使用顯示卡加速</span><select id="device"><option value="cpu" selected>否（較穩）</option><option value="cuda">是（NVIDIA，需另外安裝）</option></select></label>
  </details>
  <div class="estimate" id="estimate" hidden></div>
  <div class="actions"><button id="go">開始</button></div>
</section>

<section class="card" id="s3" hidden>
  <h2 id="runtitle">處理中…</h2>
  <div class="bar busy" id="runbar"><i></i></div>
  <p id="runmsg" class="sub" style="margin-top:8px" aria-live="polite"></p>
  <details><summary>詳細紀錄</summary><pre id="log"></pre></details>
  <div class="actions"><button class="ghost" id="cancel">取消</button></div>
</section>

<div id="s4" class="bento" hidden>
  <section class="card span5" id="outlinebox" hidden>
    <p class="label">步驟 3</p>
    <h2>段落大綱</h2>
    <p class="sub" style="margin-bottom:12px">原音檔時間，每段一句話說明在講什麼。</p>
    <ul id="outline" class="outline"></ul>
  </section>
  <section class="card span7" id="cuts">
    <p class="label">步驟 3</p>
    <h2>確認要剪掉的地方</h2>
    <p class="sub" id="planinfo" style="margin-bottom:12px"></p>
    <div class="listen"><audio id="auditor" controls preload="metadata"></audio><span class="sub" id="earmsg" aria-live="polite">按每一列的「聽內容」或「聽剪後」試聽原音檔。</span></div>
    <table><thead><tr><th>剪掉</th><th>時間</th><th>類型</th><th>說明／逐字稿</th><th>試聽</th></tr></thead><tbody id="planrows"></tbody></table>
    <label class="row" id="silrow"><input type="checkbox" id="silall" checked> <span style="min-width:0;color:var(--ink)" id="sillabel"></span></label>
    <div class="actions">
      <select id="outfmt" aria-label="輸出格式"><option value=".mp3">mp3</option><option value=".m4a">m4a</option><option value=".wav">wav</option></select>
      <label><input type="checkbox" id="norm" checked> 統一音量</label>
      <button id="render">套用並輸出整集</button>
    </div>
  </section>
</div>

<div id="s5" class="bento" hidden>
  <section class="card span7">
    <p class="label">完成</p>
    <h2 id="donetitle">完成</h2>
    <div id="donenote"></div>
    <div class="actions" style="margin:0 0 12px"><button id="zipbtn">下載全部（ZIP）</button><button class="ghost" id="morebtn" hidden>再多挑一段</button><button id="videobtn" hidden>產生波形影片</button></div>
    <p class="sub" id="videohint" hidden style="margin-bottom:12px">影片會把字幕與說話者名字燒進去，所以請先在下方確認名字再按。改了名字後再按一次，會用新名字重新產生。</p>
    <div class="files" id="files"></div>
    <p class="sub" id="where" style="margin-top:12px"></p>
    <div class="actions"><button class="ghost" onclick="location.reload()">處理另一個檔案</button></div>
  </section>
  <section class="card span5" id="notesbox">
    <p class="label">節目文案</p>
    <h2>本集介紹</h2>
    <div class="actions" style="margin-top:0"><button class="ghost" id="notesbtn">產生本集介紹文案</button></div>
    <p class="sub" id="notesmsg" style="margin-top:8px" aria-live="polite"></p>
    <pre id="notestext" hidden></pre>
    <div class="actions"><button class="ghost" id="notescopy" hidden>複製文案</button></div>
  </section>
</div>
<section class="card" id="spkbox" hidden>
  <p class="label">說話者</p>
  <h2>誰是誰？填上名字</h2>
  <p class="sub" style="margin-bottom:12px">程式只能分出「不同的人」，不知道誰是誰，也可能分錯。對照每個人的幾句話，填上名字，會改寫字幕檔與之後輸出的文字稿；波形影片等你確定名字後再按「產生波形影片」才會做，名字才會燒進去。</p>
  <div id="spkrows"></div>
  <div class="actions"><button id="spksave">套用名字</button><span class="sub" id="spkmsg" aria-live="polite"></span></div>
</section>
</main>
<script>
const T = "__TOKEN__";
const $ = s => document.querySelector(s);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };
const show = (id, on = true) => { $(id).hidden = !on; };
async function api(path, opts = {}) {
  const r = await fetch(path, {...opts, headers: {"X-Token": T, ...(opts.headers || {})}});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const post = (path, body) => api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
const clock = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
let hasSrt = false, upload = null, jobId = null, planJob = null, planCuts = [], where = "";

api("/api/env").then(env => {
  where = env.workdir;
  if (env.platform === "darwin") { $("#gpurow").hidden = true; $("#device").value = "cpu"; }
  const box = $("#envnote");
  const add = (cls, text) => { const n = el("div", text, "note " + cls); box.appendChild(n); };
  if (!env.ffmpeg) add("bad", "找不到 ffmpeg，無法切音檔。請先安裝 ffmpeg（見 README）。");
  if (!env.speakers) { $("#useSpk").disabled = true; $("#spkN").disabled = true; $("#spkhint").textContent = "尚未安裝這個選用功能：關掉視窗，重新雙擊啟動檔會自動安裝。"; }
  if (!env.whisper) add("bad", "尚未安裝語音辨識（faster-whisper）。請用 start.bat 啟動，或依 README 安裝。");
  const sel = $("#backend"); let first = null;
  env.backends.forEach(b => { const o = el("option", b.name + (b.ready ? "" : "（未安裝）")); o.value = b.name; o.disabled = !b.ready; sel.appendChild(o); if (b.ready && !first) first = b.name; });
  if (first) sel.value = first;
  else add("warn", "找不到任何 AI 命令列工具（claude、codex…）：AI 選段、AI 剪輯建議與介紹文案將無法使用。整集剪輯可取消勾選「AI 協助」。");
});

const drop = $("#drop"), input = $("#file");
drop.onclick = () => input.click();
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
input.onchange = () => input.files[0] && sendFile(input.files[0]);
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && sendFile(e.dataTransfer.files[0]); };

function sendFile(file) {
  const bar = $("#upbar"); show("#upbar"); bar.firstElementChild.style.width = "0";
  $("#upmsg").textContent = "上傳到本機工作資料夾：" + file.name;
  const x = new XMLHttpRequest();
  x.open("PUT", "/api/upload?name=" + encodeURIComponent(file.name));
  x.setRequestHeader("X-Token", T);
  x.upload.onprogress = e => { if (e.lengthComputable) bar.firstElementChild.style.width = (100 * e.loaded / e.total) + "%"; };
  x.onload = () => {
    let data = {}; try { data = JSON.parse(x.responseText); } catch (_) {}
    if (x.status !== 200) { $("#upmsg").textContent = "失敗：" + (data.error || x.status); return; }
    upload = data; hasSrt = false; $("#upmsg").textContent = "已選擇：" + data.name + (data.duration ? "（約 " + Math.round(data.duration / 60) + " 分鐘）" : "");
    show("#srtbox"); $("#srtmsg").textContent = ""; show("#srtrow", false); show("#s2"); refreshEstimate();
  };
  x.onerror = () => { $("#upmsg").textContent = "上傳失敗"; };
  x.send(file);
}

const modeOf = () => document.querySelector("input[name=mode]:checked").value;
document.querySelectorAll("input[name=mode]").forEach(r => r.onchange = () => {
  show("#optClips", modeOf() === "clips"); show("#optPlan", modeOf() === "plan");
});

// Suggested lengths per use, not platform rules: check the platform's current limits before posting.
const PRESETS = {short: [30, 90, "9:16"], square: [45, 120, "1:1"], wide: [60, 180, "16:9"], teaser: [60, 180, "9:16"]};
function applyPreset() {
  const p = PRESETS[$("#preset").value];
  if (p) { $("#minSec").value = p[0]; $("#maxSec").value = p[1]; $("#aspect").value = p[2]; }
}
$("#preset").onchange = applyPreset;
["minSec", "maxSec", "aspect"].forEach(id => $("#" + id).addEventListener("change", () => { $("#preset").value = "custom"; }));
applyPreset();

$("#srtbtn").onclick = () => $("#srtfile").click();
$("#srtfile").onchange = async () => {
  const f = $("#srtfile").files[0]; if (!f || !upload) return;
  const msg = $("#srtmsg"); msg.textContent = "上傳字幕檔中…";
  try {
    const r = await fetch("/api/subtitles?for=" + upload.upload_id, {method: "PUT", headers: {"X-Token": T}, body: f});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || r.statusText);
    hasSrt = true; show("#srtrow"); $("#useSrt").checked = true;
    msg.textContent = "已附上 " + f.name + "：" + d.cues + " 句字幕" + (d.mismatch ? "。注意：字幕比音檔長很多，請確認是同一集。" : "。");
  } catch (e) { hasSrt = false; show("#srtrow", false); msg.textContent = "字幕檔無法使用：" + e.message; }
  refreshEstimate();
};

const fmtSec = s => s < 90 ? "約 " + Math.max(1, Math.round(s)) + " 秒" : "約 " + Math.round(s / 60) + " 分鐘";
let estTimer = null;
function refreshEstimate() { clearTimeout(estTimer); estTimer = setTimeout(doEstimate, 250); }
async function doEstimate() {
  const box = $("#estimate"); if (!upload) return;
  const body = currentRequest(); if (!body) return;
  try {
    const d = await post("/api/estimate", {kind: body.kind, upload_id: upload.upload_id, options: body.options});
    if (!d.estimate) { show("#estimate", false); return; }
    const e = d.estimate, parts = [];
    if (e.transcribe_sec) parts.push("語音辨識" + fmtSec(e.transcribe_sec));
    if (e.speaker_sec) parts.push("說話者辨識" + fmtSec(e.speaker_sec));
    if (e.ai_calls) parts.push("AI " + e.ai_calls + " 次呼叫（" + fmtSec(e.ai_sec) + "）");
    box.replaceChildren(el("div", "預估：" + (parts.join("、") || "幾乎立刻完成") + (e.total_sec ? "，合計" + fmtSec(e.total_sec) : "") + "。"));
    box.appendChild(el("small", e.notes.join(" "))); show("#estimate");
  } catch (_) { show("#estimate", false); }
}
["whisper", "device", "backend", "useAI", "useSrt", "maxClips", "useSpk", "spkN"].forEach(id => $("#" + id).addEventListener("change", refreshEstimate));
document.querySelectorAll("input[name=mode]").forEach(r => r.addEventListener("change", refreshEstimate));

const GLYPH = {ok: "✓", warn: "!", fail: "✗", info: "·"};
async function runDoctor(ai) {
  show("#sdoctor"); const box = $("#doctorrows"); box.replaceChildren(el("p", ai ? "檢查中，連 AI 測試可能要等幾十秒…" : "檢查中…", "sub"));
  try {
    const d = await api("/api/doctor?backend=" + encodeURIComponent($("#backend").value || "claude") + (ai ? "&ai=1" : ""));
    box.replaceChildren();
    d.checks.forEach(c => {
      const row = el("div", null, "check " + c.status), body = el("div");
      row.appendChild(el("b", GLYPH[c.status] || "·"));
      const head = el("div"); head.appendChild(el("span", c.name + "：")); head.appendChild(el("span", c.detail, "d")); body.appendChild(head);
      if (c.fix && c.status !== "ok") body.appendChild(el("span", "→ " + c.fix, "f"));
      row.appendChild(body); box.appendChild(row);
    });
  } catch (e) { box.replaceChildren(el("p", "檢查失敗：" + e.message, "note bad")); }
}
$("#doctorbtn").onclick = () => runDoctor(false);
$("#doctorredo").onclick = () => runDoctor(false);
$("#doctorai").onclick = () => runDoctor(true);

function currentRequest() {
  if (!upload) return null;
  const mode = modeOf(), use_srt = hasSrt && $("#useSrt").checked;
  if (mode === "clips") {
    const formats = [...document.querySelectorAll(".fmt:checked")].map(c => c.value);
    return {kind: "clips", upload_id: upload.upload_id, options: {...common(), use_srt, formats, max_clips: +$("#maxClips").value,
      min_sec: +$("#minSec").value, max_sec: +$("#maxSec").value, aspect: $("#aspect").value}};
  }
  return {kind: "plan", upload_id: upload.upload_id, options: {...common(), use_srt, no_ai: !$("#useAI").checked}};
}

function common() {
  const n = Math.round(+$("#spkN").value);
  return {backend: $("#backend").value, whisper_model: $("#whisper").value, language: $("#lang").value, title_language: $("#tlang").value, device: $("#device").value,
    speakers: $("#useSpk").checked && !$("#useSpk").disabled ? Math.min(8, Math.max(2, n || 3)) : 0};
}

$("#go").onclick = async () => {
  const body = currentRequest(); if (!body) return;
  try { await run(body, body.kind === "clips" ? "正在挑選精彩片段並切出檔案…" : "正在分析整集…"); }
  catch (e) { alert(e.message); }
};

async function run(body, title) {
  const r = await post("/api/start", body);
  jobId = r.job; show("#s2", false); show("#s4", false); show("#s5", false); show("#s3");
  $("#runtitle").textContent = title; $("#log").textContent = ""; $("#runmsg").textContent = "";
  $("#runbar").classList.add("busy"); $("#cancel").disabled = false;
  poll(0);
}

async function poll(since) {
  let d;
  try { d = await api("/api/job/" + jobId + "?since=" + since); }
  catch (e) { $("#runmsg").textContent = "連線中斷：" + e.message; return; }
  if (d.lines.length) {
    const log = $("#log"); log.textContent += d.lines.join("\n") + "\n"; log.scrollTop = log.scrollHeight;
    $("#runmsg").textContent = d.lines[d.lines.length - 1];
  }
  if (d.status === "running") { setTimeout(() => poll(d.next), 1000); return; }
  $("#runbar").classList.remove("busy"); show("#s3", d.status !== "done");
  if (d.status === "cancelled") { $("#runtitle").textContent = "已取消"; $("#cancel").disabled = true; show("#s2"); return; }
  if (d.status === "failed") { $("#runtitle").textContent = "失敗"; $("#cancel").disabled = true; $("#runmsg").textContent = "請展開「詳細紀錄」查看原因（例如 AI 工具的登入已過期）。"; show("#s2"); return; }
  if (d.kind === "plan") { planJob = jobId; await loadPlan(); } else finish(d);
  loadSpeakers(jobId);
}

async function loadSpeakers(job) {
  show("#spkbox", false);
  let list = [];
  try { list = (await api("/api/speakers/" + job)).speakers || []; } catch (_) { return; }
  if (!list.length) return;
  const box = $("#spkrows"); box.replaceChildren(); $("#spkmsg").textContent = "";
  list.forEach(s => {
    const row = el("label", null, "row"), name = el("span", s.label + "（約 " + Math.max(1, Math.round(s.seconds / 60)) + " 分鐘）");
    const inp = el("input"); inp.type = "text"; inp.maxLength = 20; inp.placeholder = "例如：小明"; inp.dataset.label = s.label; inp.setAttribute("aria-label", "把「" + s.label + "」改名為");
    row.appendChild(name); row.appendChild(inp);
    if (s.samples.length) row.appendChild(el("small", "例：" + s.samples.join(" ／ "), "sub"));
    box.appendChild(row);
  });
  $("#spksave").onclick = async () => {
    const names = {}; box.querySelectorAll("input").forEach(i => { if (i.value.trim()) names[i.dataset.label] = i.value.trim(); });
    if (!Object.keys(names).length) { $("#spkmsg").textContent = "先在上面填至少一個名字。"; return; }
    try { const r = await post("/api/speakers/" + job, {names}); await loadSpeakers(job); $("#spkmsg").textContent = "已套用（改寫 " + r.changed + " 個字幕檔）。"; }
    catch (e) { $("#spkmsg").textContent = "失敗：" + e.message; }
  };
  show("#spkbox");
}

$("#cancel").onclick = () => post("/api/cancel/" + jobId, {}).catch(() => {});

async function loadPlan() {
  const p = await api("/api/plan/" + planJob);
  planCuts = p.cuts; show("#s3", false); show("#s4");
  $("#planinfo").textContent = "原長 " + (p.duration / 60).toFixed(1) + " 分。勾選的項目會被剪掉；取消勾選就保留。";
  const ol = $("#outline"); ol.replaceChildren();
  (p.outline || []).forEach(o => { const li = el("li"); li.appendChild(el("time", clock(o.start))); li.appendChild(el("span", o.topic)); ol.appendChild(li); });
  show("#outlinebox", (p.outline || []).length > 0);
  $("#s4").classList.toggle("noOutline", !(p.outline || []).length);
  stopListening(); $("#auditor").src = "/source/" + planJob + "?t=" + encodeURIComponent(T);
  const tb = $("#planrows"); tb.replaceChildren();
  const quiet = planCuts.filter(c => c.kind === "silence" && c.end - c.start < 3);
  planCuts.forEach(c => {
    if (quiet.includes(c)) return;
    const tr = el("tr"), td = el("td"), cb = el("input"); cb.type = "checkbox"; cb.checked = c.apply; cb.onchange = () => { c.apply = cb.checked; };
    td.appendChild(cb); tr.appendChild(td);
    tr.appendChild(el("td", clock(c.start) + " (" + (c.end - c.start).toFixed(1) + "s)", "mute"));
    tr.appendChild(el("td", c.kind));
    tr.appendChild(el("td", (c.reason ? c.reason + " ｜ " : "") + c.text));
    const ears = el("td");
    [["聽內容", "cut", "播放這一段被剪掉的內容（最多 25 秒）"], ["聽剪後", "after", "播放剪掉之後的銜接：前 4 秒、跳過這一段、後 4 秒"]].forEach(([label, mode, tip]) => {
      const b = el("button", label, "ghost mini"); b.title = tip; b.onclick = () => listen(c, mode); ears.appendChild(b); ears.appendChild(document.createTextNode(" "));
    });
    tr.appendChild(ears);
    tb.appendChild(tr);
  });
  show("#silrow", quiet.length > 0);
  $("#sillabel").textContent = "同時縮短其餘 " + quiet.length + " 處較短的停頓（3 秒以內，會縮短成約 0.4 秒）";
  $("#silall").checked = quiet.every(c => c.apply);
  $("#silall").onchange = e => quiet.forEach(c => { c.apply = e.target.checked; });
}

let earTimer = null;
function stopListening() {
  clearInterval(earTimer); earTimer = null;
  const aud = $("#auditor"); if (aud) aud.pause();
}
// mode "cut": play what is removed. mode "after": play 4 s before, skip the cut, play 4 s after (what listeners will hear).
function listen(c, mode) {
  stopListening();
  const aud = $("#auditor"), msg = $("#earmsg"), pad = 4;
  const from = mode === "cut" ? c.start : Math.max(0, c.start - pad);
  const stop = mode === "cut" ? Math.min(c.end, c.start + 25) : c.end + pad;
  let jumped = false;
  const go = () => {
    aud.currentTime = from;
    aud.play().then(() => { msg.textContent = mode === "cut" ? "正在播放被剪掉的內容…" : "正在播放剪掉之後的銜接…"; })
      .catch(e => { msg.textContent = "這個音檔格式瀏覽器無法播放：" + e.message; });
    earTimer = setInterval(() => {
      const t = aud.currentTime;
      if (mode === "after" && !jumped && t >= c.start) { jumped = true; aud.currentTime = c.end; return; }
      if (t >= stop || aud.ended) { stopListening(); msg.textContent = "播放完畢。"; }
    }, 60);
  };
  if (aud.readyState >= 1) go(); else { aud.addEventListener("loadedmetadata", go, {once: true}); aud.load(); }
}

$("#render").onclick = async () => {
  try {
    stopListening();
    await post("/api/plan/" + planJob, {apply: planCuts.map(c => !!c.apply)});
    await run({kind: "render", plan_job: planJob, options: {format: $("#outfmt").value, no_loudnorm: !$("#norm").checked}}, "正在輸出剪好的整集…");
  } catch (e) { alert(e.message); }
};

$("#zipbtn").onclick = () => { location.href = "/zip/" + jobId + "?t=" + encodeURIComponent(T); };
$("#videobtn").onclick = async () => {
  try { await run({kind: "videos", plan_job: jobId, options: {}}, "正在產生波形影片（每段約需數秒到十幾秒）…"); }
  catch (e) { alert(e.message); }
};
$("#morebtn").onclick = async () => {
  try { await run({kind: "more", plan_job: jobId, options: {}}, "正在切出下一段備選…"); }
  catch (e) { alert(e.message); }
};

let notesFrom = null;
$("#notesbtn").onclick = async () => {
  const btn = $("#notesbtn"), msg = $("#notesmsg"); btn.disabled = true; msg.textContent = "AI 正在讀逐字稿、整理重點…";
  try {
    const r = await post("/api/start", {kind: "notes", plan_job: notesFrom, options: {title_language: $("#tlang").value, backend: $("#backend").value}});
    let d;
    do { await new Promise(x => setTimeout(x, 1500)); d = await api("/api/job/" + r.job + "?since=0"); } while (d.status === "running");
    if (d.status !== "done") throw new Error(d.lines.slice(-2).join(" ") || d.status);
    const t = await fetch("/files/" + r.job + "/episode_notes.txt?t=" + encodeURIComponent(T)).then(x => x.text());
    $("#notestext").textContent = t; show("#notestext"); show("#notescopy"); msg.textContent = "完成，可直接複製；也已存成 episode_notes.txt。";
  } catch (e) { msg.textContent = "失敗：" + e.message; }
  btn.disabled = false;
};
$("#notescopy").onclick = () => navigator.clipboard.writeText($("#notestext").textContent).then(() => { $("#notescopy").textContent = "已複製"; });

function finish(d) {
  notesFrom = jobId; $("#notestext").hidden = true; $("#notescopy").hidden = true; $("#notesmsg").textContent = ""; $("#notescopy").textContent = "複製文案"; $("#notesbtn").disabled = false;
  show("#s3", false); show("#s5");
  $("#donetitle").textContent = d.kind === "render" ? "剪輯完成" : d.kind === "videos" ? "影片完成" : "片段完成";
  show("#videobtn", ["clips", "more", "videos"].includes(d.kind) && !!d.video); show("#videohint", ["clips", "more", "videos"].includes(d.kind) && !!d.video);
  $("#videobtn").textContent = d.kind === "videos" ? "重新產生波形影片" : "產生波形影片";
  const box = $("#files"); box.replaceChildren();
  const shown = d.files.filter(f => d.kind === "render" ? /^episode_edited/.test(f.path) : true);
  if (!shown.length) $("#donenote").appendChild(el("div", "沒有產生任何檔案（可能沒有找到合適的片段）。", "note warn"));
  shown.forEach(f => {
    const url = "/files/" + jobId + "/" + f.path.split("/").map(encodeURIComponent).join("/") + "?t=" + encodeURIComponent(T);
    const a = el("a", f.path + "（" + (f.size / 1048576).toFixed(1) + " MB）");
    a.href = url; a.download = "";
    const row = el("div", null, "result"); row.appendChild(a);
    if (/\.(mp3|m4a|wav)$/i.test(f.path)) {
      const au = el("audio"); au.controls = true; au.preload = "none"; au.src = url + "&inline=1"; row.appendChild(au);
    }
    box.appendChild(row);
  });
  $("#where").textContent = "檔案也存在：" + where;
  show("#zipbtn", shown.length > 0);
  const alts = d.alternates, more = $("#morebtn");
  show("#morebtn", (d.kind === "clips" || d.kind === "more" || d.kind === "videos") && alts != null);
  more.disabled = !alts; more.textContent = alts ? "再多挑一段（還有 " + alts + " 個備選）" : "沒有更多備選";
}
</script>
</body>
</html>
"""
