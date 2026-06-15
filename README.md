---
title: Quillwright
emoji: ⚡
colorFrom: purple
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
thumbnail: https://huggingface.co/spaces/build-small-hackathon/Quillwright/resolve/main/quillwright/web/img/quillwright-logo-trimmed.png
short_description: Tell it about the job. It drafts the estimate.
tags:
  - backyard-ai
  - agent
  - small-models
  - off-the-grid
  - track:backyard
  - sponsor:openbmb
  - sponsor:nvidia
  - sponsor:modal
  - achievement:welltuned
  - achievement:offbrand
  - achievement:llama
---

# Quillwright

A human-supervised, small-model agent for tradespeople: snap a job photo + voice note → a team of **local** small models forges a finished, itemized **estimate**. No cloud, runs on your machine. Build Small Hackathon entry (Backyard AI track).

**▶ [Demo video](https://youtu.be/KqTJc9vYlb0)** · **[Launch post on X](https://x.com/APrak2022/status/2066633276379255060)**

> **⏳ Cold start (please wait ~30–60s on first load).** This Space scales to zero when idle,
> so the **first** visit after a quiet period has to boot the container before the app
> responds — you may see Hugging Face's "Building / Starting" screen, then a moment where
> the page is warming up. **The app is not broken — it's waking up.** The container (CPU)
> hosts the UI; the models themselves run on Modal GPUs that also scale to zero, so the
> **first forge** pays a separate model cold-start (up to a minute or two for the 30B
> brain). Reload once if the first paint hangs; the UI shows a "waking up → ready" banner
> when it reconnects and a "Waking the models" card on the first forge.

> **This hosted Space is wired live to Modal** (CPU container → Modal GPUs): the real small models run on hosted NVIDIA GPUs — brain on Nemotron-3-Nano-30B, vision/audio on Nemotron-Omni-30B, multilingual on Aya-Expanse-8B, Document Capture on the fine-tuned Parse extractor. The full local stack (MiniCPM-V, Nemotron, Aya via Ollama) is the Airplane-Mode story — see the demo video / Airplane-Mode Proof. The apps scale to zero when idle; to fall back to instant CPU stub mode, unset the `FF_BACKEND` Space secret.

See `docs/superpowers/specs/` and `docs/adr/` for the design.

## Built on NVIDIA Nemotron

Quillwright's orchestra is **NVIDIA-first** — three of the model roles run NVIDIA
Nemotron, and the whole agent is designed around the same family scaling from a laptop to
a GPU:

- **Brain** (the tool-calling agent loop) — **Nemotron-3-Nano**, local _and_ hosted. This is
  the heart of the app: it decides which line items to add, the quantities, and when the
  estimate is done.
- **Perception** (reads the job photo) and **Audio** (the voice note) — on the hosted Best
  Stack, both run **Nemotron-Omni**, one multimodal deployment serving vision and speech.
  (Locally, perception runs MiniCPM-V from OpenBMB — see _Backend resolution_.)

The point of the build is the **same family at two tiers**:

- **Private Stack (local / Airplane-Mode)** — **Nemotron-3-Nano 4B** via Ollama, on your
  machine, no cloud. Tuned to **~0.97 item-F1** on the eval set (`scripts/run_brain_eval.py`).
- **Best Stack (hosted)** — **Nemotron-3-Nano 30B** + **Nemotron-Omni 30B** on Modal GPUs,
  the same agent loop with more headroom. The hosted Space runs the Best Stack live (see
  _Backend resolution_ below). Aya-Expanse (multilingual) and the fine-tuned Parse extractor
  (Document Capture) round out the orchestra.

One agent, one tool contract — flip `FF_BACKEND` and the **Nemotron brain** moves from a 4B
on your laptop to a 30B on a GPU without touching the agent code. Facts-from-Tools holds at
both tiers: the model never invents a price.

## What's real

- **Vision** — MiniCPM-V (OpenBMB) reads job photos → observations, locally via Ollama.
- **Brain** — Nemotron-3-Nano (NVIDIA) drives the tool-calling agent loop (which items, quantities, when done), locally via Ollama. Tuned to ~0.97 item-F1 on the eval set (`scripts/run_brain_eval.py`).
- **Facts-from-Tools** — every price/total comes from the catalog + deterministic `compute`, never the LLM. Holds even for human edits.
- **Human-in-the-loop** — the agent pauses to ask when a price is missing; you answer and it resumes.
- **Saved Estimates** — per-account persistence: auto-save on forge, reopen from "My Estimates", resume the (sanitized) refinement chat (ADR-0013).
- **Phone capture** — call a Twilio number (it forges a draft + texts the PDF) or scan a QR to capture a photo + voice note on your phone and forge live on the desktop.
- **Frontend** — a bespoke web UI served by `gradio.Server` (FastAPI under the hood): streaming "Digital Apprentice" trace, editable estimate, PDF export.

## Run

```
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m quillwright.server          # http://127.0.0.1:7860
```

By default the models are stubbed (fast, no GPU). For the **real local models**, install [Ollama](https://ollama.com), pull the models, and set the flag:

```
ollama pull minicpm-v
ollama pull nemotron-3-nano:4b
FF_REAL_MODELS=1 python -m quillwright.server
```

### Backend resolution — read this before "am I on Modal?"

There is no single local/Modal switch. `FF_REAL_MODELS=1` is the master gate out of
stub mode; backends then resolve **per role** (see `quillwright/resolver.py`), and a
few roles can only go one way:

| Role                                      | Stub (default) | Local (Ollama)                                                         | Modal (hosted Best Stack)                                                       |
| ----------------------------------------- | -------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **brain** (agent loop)                    | scripted       | Nemotron-3-Nano **4B**                                                 | Nemotron-3-Nano **30B** — set `FF_BACKEND=modal` + `FF_MODAL_BRAIN_URL`         |
| **perception** (vision)                   | scripted       | MiniCPM-V                                                              | Nemotron **Omni** — additionally set `FF_MODAL_OMNI_URL` (else stays on Ollama) |
| **audio** (voice note)                    | scripted       | Cohere Transcribe on-device (transformers)                             | Nemotron **Omni** (same deployment as perception) — `FF_MODAL_OMNI_URL`         |
| **multilingual**                          | scripted       | Aya                                                                    | **Aya Expanse 8B** — additionally set `FF_MODAL_AYA_URL` (else stays on Ollama) |
| **embedding**                             | scripted       | on-device (sentence-transformers) — same path for any non-stub backend | _same on-device path_                                                           |
| **extraction** (Document Capture / Parse) | scripted       | _no local path_ (>30GB RAM on Apple Silicon)                           | **Modal only**, always remote — needs `FF_MODAL_PARSE_URL`                      |

How the switches compose:

- **`FF_BACKEND=modal` by itself moves only the _brain_ to Modal** (its URL is then
  required — missing `FF_MODAL_BRAIN_URL` fails loud, never silently downgrades).
- **Each other role opts in per-URL**: with `FF_BACKEND=modal` set, perception/audio
  upgrade to the hosted Omni only when `FF_MODAL_OMNI_URL` is also set, multilingual to
  Aya Expanse only when `FF_MODAL_AYA_URL` is set. Unset URLs keep the local/on-device
  path working — deploying one GPU app never breaks the roles you didn't deploy.
- **Parse keys off its own `FF_MODAL_PARSE_URL`, independent of `FF_BACKEND`.** So you can
  run a local Ollama brain _and_ hit Modal Parse at the same time — "am I on Modal?" is not
  a single yes/no. This is intentional: Parse has no local serving path (ADR-0011), but it
  means the offline ("Airplane-Mode") story only holds while every `FF_MODAL_*_URL` is unset.

### Wiring the hosted Space to Modal (live real models)

The Space can serve the real models on Modal GPUs — no tunnel involved (Modal apps are
public HTTPS endpoints; the Space just calls them). The apps are deployed and scale to zero;
wiring is purely Space **secrets** (Settings → Variables and secrets):

| Secret               | Value                           | Effect                                            |
| -------------------- | ------------------------------- | ------------------------------------------------- |
| `FF_BACKEND`         | `modal`                         | moves the **brain** to Modal (Nemotron 30B)       |
| `FF_MODAL_BRAIN_URL` | `https://<brain-app>.modal.run` | **required** when `FF_BACKEND=modal` (fails loud) |
| `FF_MODAL_OMNI_URL`  | `https://<omni-app>.modal.run`  | upgrades **vision + audio** to hosted Omni        |
| `FF_MODAL_AYA_URL`   | `https://<aya-app>.modal.run`   | upgrades **multilingual** to Aya Expanse          |
| `FF_MODAL_PARSE_URL` | `https://<parse-app>.modal.run` | enables **Document Capture** (Parse; Modal-only)  |

Get the URLs from `modal app list` / each app's deployed endpoint. Each role opts in per-URL;
unset URLs keep that role on its non-Modal path.

> **⏳ Model cold-start.** The first request to each Modal app pays a GPU cold-start — up to a
> **minute or two for the 30B brain**. The app is warming, not broken: the UI shows a "Waking
> the models" card on the first forge whenever real models are in play. **Warm the apps before
> a live demo** (hit each once). When `FF_BACKEND` is unset the Space runs in instant CPU stub
> mode (the default for the public submission link).

> **💸 Cost.** A judge-clickable hosted GPU can spend over the whole judging window. The apps
> are set to **scale to zero** when idle; confirm that before leaving the Space Modal-wired,
> and don't leave apps you only warmed for the demo serving afterwards.

> **🔒 Phone features are NOT served by the Space.** The Twilio call and QR phone-capture run
> on a **tunneled local machine** (`FF_PUBLIC_BASE_URL` = ngrok/cloudflared URL), because
> third-party send creds (Twilio) can't live on a public Space (ADR-0005). Modal serves the
> _models_; the phone _capture paths_ are the local-demo + video story.

## Finalize & Send (S10)

**Finalize & Send** delivers a finished estimate to the customer by **SMS** (Twilio MMS —
the PDF attached by URL) or **email** (SendGrid — the PDF attached inline). It has the same
honest, env-gated framing as the models:

- **Real send is opt-in and local-only.** Set `FF_SEND_ENABLED=1` plus the provider creds
  and the message is actually transmitted. The providers (`twilio`, `sendgrid`) are an
  optional extra — `pip install -e ".[send]"` — deliberately **not** in the Space
  `requirements.txt` (third-party API creds can't live on a public Space — ADR-0005).
- **The public Space drafts only.** With `FF_SEND_ENABLED` unset, `/api/send_estimate`
  returns `{status: "drafted", transmitted: false}` and the UI shows a "Draft ready —
  nothing was transmitted from this hosted demo" card. It never claims a send it didn't do.

**Email has two backends — whichever is configured wins, Gmail first.** Gmail SMTP is the
simplest (stdlib `smtplib`, no extra dep, no sender-verification step — just a Google
[App Password](https://myaccount.google.com/apppasswords)); SendGrid is the fallback.

Env vars for the real path:

| Var                                        | For       | Purpose                                               |
| ------------------------------------------ | --------- | ----------------------------------------------------- |
| `FF_SEND_ENABLED=1`                        | both      | master gate out of draft-only mode                    |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | SMS       | Twilio auth                                           |
| `FF_SEND_FROM`                             | SMS       | the Twilio sending number                             |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`     | email (1) | Gmail SMTP — preferred; sends from your Gmail address |
| `SENDGRID_API_KEY`                         | email (2) | SendGrid auth (fallback if no Gmail creds)            |
| `FF_SEND_FROM_EMAIL`                       | email (2) | the SendGrid verified sender address                  |

Facts-from-Tools holds: send introduces no numbers — the PDF and the summary line both go
through `recalc_estimate`, the same server-authoritative totals the PDF/JSON already show.
SMS needs a public PDF URL (MMS attaches by URL); the server mints one at
`/api/estimate_pdf/{token}`.

## Saved Estimates (ADR-0013)

Estimates persist per **Account** (one fixed demo account, `account_id="demo"`, no auth).
A finished forge **auto-saves**; **Save** persists mid-draft; edits **update in place**;
**Discard** deletes. **My Estimates** lists them (newest first) and reopens a frozen
snapshot — existing lines never silently re-price; only newly-added lines hit the live
catalog. Each saved estimate carries a **Refinement Thread**: the post-forge chat turns,
stored **sanitized** (intents/operations, never dollar figures), so resuming the chat can
never feed a stale number back to the model — Facts-from-Tools holds on the resume path.
Long threads are kept in-context by **deterministic compaction** done in code, not by a
model summary. JSON-on-disk behind a swappable `EstimateStore`; durable locally, per-session
on the Space (`FF_ESTIMATE_STORE`).

## Phone capture (two inbound paths)

Both reuse the same pipeline + Facts-from-Tools; both are real on a tunneled local machine
(`FF_PUBLIC_BASE_URL` = the ngrok/cloudflared URL), honestly framed everywhere else.

- **Call a number (S12)** — a Twilio Voice webhook. The caller describes the job; Quillwright
  transcribes the recording (Audio role — same resolution as the mic button), forges an
  estimate, saves it as a **draft** (a human approves later), reads the spoken total back on
  the call, and texts the PDF via the same SMS path as Finalize & Send. Webhooks:
  `POST /api/voice/incoming` (greeting + `<Record>`) → `POST /api/voice/recording`.
- **Scan a QR (phone capture)** — the desktop shows a QR (tunnel URL + a pairing code). The
  phone opens a dedicated mobile capture page (`/m/<code>`), takes a photo and/or a voice
  note, and the **desktop forges it live on screen**. QR via the optional `[capture]` extra
  (segno) — local/tunnel only, not on the Space.

## Test

```
pytest -v
ruff check . && ruff format --check .                  # Python lint/format
npx prettier --check --ignore-unknown "quillwright/web/**/*"  # web lint/format
python scripts/check_deps_sync.py                      # pyproject ↔ requirements.txt

# brain accuracy against the eval set (needs Ollama + FF_REAL_MODELS=1)
FF_REAL_MODELS=1 PYTHONPATH=. python scripts/run_brain_eval.py
```

CI (`.github/workflows/ci.yml`) runs the same gate — the dependency-sync check,
ruff lint/format, pytest, and the web prettier check. It is **manual-only** (to
conserve Actions minutes): trigger it from the Actions tab or `gh workflow run ci.yml`.

Models resolve per role via `quillwright/resolver.py` (stub ↔ Ollama). Pricing is clearly-labeled sample data.
