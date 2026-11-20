# podcast-clipper

Cut an audio podcast into short clips. Per clip: audio (`clip.mp3`), subtitles (`clip.srt`),
a 9:16 waveform video with burned subtitles (`clip.mp4`), and a title/reason (`post.txt`);
`clips.json` lists every clip with timestamps.

```powershell
pip install -e .[dev]          # .[asr] adds local Whisper (CPU); .[gpu] adds the CUDA 12 libs for NVIDIA GPUs
podclip run episode.mp3 --srt episode.srt --out out        # uses the logged-in `claude` CLI
podclip run episode.mp3 --device cuda                      # no --srt: transcribe on the GPU first
podclip run episode.mp3 --dry-run                          # only clips.json, cut nothing
podclip run episode.mp3 --formats audio,srt                # skip the video
podclip run episode.mp3 --wave-color 0xFF8844              # waveform colour
podclip run episode.mp3 --backend cmd --cmd "mytool --stdin"
```

## For non-programmers: browser UI (local only)

Clone the repo, then double-click `start.bat` (Windows). The first run creates `.venv` and installs
the components from PyPI; after that it opens a page in your browser: pick an audio file, choose
"clips" or "whole-episode edit", review the cuts with checkboxes, download the results. Needs Python 3.10+,
`ffmpeg` on PATH, and (for AI suggestions) the `claude` CLI logged in. Same thing from a terminal:
`podclip web [--workdir podclip-work] [--port N] [--no-browser]`. Uploads and results live in `podclip-work/`.

## Edit a whole episode (not clips)

```powershell
podclip edit-plan episode.mp3 --srt episode.srt --out edit      # writes edit/plan.md (read) and edit/plan.json (edit)
# in plan.json set "apply": false on any cut you want to keep, then:
podclip edit-render edit/plan.json --out episode_edited.mp3 --srt episode.srt
```

Cuts: long pauses shortened to 0.4 s (ffmpeg silencedetect), cues that are only a filler (嗯, 呃, 欸),
and stretches the model flags as retake / incident / tangent / intro. Joins get 20 ms fades, output is
loudness-normalised (`--no-loudnorm` to skip) and the `.srt` is remapped to the new timeline.
`--no-ai` skips the model call. Always read `plan.md`: the AI can over-cut (it once marked the hosts'
self-introductions as "intro chatter").

## Episode blurb (本集重點)

```powershell
podclip notes episode_edited.srt --out episode_notes.txt   # summary + a short "【本集重點】" topic list
```

Reads the subtitle file (use the remapped `episode_edited.srt` after `edit-render`), asks the model for
short topic titles in time order, validates them, and prints text ready to paste. In the browser UI it is
the "產生本集介紹文案" button on the finished page. Always proofread: it only knows what the transcript says.

## Design choices (security)

- **No server by default** (only the optional `podclip web`, below), no telemetry, no publishing, no browser cookies, no runtime installs. `podclip web` listens on 127.0.0.1 only, checks Host/Origin and a per-run token, accepts only whitelisted options (never a path, `--cmd` or a shell string), serves downloads only from one job's `out/` folder, and renders model text with `textContent`. `start.bat` is the only place that installs anything, once, when you run it.
- **Subscription, not API key**: the `claude` backend runs the official CLI in print mode with all
  tools disabled (`--tools ""`), no MCP, no slash commands, no session saved. This program never
  reads or stores credentials. Check your plan's terms and usage limits before batch use.
- The transcript is untrusted. It is wrapped in `<transcript>` tags, the system prompt says to ignore
  instructions inside, and every model reply is validated (integer rows in range, duration bounds,
  bounded text) before use. Folder names come from sanitised titles; ffmpeg is called with an
  argument list, never a shell string.

## Verified so far

One real episode (65 min, Traditional Chinese, no subtitles) on Windows 11 + RTX 3060: GPU Whisper
`small` took 160 s (CPU path not timed to completion); the logged-in `claude` CLI picked 10 clips;
audio, SRT, 9:16 waveform video with CJK subtitles and post text were produced and the frames
inspected. Clip boundaries and title quality were only spot-checked, not rated. English titles can
leak into Chinese output (one `father` seen). Not tested: macOS/Linux, long episodes with several
windows beyond two, `--backend cmd` with a real vendor CLI, subscription rate limits.
