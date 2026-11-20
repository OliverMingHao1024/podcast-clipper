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
podclip run episode.mp3 --backend cmd --cmd "mytool --stdin"
```

## Design choices (security)

- **No server, no open port, no telemetry, no publishing, no browser cookies, no runtime installs.**
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
