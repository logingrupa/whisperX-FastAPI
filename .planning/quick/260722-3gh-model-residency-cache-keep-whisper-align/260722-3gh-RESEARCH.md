# Quick Task 260722-3gh: Model-Residency Cache (whisper + align warm in VRAM) — Research

**Researched:** 2026-07-22
**Domain:** WhisperX/ctranslate2 model lifecycle, in-process VRAM caching, 2-thread GPU concurrency
**Confidence:** HIGH (codebase seams read directly; concurrency model verified), MEDIUM (VRAM peaks — estimate, measure with nvidia-smi during rollout)

## Summary

Backend is ONE uvicorn process (start-server-boot.bat:69 — no `--workers`); jobs run as Starlette BackgroundTasks = **threads in that process** (`threading.Semaphore` in gpu_lock proves the model; bfebc3e commit message: "BackgroundTasks die with the process"). Shared in-process VRAM cache is therefore VALID — no process-boundary problem. Every job today loads its model inside the job body and destroys it after (`gc.collect() + torch.cuda.empty_cache() + del`), paying 6.7–9.4 s per job.

**Primary recommendation:** module-level model registry (`app/infrastructure/ml/model_registry.py`): dict keyed per model kind, per-entry `threading.Lock` held for the whole inference call, keep-all (no LRU — full resident set ≈ 10.7 GB weights, fits 24 GB with 2 jobs' activations), evict-all on CUDA errors, keep-cache on app errors. Env toggle `MODEL_CACHE_ENABLED` on flat `WhisperSettings`.

## Design-Relevant Flags (read first)

1. **NOT process-based — cache design valid.** Single process + thread workers confirmed (see §Concurrency).
2. **`FasterWhisperPipeline.transcribe()` MUTATES shared instance state** — reassigns `self.tokenizer` (asr.py:236-255) and swaps `self.options` when `suppress_numerals` (asr.py:256-262, reverted at :294-296) [VERIFIED: `inspect.getsource` on installed whisperx @2cfd7b7]. One cached pipeline instance is **NOT safe for 2 concurrent `transcribe()` calls** regardless of ct2-core thread safety → per-entry lock mandatory.
3. **Two construction paths must share ONE cache.** `/speech-to-text` builds services **fresh per job** (whisperx_wrapper_service.py:341-346); `/service/*` uses lru-cached singletons (app/core/services.py:87-111). A cache stored on service instances would only help the singleton path. Registry must be module-level, consulted by both.
4. **`torch.cuda.memory_allocated` is blind to ct2.** ctranslate2 allocates VRAM outside the torch caching allocator — the app's existing per-job GPU-memory debug logs (whisperx_transcription_service.py:69-73,126-142) report near-zero even with large-v3 loaded. Measure residency with `nvidia-smi` / pynvml only. [VERIFIED: observable in existing logs; ct2 uses its own CUDA allocator]
5. **Multi-worker future-proofing:** if anyone ever adds `--workers N` to uvicorn, the cache duplicates per process and VRAM math breaks. Add a comment/guard in the registry module.

## Codebase Seams (file:line)

### Job flow
- **Full pipeline** `/speech-to-text`: audio_api.py:167,280 `background_tasks.add_task(process_audio_common, audio_params)` → `process_audio_common` (app/services/whisperx_wrapper_service.py:307) → constructs services fresh at :341-346 → holds `gpu_slot` for transcribe→align→diarize→combine (:402-464).
- **Individual services** `/service/transcribe|align|diarize`: audio_services_api.py:93,197,298 inject lru-cached singletons (app/core/services.py:87-111) → `process_transcribe/process_alignment/process_diarize` (app/services/audio_processing_service.py:198,274,241) → `process_audio_task` wraps the callable in `gpu_slot` (audio_processing_service.py:122).

### Load / unload today (all load-per-job, destroy-after)
| Service | Load | Destroy |
|---|---|---|
| Transcription | `whisperx.load_model` at whisperx_transcription_service.py:106 | gc + `empty_cache` + `del` at :133-135 |
| Alignment | `load_align_model` at whisperx_alignment_service.py:75 | :98-101 |
| Diarization | `_load_pipeline` (DiarizationPipeline) at whisperx_diarization_service.py:101 (module fn :35-50, model pinned `_DIARIZATION_MODEL` :19) | :116-118 |

Language override resolution happens BEFORE load: `settings.whisper.resolve_model_for_language` (whisperx_transcription_service.py:82-92; config.py:116-127). Cache key must use the **resolved** model + compute_type.

### Unused residency hooks (prior research flag — confirmed)
- `WhisperXTranscriptionService.load_model/unload_model` — whisperx_transcription_service.py:147-199, stores to `self.model`.
- `WhisperXAlignmentService.load_model/unload_model` — whisperx_alignment_service.py:113-139 (`self.model`, `self.metadata`).
- `WhisperXDiarizationService.load_model/unload_model` — whisperx_diarization_service.py:130-149.
- **Zero callers** anywhere in app/ [VERIFIED: grep `.load_model(`/`.unload_model(` — only definitions]. They are instance-scoped (`self.model`) so they don't solve Flag 3 anyway; delete or rewrite to delegate to the registry.

### Dead legacy code (cleanup candidate, not blocking)
`transcribe_with_whisper` / `diarize` / `align_whisper_output` (whisperx_wrapper_service.py:79-304) are exported from app/services/__init__.py:14-32 but have no callers; the legacy `diarize()` still passes `use_auth_token=` (:204) which is a `TypeError` on whisperX main — proof it never runs in prod. Do not add caching there; delete when convenient.

### Config seam for env toggle
`WhisperSettings` (config.py:65) — **flat** env names (no prefix): `HF_TOKEN`, `WHISPER_MODEL`, `LANGUAGE_MODEL_OVERRIDES`, etc. Commit f50344e made flat .env keys load into nested settings. Add e.g. `MODEL_CACHE_ENABLED: bool = Field(default=True)` (env `MODEL_CACHE_ENABLED`) + optionally `MODEL_CACHE_MAX_MODELS: int` here. SYSTEM task reads .env from repo — no .bat change needed unless you want it pinned there too.

## Concurrency Model (CRITICAL question answered)

- `gpu_slot` = process-wide `threading.Semaphore(GPU_MAX_CONCURRENT_JOBS)` (app/core/gpu_lock.py:31-33); boot script sets `GPU_MAX_CONCURRENT_JOBS=2` (start-server-boot.bat:54).
- Uvicorn launched WITHOUT `--workers` (start-server-boot.bat:69) → 1 process. BackgroundTasks execute on Starlette's anyio threadpool → **threads**. `threading.Semaphore` would be useless across processes — the design itself confirms thread model.
- Note: concurrency_slot.py is **billing** slot accounting (FreeTierGate refund), unrelated to hardware concurrency (gpu_lock.py:14-16 documents the distinction). The residency cache interacts with `gpu_slot`, not FreeTierGate.

**Consequence:** max 2 threads inside `gpu_slot` simultaneously. Cache must tolerate exactly-2-way concurrent access. A per-entry lock caps worst case at "2 same-language jobs serialize inference but skip load" — still strictly faster than today (load was serialized inside `gpu_slot` anyway).

## ctranslate2 Thread Safety

- ct2 core: computation methods release the GIL; calling from multiple Python threads is supported and runs in parallel only with multiple workers (`inter_threads` for CPU, `device_index=[...]` for multi-GPU). Single GPU + default config = one model replica; concurrent calls queue on it — safe, serialized. [CITED: opennmt.net/CTranslate2/parallel.html]
- **But the whisperx wrapper is the binding constraint:** `FasterWhisperPipeline` state mutation (Flag 2) makes concurrent `transcribe()` on one instance unsafe at the Python level (tokenizer swap race → wrong-language decode, options race under suppress_numerals).
- **Decision: per-entry `threading.Lock`** held around the whole `transcribe()`/`align()`/`pipeline()` call. Trade-off vs per-slot duplicate instances: duplicate large-v3 costs +3.1 GB VRAM to win nothing (ct2 single-GPU serializes the heavy compute anyway). Lock wins.
- pyannote `Pipeline.__call__` thread safety is undocumented — same per-entry lock covers it [ASSUMED: not guaranteed thread-safe; lock removes the question].
- wav2vec2 align forward under `no_grad` is technically thread-safe, but keep the uniform lock (simplicity; DRY one locking rule).

## VRAM Math (RTX 4090, 24 GB)

Weights on disk (measured, `du`): ru large-v3 fp16 = 2.9 GB; lv small fp16 = 465 MB; en large-v3 (HF cache) ≈ 3.1 GB.

| Resident item | Est. VRAM |
|---|---|
| large-v3 en, ct2 fp16 | ~3.1 GB weights; ~3.4–4.7 GB during inference [CITED: SYSTRAN/faster-whisper README benchmarks; spheron/gigagpu VRAM tables] |
| large-v3-russian, ct2 fp16 | ~3.1 GB |
| raivis-small-lv ct2 fp16 | ~0.5 GB |
| align en (torchaudio WAV2VEC2_ASR_BASE_960H, fp32) | ~0.4 GB |
| align lv + ru (wav2vec2-large-xlsr HF, fp32) | ~1.3 GB each |
| pyannote 3.1 pipeline (segmentation + embedding) | ~1 GB [ASSUMED] |
| **Keep-all resident total** | **~10.7 GB** |
| + 2 concurrent jobs' activations (batch 16, whisperx batched pipeline) | ~2–4 GB each [ASSUMED — batched inference inflates activations, see faster-whisper issue #1257] |
| **Worst case** | **~19 GB < 24 GB** ✔ |

**Keep-all fits. No LRU needed for the current 3-language fleet.** Guard anyway: registry cap (`MODEL_CACHE_MAX_MODELS`, default 8) with oldest-first evict, so a future 4th fine-tune can't creep past budget silently. Measurement method: pynvml (`nvmlDeviceGetMemoryInfo`) or `nvidia-smi --query-gpu=memory.used` — NOT `torch.cuda.memory_allocated` (Flag 4).

## Eviction / Lifecycle Patterns (prior art)

- **speaches / faster-whisper-server `ModelManager`:** per-model TTL — default 300 s idle unload, `-1` = never unload, `0` = unload immediately; self-disposing model wrapper with per-model lock + reference counting. [CITED: github.com/etalab-ia/faster-whisper-server src/faster_whisper_server/config.py; speaches-ai/speaches issue #327]
- **wordcab-transcribe:** loads models once into long-lived singleton services, no per-job load.
- **Fit here:** owner box, fixed 3-language fleet, dedicated GPU → TTL adds complexity for no benefit. **Keep-all + count cap** is the right scope. TTL can be a later env knob if the box ever shares the GPU.

Recommended cache keys:
- whisper: `(resolved_model, device, device_index, compute_type, language, task, threads, hash(asr_options), hash(vad_options))` — asr/vad options are baked into the pipeline at `load_model` time; API defaults are constant so hit rate is high, but the hash keeps correctness when a caller overrides options. VAD model rides inside the cached pipeline (loaded by `whisperx.load_model`) — cached for free.
- align: `(language_code, device, model_name)` — value is the `(model, metadata)` tuple.
- diarize: `(device,)` — model name is the pinned constant (whisperx_diarization_service.py:19).

On the cached path, **remove** the per-job `gc.collect()/torch.cuda.empty_cache()/del` blocks (whisperx_transcription_service.py:133-135, alignment :98-101, diarization :116-118) — they'd evict nothing (registry holds a reference) but `empty_cache` per job adds sync stalls and thrashes the torch allocator used by align/pyannote.

## Failure Isolation

| Failure class | Cached model reusable? | Action |
|---|---|---|
| App errors (ValidationError, alignment KeyError, bad audio, HTTP callback fail) | Yes — model state untouched (transcribe reverts its mutations in-band; lock released via try/finally) | Keep cache |
| CUDA OOM (`torch.cuda.OutOfMemoryError`, or `RuntimeError` whose message contains "out of memory" — ct2 surfaces OOM as RuntimeError text) | Weights themselves intact, but VRAM pressure caused the failure | **Evict ALL** registry entries + `gc.collect()` + `torch.cuda.empty_cache()`, then let the job fail/retry — next job reloads cold (back to today's behavior, self-healing) |
| Other CUDA errors ("illegal memory access", "CUDA error:", driver stall) | No — CUDA context may be corrupted process-wide; any resident model is suspect | Evict all; log loud. If errors persist the fix is process restart (stale_task_reaper from bfebc3e already sweeps orphaned `processing` rows on boot) [ASSUMED: standard CUDA-context semantics] |

Pattern: one `evict_on_cuda_error(exc)` helper in the registry; called from the existing exception arms in `process_audio_common` (whisperx_wrapper_service.py:492-552) and `process_audio_task` (audio_processing_service.py:148-188). Detection = `isinstance(exc, torch.cuda.OutOfMemoryError) or ("cuda" in str(exc).lower() and isinstance(exc, RuntimeError))` — subtype-first, string-match fallback for ct2.

## Recommended Design (for planner)

1. **New module `app/infrastructure/ml/model_registry.py`** (SRP: residency only). Registry dict + registry-level lock for get-or-load + per-entry lock for inference; `MODEL_CACHE_ENABLED` bypass returns fresh loads (today's behavior = rollback path).
2. **Services consult registry** — `transcribe()`/`align()`/`diarize()` swap `load_model...del` for `with registry.lease(key, loader) as model:`. Both construction paths (Flag 3) converge automatically because the registry is module-level.
3. **Config:** `MODEL_CACHE_ENABLED: bool = True` (+ optional `MODEL_CACHE_MAX_MODELS: int = 8`) on `WhisperSettings` (config.py:65).
4. **Evict-on-CUDA-error** helper wired into the two worker exception paths.
5. **Optional warmup** (follow-up, not required): load en large-v3 + en align at startup in app/main.py lifespan — first-job latency win only.
6. Delete or delegate the dead `load_model/unload_model` hooks; note legacy wrapper trio as separate cleanup.
7. **Validation:** run 2 simultaneous jobs same language + different languages; watch `nvidia-smi` for residency plateau (~11 GB idle-warm) and confirm no per-job load log lines; confirm OOM path evicts (force with a tiny `CUDA_VISIBLE_DEVICES` box or synthetic raise in test).

## Assumptions Log

| # | Claim | Risk if wrong |
|---|---|---|
| A1 | pyannote 3.1 pipeline ~1 GB VRAM resident | Measure with nvidia-smi; keep-all still fits even at 2-3 GB |
| A2 | 2 concurrent batched jobs' activations ≤ ~4 GB each | If tighter: drop batch_size for concurrent case or cap cache count — headroom is ~5 GB either way |
| A3 | Non-OOM CUDA errors corrupt context → evict-all + eventual restart is correct | Over-eviction only costs one cold load; safe direction |
| A4 | pyannote Pipeline not thread-safe | Per-entry lock already covers it |

## Sources

- Codebase [VERIFIED]: app/core/gpu_lock.py:31-54; start-server-boot.bat:54,69; app/services/whisperx_wrapper_service.py:79-346,402-464,492-552; app/services/audio_processing_service.py:122,148-195; app/infrastructure/ml/whisperx_transcription_service.py:69-199; whisperx_alignment_service.py:75-139; whisperx_diarization_service.py:19,35-149; app/core/services.py:87-111; app/api/audio_api.py:167,280; app/api/audio_services_api.py:93,197,298; app/core/config.py:65-127; commit bfebc3e.
- whisperx asr.py @2cfd7b7 [VERIFIED: inspect.getsource in prod .venv] — transcribe() tokenizer/options mutation + revert.
- [CTranslate2 parallel docs](https://opennmt.net/CTranslate2/parallel.html) — GIL release, multi-thread calls, replicas via inter_threads/device_index.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) + [issue #1257](https://github.com/SYSTRAN/faster-whisper/issues/1257) — large-v3 fp16 VRAM, batched-inference memory growth; [whisper-large-v3 VRAM table](https://www.spheron.network/tools/gpu-recommender/openai/whisper-large-v3/), [gigagpu VRAM table](https://gigagpu.com/whisper-vram-requirements/).
- [faster-whisper-server config.py](https://github.com/etalab-ia/faster-whisper-server/blob/master/src/faster_whisper_server/config.py) — ModelManager TTL (300 s default, -1 never, 0 immediate); [speaches issue #327](https://github.com/speaches-ai/speaches/issues/327).
- Local model dirs measured with `du` (2.9 GB ru / 465 MB lv).

**Research date:** 2026-07-22 · **Valid until:** stack-stable (~30 days); VRAM figures re-measure at rollout.
