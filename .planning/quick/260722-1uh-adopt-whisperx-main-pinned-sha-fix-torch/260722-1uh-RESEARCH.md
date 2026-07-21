# Quick Task 260722-1uh: Adopt whisperX main (pinned SHA) + fix torchcodec/FFmpeg — Research

**Researched:** 2026-07-22
**Domain:** whisperX git-main adoption, torchcodec/FFmpeg on Windows, pyannote.audio 4.0 migration, uv git pinning
**Confidence:** HIGH (stack/versions verified), MEDIUM (pyannote 3.1-model-under-4.0 runtime behavior — needs smoke test)

## Summary

whisperX main HEAD is `2cfd7b7c5c7bba144954364db747319b50e8232b` (2026-07-13, "fix: raise actionable error when punkt_tab download fails") — pin this SHA. Main is version 3.8.7rc1 and pins torch~=2.8.0, pyannote-audio>=4.0.0, torchcodec>=0.6,<0.8 → resolver picks torchcodec 0.7.x, which requires torch 2.8 and supports **FFmpeg 4-7 only** (FFmpeg 8 support landed in torchcodec ≥0.8, which needs torch ≥2.9 — not an option under whisperX's torch~=2.8 pin). The box's gyan.dev FFmpeg 8.1 **static** build fails on both axes: no shared DLLs, wrong major. Fix: install FFmpeg 7.1 win64 **shared** build (BtbN URL verified below), prepend its `bin` to PATH in `start-server-boot.bat` (replaces `FFMPEG_DIR`, start-server-boot.bat:18) — one dir serves both torchcodec DLL discovery and whisperX's `ffmpeg.exe` subprocess (app/audio.py:12,90).

Two app-code breaks confirmed by reading whisperX main source: (1) `DiarizationPipeline` constructor is now `(model_name=None, token=None, device=None, cache_dir=None)` — app calls `use_auth_token=hf_token` at app/infrastructure/ml/whisperx_diarization_service.py:29 → `TypeError` on main. (2) Default diarization model changed from `pyannote/speaker-diarization-3.1` to `pyannote/speaker-diarization-community-1` — NOT in the box's HF cache, and `HF_HUB_OFFLINE=1` (start-server-boot.bat:37) means the default silently fails. Must pass `model_name="pyannote/speaker-diarization-3.1"` explicitly (keeps cached model) — whether the 3.1 checkpoint loads cleanly under pyannote 4.0.7 is the single biggest validation gate (MEDIUM confidence it works; see Pitfall 2).

Separately: this repo's own `pyproject.toml` `[tool.uv.sources]` markers are the root cause of the CPU-wheel clobber — `platform_machine == 'x86_64'` never matches Windows (which reports `AMD64`), so Windows resolves torch from the `pytorch-cpu` index (pyproject.toml:77-87). Upstream whisperX fixed the identical bug in commit `11bc7de` ("Fix Windows CUDA detection: include AMD64 in platform markers"). Fix markers → `uv sync` keeps cu128 torch; no post-install force-reinstall hack needed.

**Primary recommendation:** FFmpeg 7.1 shared on PATH → fix uv markers (AMD64) → pin whisperX git SHA via `[tool.uv.sources]` → patch `DiarizationPipeline(model_name="pyannote/speaker-diarization-3.1", token=...)` → smoke-test diarization + lv/ru fine-tunes in test venv before touching production `.venv`.

## Phase Requirements

| Requirement | Research Support |
|----|------------------|
| Resolve torchcodec/FFmpeg incompat | §FFmpeg + §torchcodec below — FFmpeg 7.1 shared build, verified URL |
| Adopt whisperX main at pinned SHA via uv | §uv pinning — exact pyproject syntax + marker fix |
| Diarization under pyannote 4.0.x | §pyannote 4.0 — API breaks mapped to app code lines |
| Validate transcription (en + lv/ru fine-tunes) | Prior session validated parity (known fact); re-run smoke in final venv because transformers major may differ |
| Model load time | §Open Questions — no verified upstream fix; app-level mitigation identified |

## 1. FFmpeg 7.x Shared Build for Windows

**Verified download (BtbN GitHub autobuilds)** [VERIFIED: GitHub API]:

- `https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-win64-gpl-shared-7.1.zip` (~71.5 MB)
- LGPL variant also exists: `ffmpeg-n7.1-latest-win64-lgpl-shared-7.1.zip` (~62.4 MB) — GPL variant fine here (internal service).

Caveat: the `latest` tag is **rolling** (rebuilt regularly from n7.1 branch). For reproducibility, download once, vendor into a fixed path (e.g. `C:\tools\ffmpeg-7.1-shared\`), record the sha256. Dated release tags (e.g. `autobuild-YYYY-MM-DD-...`) exist on the same repo if a frozen URL is preferred.

gyan.dev alternative: `ffmpeg-release-full-shared.7z` exists but current release is **8.1.2** — wrong major for torchcodec 0.7 [VERIFIED: gyan.dev/ffmpeg/builds]. Archived 7.1.1 shared build likely at `gyan.dev/ffmpeg/builds/packages/` but directory listing returns 403 — could not verify exact filename [LOW]. Use BtbN.

**DLL discovery on Windows** [VERIFIED: torchcodec issue #1289]: torchcodec probes `libtorchcodec_core8.dll` → `core7` → `core6` → `core5` → `core4` via ctypes/`torch.ops.load_library`; each `coreN` links FFmpeg major N (FFmpeg 7 = avcodec-61/avformat-61/avutil-59 DLLs). Dependency resolution goes through the standard Windows loader search, which includes `PATH` — the maintainer-endorsed fix is "install the full-shared version which ships DLLs" on PATH (winget `ffmpeg (shared)` works the same way). Prepending the shared `bin` dir in `start-server-boot.bat` (as line 18-19 already does for the static build) is sufficient. Belt-and-suspenders option: `os.add_dll_directory(FFMPEG_DIR)` at app startup — not required if PATH is set before python launches [ASSUMED].

**start-server-boot.bat change** (start-server-boot.bat:18):
```bat
set "FFMPEG_DIR=C:\tools\ffmpeg-7.1-shared\bin"
set "PATH=%FFMPEG_DIR%;%PATH%"
```
The shared build ships `ffmpeg.exe` too, so `whisperx.load_audio`'s bare-`ffmpeg` subprocess (app/audio.py:26,90) keeps working from the same dir. Remove/ignore the 8.1 static dir. Note MEMORY: SYSTEM scheduled task has its own environment — the .bat pins PATH so this is covered, but any manual dev shell needs the same dir.

## 2. torchcodec Version Matrix

| torchcodec | torch | FFmpeg | Notes |
|---|---|---|---|
| 0.7.x | 2.8 | **4-7** | What whisperX main resolves to (pin `>=0.6,<0.8`) [VERIFIED: torchcodec release/0.7 README + main README matrix] |
| 0.8+ | ≥2.9 | 4-8 | FFmpeg 8 support; unreachable under torch~=2.8 |

- whisperX main pins `torchcodec>=0.6.0,<0.8.0` (platform-specific) [VERIFIED: whisperX main pyproject.toml].
- pyannote.audio 4.0.7 requires `torchcodec>=0.7.0`, `torch>=2.8.0`, `torchaudio>=2.8.0` [VERIFIED: PyPI JSON] → intersection = torchcodec 0.7.x exactly.
- **Import-time hard dependency:** `pyannote.audio` imports `torchcodec.decoders.AudioDecoder` at module import; broken FFmpeg DLLs → `RuntimeError: Could not load libtorchcodec` the moment diarization service imports, even though whisperX passes in-memory waveforms (no actual file decode via torchcodec in our path) [VERIFIED: matches test-venv breakage; issue #1289].

## 3. pyannote.audio 4.0 Breaking Changes (vs 3.x)

pyannote.audio 4.0.0 released 2025-09-29; latest is **4.0.7** (2026-06-30) [VERIFIED: PyPI]. Breaking changes [VERIFIED: GitHub 4.0.0 release notes]:

| Change | Impact here |
|---|---|
| `use_auth_token` → `token` in `Pipeline.from_pretrained` | whisperX main already migrated internally; **app** must migrate its own call (below) |
| Pipeline output is `DiarizeOutput`, not `Annotation` | whisperX main handles it: `output.speaker_diarization` in `DiarizationPipeline.__call__` [VERIFIED: main diarize.py]. App receives the same `pd.DataFrame` as before — `assign_word_speakers(diarize_df, transcript, ...)` signature compatible with app/infrastructure/ml/whisperx_speaker_assignment_service.py:40 |
| Audio I/O: soundfile/sox removed, torchcodec/ffmpeg only | Covered by FFmpeg 7.1 shared fix |
| `PYANNOTE_CACHE` dropped; huggingface_hub caching | Box already uses `HF_HOME` + hub cache (start-server-boot.bat:26) — fine. `HF_HUB_OFFLINE=1` honored by huggingface_hub loading path; cached pyannote models load offline (verified 2026-07-22 per boot script comment for 3.x — re-verify under 4.0) |
| New `exclusive` diarization mode | Opt-in; whisperX main does NOT use it [VERIFIED: main diarize.py]. Ignore |
| New default model `speaker-diarization-community-1` | **whisperX main defaults to it** when `model_name=None` [VERIFIED: main diarize.py]. Not cached on box + gated + offline mode → must pass `model_name="pyannote/speaker-diarization-3.1"` explicitly |

**What whisperX main's diarize.py actually does** [VERIFIED: raw source @ main]:
```python
class DiarizationPipeline:
    def __init__(self, model_name=None, token=None, device=None, cache_dir=None):
        # default model_name -> "pyannote/speaker-diarization-community-1"
        # Pipeline.from_pretrained(model_config, token=token, cache_dir=cache_dir).to(device)
    def __call__(self, audio, ...):
        # output = self.model(audio_dict, ...); diarization = output.speaker_diarization
        # returns pd.DataFrame(['segment','label','speaker']) (+ embeddings dict if requested)
```
Also new: IntervalTree-based speaker assignment (~228x faster on long audio) — free win for `assign_word_speakers`.

**Required app change** (app/infrastructure/ml/whisperx_diarization_service.py:26-37):
```python
pipeline = DiarizationPipeline(
    model_name="pyannote/speaker-diarization-3.1",
    token=hf_token,
    device=device,
)
```
The `_load_pipeline` None-guard (lines 30-35) stays valid — pyannote 4 `from_pretrained` can still return None-ish failures; keep the fail-loud wrapper. Update `_GATED_MODEL_HINT` text if desired.

**3.1 checkpoint under pyannote 4.0.7 — MEDIUM confidence it works:** release notes claim existing pipelines keep working (checkpoint's `config.yaml` instantiates the library's `SpeakerDiarization` class, which still exists and now returns `DiarizeOutput` regardless of checkpoint) [ASSUMED — no explicit official statement found; HF model card still says "requires pyannote.audio 3.1"]. This is THE validation gate: one diarization smoke test on a known 2-speaker file, offline mode on, before promotion. Fallback if 3.1 fails to load: temporarily unset `HF_HUB_OFFLINE`, accept gated conditions for `speaker-diarization-community-1`, warm cache, re-enable offline, and A/B speaker accuracy (community-1 is claimed better via VBx clustering).

## 4. whisperX main HEAD

[VERIFIED: GitHub API, 2026-07-22]

| SHA | Date | Message |
|---|---|---|
| **`2cfd7b7c5c7bba144954364db747319b50e8232b`** | 2026-07-13 | fix: raise actionable error when punkt_tab download fails ← **pin this** |
| `8dcdec1` | 2026-06-26 | chore(deps): huggingface-hub >=0.28.1 |
| `5f2f9d4` | 2026-06-03 | regenerate uv.lock for AMD64 markers |
| `11bc7de` | 2026-05-15 | **Fix Windows CUDA detection: include AMD64 in platform markers** |
| `3ccc17b` | 2026-05-25 | bump whisperx to 3.8.6 |

Nothing merged since the prior validation session changes the picture (HEAD commit is an NLTK error-message fix — note: main uses nltk `punkt_tab` for sentence splitting; offline box should verify punkt_tab is bundled/downloaded once, or the new actionable error will fire on first alignment-dependent path that needs it [ASSUMED — verify which codepath uses nltk; likely `--highlight_words`/sentence splitting only]).

Main's pins [VERIFIED: main pyproject.toml]: torch~=2.8.0, torchaudio~=2.8.0, torchvision~=0.23.0, pyannote-audio>=4.0.0, transformers>=4.48.0, ctranslate2>=4.5.0, faster-whisper>=1.2.0, numpy>=2.1.0, nltk>=3.9.1, huggingface-hub>=0.28.1.

`transformers>=4.48.0` is an open lower bound — resolver may pick transformers 5.x. The prior parity validation (en/lv/ru) happened against whatever the test venv resolved; **copy `pip freeze` from the test venv** (`...\b0f54f43...\scratchpad\venv-wsp-main`) as the reference resolution and diff against what `uv lock` produces — any transformers/ctranslate2 major drift = re-run parity smoke.

## 5. Model-Load Slowdown (ctranslate2 4.8.x / faster-whisper 1.2.x)

No upstream GitHub issue documenting a load-time regression in ctranslate2 4.8.x or faster-whisper 1.2.x was found [LOW confidence there's an upstream fix coming — searched, nothing]. Known fact stands: 3-5 s slower per load, 16-21% slower end-to-end because the service loads models per job.

Mitigations, best-first:
1. **App-level model residency (recommended, biggest win, upstream-independent):** `WhisperXTranscriptionService.transcribe()` calls `load_model` per job then deletes it (app/infrastructure/ml/whisperx_transcription_service.py:106,135); the class already has `load_model`/`unload_model` persistence hooks (lines 147-199) that nothing uses. Caching the loaded model keyed on `(model, language, compute_type)` eliminates the regression entirely and turns the upgrade into a net speed win (alignment is 1.8x faster on main). 24 GB VRAM with ~4 GB/job and `GPU_MAX_CONCURRENT_JOBS=2` leaves headroom for 1-2 resident models. Scope decision for planner: in-scope now vs follow-up task.
2. **Bisect ctranslate2 within whisperX's pin:** `ctranslate2>=4.5.0` allows forcing `ctranslate2==4.6.0` (constraint in our pyproject / `uv add 'ctranslate2==4.6.0'`) to test whether the load regression is ct2-side. Cheap experiment in the test venv [ASSUMED it's ct2-side; could equally be faster-whisper 1.2's tokenizer/model init].
3. `local_files_only` / hub revalidation is NOT the cause — `HF_HUB_OFFLINE=1` already set.

## 6. Pinning git dep with uv (this repo's pyproject.toml)

**Syntax** [VERIFIED: docs.astral.sh/uv — Git dependency sources]:
```toml
[project]
dependencies = [
    # replace "whisperx==3.7.4" with:
    "whisperx",
    ...
]

[tool.uv.sources]
whisperx = { git = "https://github.com/m-bain/whisperX", rev = "2cfd7b7c5c7bba144954364db747319b50e8232b" }
```
`uv lock` records the exact SHA; `uv sync` is reproducible. Requires `git` on PATH for the SYSTEM/CI context that runs sync.

**CRITICAL companion fix — CUDA index markers (root cause of CPU-wheel clobber).** Current markers (pyproject.toml:77-87) route Windows to `pytorch-cpu` because Windows `platform_machine` is `AMD64`, not `x86_64`. Mirror upstream whisperX commit `11bc7de`:
```toml
[tool.uv.sources]
torch = [
  { index = "pytorch-cpu", marker = "sys_platform == 'darwin'" },
  { index = "pytorch", marker = "(platform_machine == 'x86_64' or platform_machine == 'AMD64') and sys_platform != 'darwin'" },
  { index = "pytorch-cpu", marker = "platform_machine != 'x86_64' and platform_machine != 'AMD64' and sys_platform != 'darwin'" },
]
torchaudio = [ # same three entries ]
torchvision = [ # ADD — currently missing from sources entirely (pyproject.toml:47-49 pins it but it resolves from PyPI = CPU wheel) ]
```
With markers fixed, `uv sync` resolves torch 2.8.0+cu128 / torchaudio 2.8.0+cu128 / torchvision 0.23.0+cu128 from the existing `pytorch` index (pyproject.toml:92-95) and never clobbers CUDA — the "install whisperX first, force-reinstall torch after" trap disappears for uv-managed installs. Note: whisperX's own `[tool.uv.sources]`/index config is ignored when consumed as a dependency (uv honors only the workspace root's sources) — our pyproject governs [VERIFIED: uv docs behavior].

Also update loose pins for coherence: `torch<=2.8.0` + whisperX's `torch~=2.8.0` intersect at 2.8.0 — OK as-is. torchcodec needs no explicit entry (transitive via whisperX/pyannote; wheel is CPU-side FFmpeg binding — PyPI wheel fine) [ASSUMED: no cu-specific torchcodec wheel needed for decode-on-CPU usage; test venv used PyPI wheel].

## 7. App API-Surface Migration Map (complete)

| Call site | Symbol | main status |
|---|---|---|
| app/infrastructure/ml/whisperx_transcription_service.py:8,106,180 | `whisperx.load_model(...)` | unchanged signature — compatible |
| app/infrastructure/ml/whisperx_alignment_service.py:8 | `whisperx.align`, `whisperx.load_align_model` | unchanged — compatible (1.8x faster, backtrack_beam gone) |
| app/infrastructure/ml/whisperx_diarization_service.py:9,29 | `whisperx.diarize.DiarizationPipeline(use_auth_token=...)` | **BREAKS** — `token=` + explicit `model_name=` required (see §3) |
| app/infrastructure/ml/whisperx_speaker_assignment_service.py:40 | `whisperx.assign_word_speakers(df, transcript)` | compatible (new optional params only) |
| app/audio.py:12-13,90 | `whisperx.load_audio`, `whisperx.audio.SAMPLE_RATE` | unchanged module path — compatible; still shells to bare `ffmpeg` (FFMPEG_DIR PATH covers it) |

## Common Pitfalls

1. **`uv sync` before marker fix** → silently reinstalls CPU torch; CUDA gone; jobs 10x slower. Fix markers in the SAME commit as the git pin. Verify after sync: `python -c "import torch; assert torch.cuda.is_available()"`.
2. **Diarization default model swap** → with `HF_HUB_OFFLINE=1`, `DiarizationPipeline(token=...)` without `model_name` tries `community-1`, not cached → opaque failure at diarize step. Always pass `model_name="pyannote/speaker-diarization-3.1"`.
3. **FFmpeg 8 shared instead of 7** → torchcodec 0.7 has no `core8` binding for its wheel range... actually 0.7 ships core4-7 only; FFmpeg 8 DLLs won't be probed successfully. Must be major 7 (or 6).
4. **SYSTEM task environment** — production runs as SYSTEM via "\WhisperX Backend" scheduled task; PATH/FFMPEG_DIR comes only from start-server-boot.bat. Update the .bat, then restart task elevated. Manual `start-server.bat` (dev) needs the same FFMPEG_DIR edit — check it too.
5. **transformers major drift** between test venv (validated) and uv-resolved venv — diff `pip freeze` vs `uv.lock`; re-smoke lv/ru fine-tune parity if transformers/ctranslate2/faster-whisper versions differ.
6. **nltk punkt_tab offline** — main HEAD's newest commit exists precisely because punkt_tab download failures were opaque; on an offline box, pre-download `python -c "import nltk; nltk.download('punkt_tab')"` once during setup [ASSUMED this codepath triggers in our pipeline — verify during smoke].

## Validation Sequence (for planner)

1. In existing test venv (`venv-wsp-main`): drop FFmpeg 7.1 shared bin onto PATH → `python -c "from torchcodec.decoders import AudioDecoder"` → `python -c "from pyannote.audio import Pipeline"` — proves DLL fix without touching production.
2. Same venv: patched `DiarizationPipeline(model_name='pyannote/speaker-diarization-3.1', token=...)` with `HF_HUB_OFFLINE=1` on a known 2-speaker file — proves 3.1-under-4.0.7 (the MEDIUM-confidence gate).
3. Repo changes: pyproject (git SHA pin + AMD64 markers + torchvision source) + diarization service patch + both .bat FFMPEG_DIR edits → `uv sync` into a fresh venv (or `.venv` after backup) → `torch.cuda.is_available()` check → en/lv/ru transcription smoke + diarization smoke + model-load timing capture.
4. Promote: restart "\WhisperX Backend" scheduled task elevated; watch logs/backend-boot.log first job end-to-end.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | speaker-diarization-3.1 checkpoint loads + runs under pyannote 4.0.7 | §3 | Diarization blocked; fallback = warm community-1 cache online, A/B quality |
| A2 | PATH-only DLL discovery sufficient (no os.add_dll_directory needed) | §1 | Add `os.add_dll_directory` at app startup — 3-line fix |
| A3 | torchcodec PyPI wheel (non-CUDA-specific) sufficient for our decode path | §6 | Would need FFmpeg-CUDA build — very unlikely, decode is trivial here |
| A4 | Model-load regression is ct2/faster-whisper-side (not fixable by flag) | §5 | Mitigation 1 (model residency) works regardless |
| A5 | nltk punkt_tab needed by some main codepath on this box | Pitfalls | One-time pre-download is harmless either way |

## Sources

### Primary (HIGH)
- github.com/m-bain/whisperX — main HEAD commits (GitHub API), raw `whisperx/diarize.py` @ main, raw `pyproject.toml` @ main
- github.com/meta-pytorch/torchcodec — README matrix (main + release/0.7 branch), issue #1289 (Windows DLL discovery + fix)
- github.com/pyannote/pyannote-audio — 4.0.0 release notes
- pypi.org/pypi/pyannote.audio/json — 4.0.x release list + deps (4.0.7 latest, torchcodec>=0.7)
- api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest — exact shared-build asset URLs
- docs.astral.sh/uv — git dependency `rev` pinning syntax
- Codebase: pyproject.toml:40,47-49,77-100; start-server-boot.bat:18-19,26,37; app/infrastructure/ml/whisperx_diarization_service.py:9,26-37; whisperx_transcription_service.py:8,106; whisperx_alignment_service.py:8; whisperx_speaker_assignment_service.py:40; app/audio.py:12-13,90

### Secondary (MEDIUM)
- gyan.dev/ffmpeg/builds — current release 8.1.2, shared variant exists; 7.x archive dir 403'd
- WebSearch: pyannote 4.x DiarizeOutput behavior, torchcodec Windows DLL threads

### Known-facts input (prior validated session, not re-derived)
- Transcript parity en/lv/ru, alignment 1.8x, model load 3-5s slower, install-order trap, driver 591.86/cu128 OK

**Research date:** 2026-07-22 · **Valid until:** ~2026-08-22 (BtbN `latest` tag rolls; whisperX main moves — SHA pin insulates)
