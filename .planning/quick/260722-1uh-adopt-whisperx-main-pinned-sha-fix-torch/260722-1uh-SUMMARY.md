---
phase: quick-260722-1uh
plan: 01
subsystem: ml-runtime
tags: [whisperx, pyannote, torchcodec, ffmpeg, uv, cuda]
requires: []
provides:
  - "whisperX git main (SHA 2cfd7b7c) in production .venv, backtrack_beam removed"
  - "pyannote.audio 4.0.7 diarization with pinned speaker-diarization-3.1, fully offline"
  - "FFmpeg 7.1 shared vendored at C:\\tools\\ffmpeg-7.1-shared (torchcodec compat)"
  - "AMD64-correct CUDA wheel markers (root-cause fix for CPU-wheel clobber)"
affects: [transcription, diarization, server-launchers, dependency-resolution]
tech-stack:
  added: [torchcodec 0.7.0, websockets 16.0 (now explicit)]
  patterns: ["os.add_dll_directory for native DLL deps (py3.8+ Windows)", "SYSTEM-profile env pins (HF_HOME, NLTK_DATA, FFMPEG_DIR)"]
key-files:
  created: [app/core/dll_paths.py]
  modified: [pyproject.toml, uv.lock, app/infrastructure/ml/whisperx_diarization_service.py, app/main.py, start-server-boot.bat, start-server.bat]
decisions:
  - "Pinned pyannote/speaker-diarization-3.1 explicitly (main defaults to gated community-1)"
  - "Warm-cached community-1 PLDA npz files (owner accepted HF gate) instead of shimming get_plda in production"
  - "websockets declared explicitly — uvicorn pinned without [standard]; new tree dropped it transitively"
  - "Model residency cache NOT implemented (report-only per owner)"
metrics:
  duration: "~3h across two agent sessions (checkpoint: HF gate acceptance)"
  completed: "2026-07-22"
---

# Quick Task 260722-1uh: Adopt whisperX main (pinned SHA) + fix torch markers — Summary

whisperX main (3.8.7rc1, SHA 2cfd7b7c) promoted to production: FFmpeg 7.1 shared fixes torchcodec, AMD64 markers fix CPU-wheel clobber at root cause, diarization runs pyannote 4.0.7 + pinned 3.1 model fully offline, backend restarted and serving — **PROMOTED**.

## Verdict: PROMOTED

All gates green. Production backend restarted on empty queue, serving jobs on whisperX main under SYSTEM environment with HF_HUB_OFFLINE=1.

## Diarization Verdict (was the highest-risk gate)

**PASSED un-shimmed, fully offline.** pyannote/speaker-diarization-3.1 loads and runs under pyannote.audio 4.0.7 with HF_HUB_OFFLINE=1.

- Blocker found: pyannote 4.x `get_plda()` eagerly downloads `plda/xvec_transform.npz` + `plda/plda.npz` from **gated** `pyannote/speaker-diarization-community-1` even when running the 3.1 pipeline (PLDA is only consumed by VBxClustering, which 3.1 never uses).
- Resolution: owner accepted the community-1 HF gate; both npz files warm-cached (134,376 + 133,852 bytes, snapshot 3533c8cf). Offline boots now clean.
- Un-shimmed gate results (identical in test venv AND production .venv AND live API): 40 rows, 2 speakers, flat `start`/`end` columns present — response mapping unchanged, `[{label,speaker,start,end}]` confirmed end-to-end.
- New-machine setup note: HF_TOKEN owner must have accepted BOTH `pyannote/speaker-diarization-3.1` and `pyannote/speaker-diarization-community-1` gates, then run one online diarization (or hf_hub_download of the two plda files) before enabling offline mode.

## load_model Timing: 3.7.4 vs main (production hardware)

| Model | 3.7.4 cold | 3.7.4 warm | main (test venv) | main (prod venv) cold | main (prod venv) warm |
|---|---|---|---|---|---|
| large-v3 (en) | 16.92s | 15.96s | 26.39s / 13.12s warm | 13.27s | 9.39s |
| raivis-small-lv-ct2-fp16 (lv) | 12.02s | 14.12s | 15.38s | 6.68s | — |
| faster-whisper-large-v3-russian (ru) | 15.60s | 15.69s | 20.73s | 9.23s | — |

**Main in the production venv is FASTER than 3.7.4 on every model** (en warm 9.39s vs 15.96s; lv 6.68s vs 12.02s; ru 9.23s vs 15.60s). The earlier test-venv slowness did not reproduce in the promoted venv (prod venv resolved transformers 4.57.1 vs test venv's 5.14.1 — see freeze diff below). No load-time regression to mitigate.

**Model-residency recommendation (report-only, NOT implemented):** `WhisperXTranscriptionService` has unused `load_model`/`unload_model` residency hooks (whisperx_transcription_service.py:147-199). Caching the loaded model keyed `(model, language, compute_type)` would cut 6-13s from every job. With 24GB VRAM and 2-way concurrency there is headroom. Owner may schedule separately.

## Word-Coverage Parity: en/lv/ru

| Lang | Metric | 3.7.4 baseline | main (prod venv) |
|---|---|---|---|
| en | words timed / total | 13/13 | 13/13 |
| en | zero-word segments | 0 | 0 |
| lv | words timed / total | 55/55 | 55/55 |
| lv | zero-word segments | 0 | 0 |
| ru | words timed / total | 62/62 | 62/62 |
| ru | zero-word segments | 0 | 0 |

Zero regression. Align is also faster on main (lv 0.40s vs 1.88s; ru 0.37s vs 1.95s).

## Post-Restart API Smokes (SYSTEM env, offline, FFmpeg 7.1)

- Boot log clean — no import/DLL/torchcodec errors; startup sweep + scheduler normal.
- `GET /health` → 200.
- `POST /speech-to-text` (en) → completed; 12/12 words with start+end timestamps. (Minor transcript wording variance vs baseline run — "the test"/"film-line" vs "a test"/"phone line" on the deliberately phone-quality sample; nondeterministic decode, coverage unaffected.)
- `POST /service/transcribe` (en) → completed (segment-level route, by design no words).
- `POST /service/diarize` (2-speaker lv, min=max=2) → 40 rows `[{label,speaker,start,end}]`, speakers {SPEAKER_00, SPEAKER_01}. First row identical to offline gate output.
- Smoke API key (id=8, user 3) minted via production KeyService, revoked after smokes; plaintext file deleted.

## Commits

| Hash | Message |
|---|---|
| 4ab7f29 | feat(deps): pin whisperx to main SHA 2cfd7b7; fix AMD64 CUDA markers + torchvision source |
| 1cc8106 | fix(diarization): pyannote 4.x API - token= + explicit speaker-diarization-3.1 model |
| 4436ed9 | chore(ops): pin FFmpeg 7.1 shared in both server launchers (torchcodec DLL compat) |
| 73124b5 | fix(deps): declare websockets explicitly - whisperX main tree dropped it transitively |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] setuptools flat-layout build failure on `uv sync`**
- **Found during:** Task 2d (first sync attempt)
- **Issue:** Root project build failed — auto-discovery found multiple top-level dirs (app, data, logs, models, alembic, frontend, node_modules) accumulated at repo root.
- **Fix:** Explicit `[tool.setuptools.packages.find] include = ["app*"]`.
- **Files modified:** pyproject.toml
- **Commit:** 4ab7f29

**2. [Rule 3 - Blocking] websockets dropped from dependency tree → boot crash**
- **Found during:** Task 3 (first restart)
- **Issue:** Old lock carried `websockets==16.0` transitively; new whisperX-main resolution removed it. First (lock-interrupted) sync also left a mangled partial `websockets` install. uvicorn WS protocol import crashed the boot (`ModuleNotFoundError: websockets.legacy.handshake`).
- **Fix:** Purged mangled install; declared `websockets==16.0` explicitly (uvicorn is pinned WITHOUT `[standard]`; websocket_router needs it); re-synced; clean restart.
- **Files modified:** pyproject.toml, uv.lock
- **Commit:** 73124b5

**3. [Rule 2 - Missing critical] NLTK_DATA pin for SYSTEM profile**
- **Found during:** Task 2d (punkt_tab pre-download)
- **Issue:** punkt_tab downloads to the desktop user's `%APPDATA%\nltk_data`; the SYSTEM-run backend resolves a different APPDATA and would fail sentence splitting — same failure class as the documented HF_HOME pin.
- **Fix:** `set "NLTK_DATA=C:\Users\rolan\AppData\Roaming\nltk_data"` in start-server-boot.bat.
- **Commit:** 4436ed9

### Authentication Gates

**HF gated model (checkpoint:human-action, previous session):** pyannote 4.x required read access to gated `pyannote/speaker-diarization-community-1` for PLDA files. Owner accepted the gate; this session warm-cached both files and re-validated un-shimmed offline. Normal flow, resolved.

## Operational Record

- FFmpeg 7.1 shared (BtbN `ffmpeg-n7.1-latest-win64-gpl-shared-7.1.zip`) sha256: `1c8b6099ca423e56e2d1a97adeea251abc453abfc15ce4d9d9e585ef08235322`; vendored to `C:\tools\ffmpeg-7.1-shared\bin`. Old winget 8.1 static dir left intact (rollback).
- Rollback path: `git revert` the four commits + `uv sync` → restores whisperx==3.7.4; 8.1 dir still referenced by reverted .bat files.
- Freeze diff test venv → prod venv: transformers 5.14.1→4.57.1 (major), ctranslate2 4.8.1→4.6.0, faster-whisper 1.2.1→1.2.0. Drift triggered the mandated in-prod-venv re-smoke (en/lv/ru) — all parity green (tables above).
- Backend stopped/started via `schtasks //end` / `//run` on `\WhisperX Backend` (shell was elevated); queue confirmed 0 processing (UTC-safe check) before both.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes. Threat register dispositions honored: SHA pinned in uv.lock (T-q1uh-01), zip sha256 recorded (T-q1uh-02), HF_TOKEN read from .env only, smoke-key plaintext deleted (T-q1uh-03), queue-empty gate enforced (T-q1uh-04).

## Self-Check: PASSED

- app/core/dll_paths.py — FOUND
- C:\tools\ffmpeg-7.1-shared\bin\ffmpeg.exe — FOUND (validated Task 1)
- Commits 4ab7f29, 1cc8106, 4436ed9, 73124b5 — FOUND in git log
- Backend serving: /health 200, transcription + diarization jobs completed post-restart
