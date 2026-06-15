---
name: editing-video-with-claude-code
description: Use when editing a talking-head / demo / launch video from raw camera takes — multiple takes per scene to pick from, cuts that must land in silence, color grading from log footage, or animated graphics timed to spoken words. The edit is text (transcripts + JSON + code), executed by ffmpeg/Remotion, not a timeline NLE.
---

# Editing Video with Claude Code

Edit a video the way Fable's launch video was edited (Thariq, June 2026): **no
timeline, no NLE project file — the edit is text the agent can read, diff, and
re-render.** Footage by a camera, taste by the human, everything in between by the
agent.

**Core principle:** Every decision lives in a file. Word timestamps come from a
transcript (grepped, never scrubbed). Cut picks + rationale live in an EDL JSON.
The grade is a `.cube` LUT. Graphics are React components. ffmpeg/Remotion execute
those files. Because it's all text, the agent can verify its own output and redo it.

## The pipeline (9 steps)

```
raw takes ──▶ 1 transcribe (Whisper, word timestamps)
          ──▶ 2 select best take per scene (subagents + verifier)
          ──▶ 3 EDL: final-edit.json (picks + in/out + rationale)
          ──▶ 4 ffmpeg cuts each pick, concats → first watchable cut
          ──▶ 5 color grade: hand-written .cube LUTs (S-Log3 → Rec.709)
          ──▶ 6 graphics: PNGs rebuilt as Remotion React components
          ──▶ 7 cue sheet times each overlay to a spoken word from the transcript
          ──▶ 8 (optional) Figma MCP round-trip for design review
          ──▶ 9 final render: npx remotion render, verify frames, encode
```

One prompt can kick off steps 1–4 (`/goal don't stop until you have a final video`).
Do the rest as follow-up prompts. **Drive it scene-by-scene; verify each stage's
output before moving on.**

## Quick reference

| Stage      | Tool                  | Artifact                     | How the agent works                           |
| ---------- | --------------------- | ---------------------------- | --------------------------------------------- |
| Transcribe | Whisper (local)       | `transcripts/<clip>.json`    | word-level `{word,start,end}`                 |
| Select     | subagents + verifier  | `selection_rationale` in EDL | one subagent per scene, double-checked        |
| EDL        | (write JSON)          | `final-edit.json`            | candidate takes, in/out, written rationale    |
| Cut        | ffmpeg                | `cuts/seg*.mp4`, `final.mp4` | `-ss/-to` per pick, then concat               |
| Grade      | ffmpeg + `.cube`      | `luts/*.cube`                | hand-written LUT, applied at encode           |
| Graphics   | Remotion (React)      | `src/cards`, `src/overlays`  | each PNG → JSX component, props               |
| Timing     | (one config)          | `anim.tsx`, `FinalEdit.tsx`  | 6 knobs + cue sheet, grep timestamps          |
| Review     | Figma MCP             | Figma file                   | export components, designers tweak, re-import |
| Render     | `npx remotion render` | final 4K mp4                 | screenshot stills, verify, then encode        |

## Step 1 — Transcribe every take (word timestamps)

Run **Whisper locally** on each take to get word-level timestamps. These timestamps
are the backbone: every cut point and every overlay cue is **grepped out of the
transcript, never found by scrubbing a timeline.**

```bash
# openai-whisper (pip install -U openai-whisper) — word timestamps as JSON
whisper A004C003.MP4 --model large-v3 --word_timestamps True \
  --output_format json --output_dir work/transcripts/
```

```jsonc
// work/transcripts/A004C003.json — what you're after
"words": [
  { "word": " Hey",   "start": 1.02, "end": 1.50 },
  { "word": " it's",  "start": 1.90, "end": 2.04 },
  { "word": " Thariq","start": 2.04, "end": 2.24 }
]
```

Gotcha: Whisper mis-hears names ("Thariq" → "Sark"). **The text can be wrong; the
timestamps still land.** You cut on timestamps, so this is fine.

## Step 2 — Select the best take per scene

Dispatch **one subagent per scene** to read that scene's transcripts and pick the
best take, with a **verifier** double-checking. Heuristics:

- Best take is usually the **last** one (fewest ums) — but not always; read them.
- Disqualify incomplete takes (long dead pauses mid-sentence).
- **Every cut must land in silence.** Find the silent gap between words and put the
  cut point inside it (e.g. warm-up "Hey [name]" ends at 66.40, cut in at 66.45).
- Cut the warm-up "Hey [name]" openers the speaker uses to start warm.

The subagent writes a `selection_rationale` string into the EDL for every pick —
the _reasoning_ is part of the artifact, so the human can audit it.

## Step 3 — The edit is a JSON file (EDL)

`final-edit.json` is the edit decision list — candidate takes, the chosen clip,
frame-accurate in/out, and the written rationale. ffmpeg executes it.

```jsonc
// final-edit.json
{
  "scene": 1,
  "title": "Part 1: Intro",
  "candidate_takes": ["C001", "C002", "C003", "C004", "C017 (re-shoot)"],
  "selection_rationale": "C017 incomplete — 5.8s dead pause mid-sentence, disqualified. C003 cleanest complete take: zero ums, clean ending.",
  "clips": [
    {
      "clip": "A004C003",
      "start": 1.89,
      "end": 60.81,
      "first_words": "Hey everyone, it's Thariq...",
    },
  ],
}
```

After ffmpeg builds the cut, **re-transcribe the cut itself** and confirm the script
(e.g. "zero ums") — the agent verifies its own edit.

## Step 4 — ffmpeg cuts and stitches

```bash
# one frame-accurate cut per pick (re-encode for accuracy at arbitrary timestamps)
ffmpeg -ss 1.89 -to 60.81 -i A004C003.MP4 cuts/seg1.mp4
# ...repeat per pick, then join the picks (concat demuxer, stream copy)
ffmpeg -f concat -safe 0 -i concat.txt -c copy final.mp4
```

`concat.txt` is one `file 'cuts/segN.mp4'` line per segment. This yields a watchable
cut within minutes — flat/ungraded, grade comes next.

## Step 5 — Color grade from scratch (hand-written LUTs)

Footage is **S-Log3** (flat, log). Write `.cube` LUTs by hand — **no preset packs**
— to go S-Log3 → Rec.709. When the human says "too muted," generate several graded
options and let them choose ("make examples of how we might regrade").

```bash
ffmpeg -i final.mp4 -vf "lut3d=luts/neutral_cool_desat.cube" graded.mp4
```

The grade is **plain text** (the `.cube` file), applied by ffmpeg at encode time —
so it's diffable and promptable like everything else.

**Authoring the `.cube` by hand.** A `.cube` is a plain-text 3D LUT: a header
(`LUT_3D_SIZE N`, `DOMAIN_MIN/MAX`) then `N³` lines of `R G B` floats in 0–1, the
output color for each input grid point (blue varies slowest). Don't write N³ lines by
hand — **generate it with a tiny script** that, per grid point, applies the transform
in order: (1) **S-Log3 → linear** (Sony's S-Log3 EOTF, inverse), (2) the creative move
(white balance / saturation / contrast / channel curves — this is the "look"), (3)
**linear → Rec.709** (the gamma 2.4 / Rec.709 OETF). Then write the grid out. Start at
`LUT_3D_SIZE 33`. Sanity-check by applying it to one still and eyeballing skin tone +
neutrals before re-encoding the whole cut.

```python
# make_lut.py — emit a 33³ .cube; fill transform() with the 3 stages above
N = 33
print(f"LUT_3D_SIZE {N}")
for b in range(N):
    for g in range(N):
        for r in range(N):
            ro, go, bo = transform(r/(N-1), g/(N-1), b/(N-1))  # slog3→linear→look→rec709
            print(f"{ro:.6f} {go:.6f} {bo:.6f}")
```

## Step 6 — Graphics: PNGs rebuilt as Remotion components

Designers hand over static PNGs (cards, lower-thirds, overlays). **Rebuild each PNG
as a React component in Remotion** so every word, color, and beat becomes a prop you
can prompt ("make it snappier" = a one-line change).

```tsx
// KeypointLedger.tsx — beat 2: right column lights up, left grays + strikes
const beat2 = interpolate(frame, [beat2At, beat2At + 12], [0, 1], { easing: EASE_OUT });
<div style={{ ...text, color: cream, opacity: 1 - beat2 }}>“Is Claude doing the work right?”</div>;
```

## Step 7 — One timing file + a transcript-timed cue sheet

Put the global feel in one config so "make it snappier" is a single edit:

```tsx
// anim.tsx — global timing knobs (frames @ 24fps); tweak these first
export const TIMING = { reveal: 13, stagger: 4, overlayIn: 10, overlayOut: 8, emphasisDelay: 3 };
export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
```

Then a cue sheet lands each overlay **on the spoken word**, timed from the transcript
— the agent greps the word's timestamp, never scrubs:

```tsx
// FinalEdit.tsx — overlays land on the word
CUES = [
  { id: "lower-third", at: 1.2, dur: 4.5 }, // "…it's Thariq from the Claude Code team"
  { id: "keypoint", at: 12.2, dur: 25.6 }, // "Is Claude doing the right work?"
];
// e.g. <KeypointLedger beat2At={295} /> — frame 295 is the word "right" (295/24fps)
```

## Step 8 — Figma round-trip (optional, for a design team)

Export the Remotion components to a **Figma file via the Figma MCP** so designers can
tweak (components, color-grading station, motion page). They edit in Figma, then
"copy feedback as prompt" → paste back into Claude Code → "the design has been updated
in this Figma, update the video to match." Code → Figma → code, rebuilt in code each way.

## Step 9 — Final render + self-verification

```bash
npx remotion render   # headless 4K, e.g. 3840×2160 @ exactly 24 fps
```

Before/after each render pass, **Claude screenshots stills and reviews its own work**:
pull frames at the cue/cut timestamps and Read them (a VLM can see a clipped word, a
mis-timed overlay, a bad grade). Pass: frame count matches duration × fps, every cue
overlay is present and lands on its word, no cut clips audio/visual mid-word.

```bash
# extract stills at the moments that matter (the cue timestamps), then Read them
ffmpeg -i graded.mp4 -vf "select='eq(n,295)'" -vframes 1 stills/f295.png   # the word "right"
ffmpeg -i graded.mp4 -vf fps=1 stills/every_%04d.png                       # or one per second
```

The whole job is a repo:

```
transcripts/*.json   word timestamps — cut points + cues grepped from here
final-edit.json      the EDL: takes, in/out, rationale; ffmpeg executes it
luts/*.cube          hand-written grade, S-Log3 → Rec.709
src/cards · overlays  graphics as Remotion components
anim.tsx · FinalEdit.tsx  6 timing knobs + transcript-timed cue sheet
```

## Common mistakes

- **Scrubbing for a cut/cue point.** Don't. Grep the word in the transcript and use
  its timestamp. The transcript is the source of timing truth.
- **Cutting on a word boundary.** Cuts must land **in the silent gap** between words,
  or you clip audio. Find the gap (prev word `end` → next word `start`).
- **Trusting Whisper's spelling.** Names/jargon will be wrong; timestamps are right.
  Cut on timestamps, not on matching exact text.
- **`-c copy` for arbitrary in/out.** Stream-copy only cuts on keyframes → off by up
  to a GOP. Re-encode per-segment cuts (`-ss/-to` without `-c copy`); use `-c copy`
  only for the final concat of already-cut segments.
- **Preset LUT packs.** Write the `.cube` by hand for this footage; keep the grade as
  diffable text.
- **Scattering timing constants.** One `anim.tsx` with a few knobs; "snappier" = one line.
- **Skipping self-verification.** Re-transcribe the cut; screenshot render stills. The
  agent checking its own output is the point.

## Real-world impact

Fable's 3:00 4K launch video: 17 takes / 25 GB raw → verified 2:50 cut in minutes,
7 LUTs + 11 graphics-as-components, ~10 re-renders in one night, 2 code↔Figma round
trips, 4 days (Jun 6–9), **0 video editors opened.**
