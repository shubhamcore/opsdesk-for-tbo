# Video Production Guide

Two artefacts are produced by this repository, both from real code execution:

| File | What it is | Duration | Size |
| --- | --- | --- | --- |
| `Product_Demo.mp4` | Six Playwright screen-capture segments of the running app, normalised and concatenated with FFmpeg | 207 s | ≈4.6 MB |
| `Explainer.mp4` | Seven rendered scene cards (text + real product screenshots), 15 s each | 105 s | ≈0.9 MB |
| `Product_Demo.srt`, `Explainer.srt` | Subtitle tracks matched to the cuts above | — | — |

Both are H.264, 1440×900, 25 fps, `yuv420p`, no audio.

---

## 1. Regenerate

```bash
# prerequisites: server on :8000, seeded database, playwright chromium, ffmpeg
python -m scripts.run_Automated_Demo                 # both videos + both SRTs
python -m scripts.run_Automated_Demo --only demo     # capture + cut the product demo
python -m scripts.run_Automated_Demo --only explainer # render cards + assemble the explainer
```

Outputs land in `videos/`. Intermediate files: `videos/raw/` (per-segment webm/mp4) and
`videos/cards/` (scene PNG/HTML). A machine-readable summary is written to `videos/render_report.json`.

Recording happens after a reseed, so rehearsals and finals show identical numbers.

## 2. Add narration

The scripts in `Explainer_Voiceover.md` and `Demo_Video_Script.md` are written for a human VO.
Record a mono WAV, then mux without touching the video timing:

```bash
ffmpeg -i Explainer.mp4 -i voiceover.wav \
  -c:v copy -c:a aac -b:a 160k -shortest \
  Explainer_with_voice.mp4
```

If the narration is longer than 105 s, either trim sentences or slow the video by 4–6 % with
`setpts=1.05*PTS` (and re-time `Explainer.srt`).

## 3. Burn in subtitles (optional)

```bash
ffmpeg -i Product_Demo.mp4 -vf "subtitles=Product_Demo.srt:force_style='FontName=Inter,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00102338,BorderStyle=1,Outline=1'" \
  -c:a copy Product_Demo_subs.mp4
```

Soft subtitles are also valid for most review tools:

```bash
ffmpeg -i Product_Demo.mp4 -i Product_Demo.srt -c copy -c:s mov_text Product_Demo_softsubs.mp4
```

## 4. Export settings that match what is shipped

```
Container : MP4
Video     : H.264, 1440×900, 25 fps, CRF 23–25, preset veryfast
Pixel fmt : yuv420p (required by most players)
Audio     : AAC 160 kb/s mono/stereo (only if narration is added)
Subtitles : mov_text (soft) or burned-in
```

## 5. Pre-publish checklist

- [ ] `ffprobe` shows the expected duration and 1440×900 H.264
- [ ] A frame at 10 %, 50 % and 90 % shows real product UI (not a spinner or an error toast)
- [ ] SRT cue times land on the intended scene/segment
- [ ] No credentials, tokens or `.env` values appear on screen
- [ ] The demo dataset is labelled synthetic in the video (the corner label and the app footer both say so)
- [ ] No figure in the narration contradicts `benchmark_results/benchmark_report.json`

## 6. Known limitations

- The captures are headless Chromium at 1440×900; a retina capture would need `device_scale_factor=2`
  and would roughly quadruple the file size.
- There is **no audio track** in the shipped files — narration is intentionally left to a human recording
  so the video never claims a voice artist or a synthesised voice it does not have.
- Scenes are hard cuts; transitions would require re-timing the SRT.
