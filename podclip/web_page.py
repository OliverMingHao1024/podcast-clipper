"""The single page served by ``podclip web``. Model-written text is only inserted with textContent."""

PAGE = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Podcast 剪輯工具</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2230;--mute:#667085;--line:#e1e5ec;--accent:#3b6fe0;--accent-ink:#fff;--ok:#1a7f4b;--bad:#c0392b;--warn:#b26a00}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--card:#1b2030;--ink:#e8ebf3;--mute:#98a2b8;--line:#2c3348;--accent:#6aa9ff;--accent-ink:#0b1020;--ok:#4cc38a;--bad:#ff7b6b;--warn:#f0b35a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,"Noto Sans TC","Microsoft JhengHei",sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:0 0 12px}
.sub{color:var(--mute);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin:0 0 16px}
.card[hidden]{display:none}
.drop{border:2px dashed var(--line);border-radius:10px;padding:28px;text-align:center;color:var(--mute);cursor:pointer}
.drop.over{border-color:var(--accent);color:var(--ink)}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:560px){.modes{grid-template-columns:1fr}}
.mode{border:2px solid var(--line);border-radius:10px;padding:12px 14px;cursor:pointer;display:block}
.mode input{margin-right:6px}.mode b{display:block}.mode span{color:var(--mute);font-size:14px}
.mode:has(input:checked){border-color:var(--accent)}
label.row{display:flex;gap:10px;align-items:center;margin:8px 0;flex-wrap:wrap}
label.row>span{min-width:9em;color:var(--mute);font-size:14px}
select,input[type=number]{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
button{font:inherit;border:0;border-radius:8px;padding:10px 18px;cursor:pointer;background:var(--accent);color:var(--accent-ink);font-weight:600}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line);font-weight:400}
button:disabled{opacity:.5;cursor:not-allowed}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:10px}
.bar>i{display:block;height:100%;width:0;background:var(--accent);transition:width .2s}
.bar.busy>i{width:40%;animation:slide 1.2s infinite ease-in-out}
@keyframes slide{0%{margin-left:-40%}100%{margin-left:100%}}
@media (prefers-reduced-motion:reduce){.bar.busy>i{animation:none;width:100%;opacity:.5}}
.note{padding:10px 12px;border-radius:8px;border:1px solid var(--line);margin:0 0 12px;font-size:14px}
.note.warn{border-color:var(--warn);color:var(--warn)}.note.bad{border-color:var(--bad);color:var(--bad)}.note.ok{border-color:var(--ok);color:var(--ok)}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;max-height:240px;overflow:auto;font-size:13px;white-space:pre-wrap;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td.mute{color:var(--mute)}
.files a{display:block;padding:6px 0;color:var(--accent);word-break:break-all}
.actions{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.outline{list-style:none;margin:0 0 16px;padding:10px 12px;background:var(--bg);border:1px solid var(--line);border-radius:8px;max-height:260px;overflow:auto;font-size:14px}
.outline li{display:flex;gap:12px;padding:2px 0}.outline time{font-variant-numeric:tabular-nums;color:var(--accent);min-width:4.5em}
details{margin-top:10px}summary{cursor:pointer;color:var(--mute);font-size:14px}
</style>
</head>
<body>
<main>
<h1>Podcast 剪輯工具</h1>
<p class="sub">全程在你自己的電腦上執行，音檔不會上傳到任何地方（AI 建議只透過你本機已登入的 Claude 取得）。</p>
<div id="envnote"></div>

<section class="card" id="s1">
  <h2>① 選音檔</h2>
  <div class="drop" id="drop">把音檔拖到這裡，或點一下選擇<br><small>mp3 / m4a / wav / flac / ogg / mp4 等</small></div>
  <input type="file" id="file" hidden accept="audio/*,video/mp4,video/webm,video/x-matroska,.mp3,.m4a,.wav,.flac,.ogg,.aac,.opus,.mp4,.mkv,.webm">
  <div class="bar" id="upbar" hidden><i></i></div>
  <p id="upmsg" class="sub" style="margin:8px 0 0"></p>
</section>

<section class="card" id="s2" hidden>
  <h2>② 你想做什麼？</h2>
  <div class="modes">
    <label class="mode"><input type="radio" name="mode" value="clips" checked><b>挑出精彩短片段</b><span>AI 找出約 1～3 分鐘、適合分享的段落，各自輸出音檔、字幕與影片。</span></label>
    <label class="mode"><input type="radio" name="mode" value="plan"><b>整集剪輯</b><span>去掉長沉默、嗯呃、講錯重來。先給你勾選確認，再輸出剪好的整集。</span></label>
  </div>
  <div id="optClips">
    <label class="row"><span>要輸出</span>
      <label><input type="checkbox" class="fmt" value="audio" checked> 音檔</label>
      <label><input type="checkbox" class="fmt" value="srt" checked> 字幕</label>
      <label><input type="checkbox" class="fmt" value="video"> 波形影片</label></label>
    <label class="row"><span>最多幾段</span><input type="number" id="maxClips" value="10" min="1" max="30"></label>
  </div>
  <div id="optPlan" hidden>
    <label class="row"><span>AI 協助</span><label><input type="checkbox" id="useAI" checked> 讓 AI 找出講錯重來與雜音事故（需要本機已登入 Claude）</label></label>
  </div>
  <details><summary>進階設定</summary>
    <label class="row"><span>語音辨識品質</span><select id="whisper"><option value="tiny">最快（較不準）</option><option value="base">快</option><option value="small" selected>標準</option><option value="medium">最準（很慢）</option></select></label>
    <label class="row"><span>說話語言</span><select id="lang"><option value="">自動偵測</option><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option><option value="ko">한국어</option></select></label>
    <label class="row"><span>說明文字語言</span><select id="tlang"><option>繁體中文</option><option>简体中文</option><option>English</option><option>日本語</option></select></label>
    <label class="row" id="gpurow"><span>使用顯示卡加速</span><select id="device"><option value="cpu" selected>否（較穩）</option><option value="cuda">是（NVIDIA，需另外安裝）</option></select></label>
  </details>
  <div class="actions"><button id="go">開始</button></div>
</section>

<section class="card" id="s3" hidden>
  <h2 id="runtitle">處理中…</h2>
  <div class="bar busy" id="runbar"><i></i></div>
  <p id="runmsg" class="sub" style="margin:8px 0 0"></p>
  <details><summary>詳細紀錄</summary><pre id="log"></pre></details>
  <div class="actions"><button class="ghost" id="cancel">取消</button></div>
</section>

<section class="card" id="s4" hidden>
  <h2>③ 確認要剪掉的地方</h2>
  <p class="sub" id="planinfo"></p>
  <div id="outlinebox" hidden>
    <h2 style="font-size:15px">段落大綱（原音檔時間）</h2>
    <ul id="outline" class="outline"></ul>
  </div>
  <table><thead><tr><th>剪掉</th><th>時間</th><th>類型</th><th>說明／逐字稿</th></tr></thead><tbody id="planrows"></tbody></table>
  <label class="row" id="silrow"><input type="checkbox" id="silall" checked> <span style="min-width:0;color:var(--ink)" id="sillabel"></span></label>
  <div class="actions">
    <select id="outfmt"><option value=".mp3">mp3</option><option value=".m4a">m4a</option><option value=".wav">wav</option></select>
    <label><input type="checkbox" id="norm" checked> 統一音量</label>
    <button id="render">套用並輸出整集</button>
  </div>
</section>

<section class="card" id="s5" hidden>
  <h2 id="donetitle">完成</h2>
  <div id="donenote"></div>
  <div class="files" id="files"></div>
  <div id="notesbox">
    <div class="actions"><button class="ghost" id="notesbtn">產生本集介紹文案</button></div>
    <p class="sub" id="notesmsg" style="margin:8px 0 0"></p>
    <pre id="notestext" hidden></pre>
    <div class="actions"><button class="ghost" id="notescopy" hidden>複製文案</button></div>
  </div>
  <p class="sub" id="where"></p>
  <div class="actions"><button class="ghost" onclick="location.reload()">處理另一個檔案</button></div>
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
let upload = null, jobId = null, planJob = null, planCuts = [], where = "";

api("/api/env").then(env => {
  where = env.workdir;
  if (env.platform === "darwin") { $("#gpurow").hidden = true; $("#device").value = "cpu"; }
  const box = $("#envnote");
  const add = (cls, text) => { const n = el("div", text, "note " + cls); box.appendChild(n); };
  if (!env.ffmpeg) add("bad", "找不到 ffmpeg，無法切音檔。請先安裝 ffmpeg（見 README）。");
  if (!env.whisper) add("bad", "尚未安裝語音辨識（faster-whisper）。請用 start.bat 啟動，或依 README 安裝。");
  if (!env.claude) add("warn", "找不到 claude 指令：AI 選段與 AI 剪輯建議將無法使用。整集剪輯可取消勾選「AI 協助」。");
});

const drop = $("#drop"), input = $("#file");
drop.onclick = () => input.click();
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
    upload = data; $("#upmsg").textContent = "已選擇：" + data.name; show("#s2");
  };
  x.onerror = () => { $("#upmsg").textContent = "上傳失敗"; };
  x.send(file);
}

const modeOf = () => document.querySelector("input[name=mode]:checked").value;
document.querySelectorAll("input[name=mode]").forEach(r => r.onchange = () => {
  show("#optClips", modeOf() === "clips"); show("#optPlan", modeOf() === "plan");
});

function common() {
  return {whisper_model: $("#whisper").value, language: $("#lang").value, title_language: $("#tlang").value, device: $("#device").value};
}

$("#go").onclick = async () => {
  const mode = modeOf(); let body;
  if (mode === "clips") {
    const formats = [...document.querySelectorAll(".fmt:checked")].map(c => c.value);
    body = {kind: "clips", upload_id: upload.upload_id, options: {...common(), formats, max_clips: +$("#maxClips").value}};
  } else {
    body = {kind: "plan", upload_id: upload.upload_id, options: {...common(), no_ai: !$("#useAI").checked}};
  }
  try { await run(body, mode === "clips" ? "正在挑選精彩片段並切出檔案…" : "正在分析整集…"); }
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
  if (d.status === "failed") { $("#runtitle").textContent = "失敗"; $("#cancel").disabled = true; $("#runmsg").textContent = "請展開「詳細紀錄」查看原因（例如 Claude 登入過期）。"; show("#s2"); return; }
  if (d.kind === "plan") { planJob = jobId; await loadPlan(); } else finish(d);
}

$("#cancel").onclick = () => post("/api/cancel/" + jobId, {}).catch(() => {});

async function loadPlan() {
  const p = await api("/api/plan/" + planJob);
  planCuts = p.cuts; show("#s3", false); show("#s4");
  $("#planinfo").textContent = "原長 " + (p.duration / 60).toFixed(1) + " 分。勾選的項目會被剪掉；取消勾選就保留。";
  const ol = $("#outline"); ol.replaceChildren();
  (p.outline || []).forEach(o => { const li = el("li"); li.appendChild(el("time", clock(o.start))); li.appendChild(el("span", o.topic)); ol.appendChild(li); });
  show("#outlinebox", (p.outline || []).length > 0);
  const tb = $("#planrows"); tb.replaceChildren();
  const quiet = planCuts.filter(c => c.kind === "silence" && c.end - c.start < 3);
  planCuts.forEach(c => {
    if (quiet.includes(c)) return;
    const tr = el("tr"), td = el("td"), cb = el("input"); cb.type = "checkbox"; cb.checked = c.apply; cb.onchange = () => { c.apply = cb.checked; };
    td.appendChild(cb); tr.appendChild(td);
    tr.appendChild(el("td", clock(c.start) + " (" + (c.end - c.start).toFixed(1) + "s)", "mute"));
    tr.appendChild(el("td", c.kind));
    tr.appendChild(el("td", (c.reason ? c.reason + " ｜ " : "") + c.text));
    tb.appendChild(tr);
  });
  show("#silrow", quiet.length > 0);
  $("#sillabel").textContent = "同時縮短其餘 " + quiet.length + " 處較短的停頓（3 秒以內，會縮短成約 0.4 秒）";
  $("#silall").checked = quiet.every(c => c.apply);
  $("#silall").onchange = e => quiet.forEach(c => { c.apply = e.target.checked; });
}

$("#render").onclick = async () => {
  try {
    await post("/api/plan/" + planJob, {apply: planCuts.map(c => !!c.apply)});
    await run({kind: "render", plan_job: planJob, options: {format: $("#outfmt").value, no_loudnorm: !$("#norm").checked}}, "正在輸出剪好的整集…");
  } catch (e) { alert(e.message); }
};

let notesFrom = null;
$("#notesbtn").onclick = async () => {
  const btn = $("#notesbtn"), msg = $("#notesmsg"); btn.disabled = true; msg.textContent = "AI 正在讀逐字稿、整理重點…";
  try {
    const r = await post("/api/start", {kind: "notes", plan_job: notesFrom, options: {title_language: $("#tlang").value}});
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
  notesFrom = jobId; $("#notestext").hidden = true; $("#notescopy").hidden = true; $("#notesmsg").textContent = "";
  show("#s3", false); show("#s5");
  $("#donetitle").textContent = d.kind === "render" ? "剪輯完成" : "片段完成";
  const box = $("#files"); box.replaceChildren();
  const shown = d.files.filter(f => d.kind === "render" ? /^episode_edited/.test(f.path) : true);
  if (!shown.length) $("#donenote").appendChild(el("div", "沒有產生任何檔案（可能沒有找到合適的片段）。", "note warn"));
  shown.forEach(f => {
    const a = el("a", f.path + "（" + (f.size / 1048576).toFixed(1) + " MB）");
    a.href = "/files/" + jobId + "/" + f.path.split("/").map(encodeURIComponent).join("/") + "?t=" + encodeURIComponent(T);
    a.download = ""; box.appendChild(a);
  });
  $("#where").textContent = "檔案也存在：" + where;
}
</script>
</body>
</html>
"""
