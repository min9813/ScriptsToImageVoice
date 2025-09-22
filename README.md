ScriptsToImageVoice Pipeline

End‑to‑end pipeline to turn a subscription/script file (sub.json) into:
- Per‑scene VOICEVOX audio and a combined .srt subtitle
- Image prompts extracted from sub.json
- Images generated via Playwright automation against ChatGPT

This README documents the pipeline, commands, configuration, troubleshooting, and a proposed clean architecture that preserves current behavior while making the system easier to extend and test.

**At A Glance**
- Input: `sub.json` containing scenes with text, optional `image_prompt`s
- Stage 1: Generate per‑scene audio + combined `.srt`
- Stage 2: Extract image prompts into `prompts.json`
- Stage 3: Use Playwright to iterate prompts and save images + run logs

**Repo Layout (current)**
- `scene_voice_generator.py` — Main entry for audio generation; also drives subtitle creation
- `scene_subtitle_generator.py` — Subtitle generator used by the above (or standalone)
- `chatgpt-playwright/scripts/get_image_prompts.py` — Extract image prompts from `sub.json`
- `chatgpt-playwright/generateImageLoop_resilient.ts` — Robust Playwright operator
- `chatgpt-playwright/pipeline.sh` — Convenience wrapper to run prompts → image generation
- `../apis/voicevox.py` — VOICEVOX API client used by audio generation

**Quick Start**
- Python 3.10+ and Node.js 18+ recommended
- Install Node deps in `chatgpt-playwright`: `cd chatgpt-playwright && npm i`
- Install Playwright browsers: `npx playwright install`
- Sign in to ChatGPT once for Playwright profile: `npx ts-node setupLogin.ts`
- Ensure VOICEVOX engine is running (default `127.0.0.1:50021`)

**Pipeline Stages**
- Stage 1 — Audio + SRT
  - Runs VOICEVOX synthesis per scene and produces `scene_*/voice_audio.wav`, `scene_*/voice_query.json`, `scene_*/scene_sub.json`, and combined `combined_subtitles.srt`.
  - Command examples (from `scene_voice_generator.py:main`):
    - Basic: `python3 scene_voice_generator.py --json_path <path/to/sub.json> --output_dir <out_dir>`
    - Disable combining audio: `python3 scene_voice_generator.py --json_path <sub.json> --output_dir <out_dir> --no_combine`
    - Change silence between scenes: `python3 scene_voice_generator.py --json_path <sub.json> --output_dir <out_dir> --silence_duration 1.0`
  - Output structure (under `<out_dir>`):
    - `scene_*/`
      - `script.txt` — concatenated scene text
      - `voice_query.json` — VOICEVOX audio query (includes speedScale)
      - `voice_audio.wav` — synthesized audio
      - `scene_sub.json` — scene JSON enriched with `title_kana` and `texts_kana`
    - `combined_all_scenes.wav` — when combining enabled and >1 scene
    - `combined_subtitles.srt` — combined subtitles aligned to timing

- Stage 2 — Prompt Extraction
  - Extracts every sufficiently detailed `image_prompt` from `sub.json` (scene and content level), de‑duplicates, and writes `prompts.json` into a project folder.
  - Command: `python3 chatgpt-playwright/scripts/get_image_prompts.py <project_name>`
    - Looks for `t_sozai/upload_movies/<project_name>/sub.json` under base path
    - Saves to `chatgpt-playwright/projects/<project_name>/prompts.json`
  - Utilities:
    - List available projects: `python3 chatgpt-playwright/scripts/get_image_prompts.py --list`
    - Process all: `python3 chatgpt-playwright/scripts/get_image_prompts.py --all`

- Stage 3 — Image Generation (Playwright)
  - Reads prompts from env or `projects/<project>/prompts.json`, opens ChatGPT, sends each prompt, waits for images to render, saves them, and records run status.
  - Typical run: `PROJECT=<project_name> npx ts-node chatgpt-playwright/generateImageLoop_resilient.ts`
  - Environment/CLI:
    - `PROJECT` or `--project <name>` — project name; default `default`
    - `PROMPTS` — JSON array of prompts to run instead of reading file (optional)
    - `KEEP_OPEN=true` — reopen and hold a browser session after completion
  - Output:
    - `chatgpt-playwright/artifacts/<project>/genNNN_*.{png|jpg|webp|gif}` — saved images or screenshot fallback
    - `chatgpt-playwright/runs/<project>/status.json` — prompt‑wise status and outputs
    - `chatgpt-playwright/runs/<project>/send_prompts.json` — sent‑prompt ledger to skip duplicates

- Convenience wrapper — Prompts → Images
  - `bash chatgpt-playwright/pipeline.sh <project_name>`
    - Extract prompts and then run the Playwright operator for that project

**Current Script Notes**
- `scene_voice_generator.py` also triggers `generate_combined_subtitles` to create the final `.srt`, then copies the full output directory to `edit/` next to the original `sub.json`.
- `chatgpt-playwright/scripts/get_image_prompts.py` currently assumes base path `.../voicevox` on your machine. See Configuration to make this portable.
- `generateImageLoop_resilient.ts` maintains idempotency by skipping prompts that already succeeded or were sent previously.

**Configuration**
- Minimal env vars (supported now by scripts):
  - `PROJECT` — project folder under `chatgpt-playwright/projects/`
  - `PROMPTS` — JSON array of prompts (overrides file)
  - `KEEP_OPEN` — `true` to hold a browser open at the end
- VOICEVOX settings (CLI flags today):
  - `--host`, `--port`, `--speaker_id`, `--speed_scale`, `--silence_duration`
- Proposed normalized config (not yet implemented):
  - `.env` at repo root for quick overrides
  - `config.yaml` at repo root for durable defaults
  - Example `config.yaml`:
    - `paths.base`: absolute root, e.g., `.../voicevox` (used by prompt extractor)
    - `paths.prompts_root`: `chatgpt-playwright/projects`
    - `voicevox.host`: `127.0.0.1`
    - `voicevox.port`: `50021`
    - `voicevox.speaker_id`: `13`
    - `audio.speed_scale`: `1.15`
    - `audio.silence_duration`: `0.5`
    - `playwright.user_data_dir`: `chatgpt-playwright/.user-data`
    - `logging.level`: `INFO`

**Run Each Stage Independently**
- Audio only: `python3 scene_voice_generator.py --json_path <sub.json> --output_dir <out_dir> --skip_voice_generation` (generate only subtitles if audio already exists)
- Subtitles only: `python3 scene_subtitle_generator.py --base_dir <out_dir> --output_filename <file.srt>`
- Prompts only: `python3 chatgpt-playwright/scripts/get_image_prompts.py <project>`
- Images only: `PROJECT=<project> npx ts-node chatgpt-playwright/generateImageLoop_resilient.ts`

**End‑to‑End Example**
- Prepare `sub.json` in `t_sozai/upload_movies/<project>/sub.json`
- Generate audio + subtitle:
  - `python3 scene_voice_generator.py --json_path t_sozai/upload_movies/<project>/sub.json --output_dir ./scene_outputs/<project>`
- Extract prompts: `python3 chatgpt-playwright/scripts/get_image_prompts.py <project>`
- Generate images: `cd chatgpt-playwright && PROJECT=<project> npx ts-node generateImageLoop_resilient.ts`
- Or use wrapper: `bash chatgpt-playwright/pipeline.sh <project>`

**Proposed Clean Architecture (spec, future refactor)**
- Goals: Keep behavior identical; separate concerns; typed interfaces; testable units; normalized config; consistent logging and errors.
- Top‑level layout (proposed):
  - `configs/` — `config.yaml`, `.env.example`
  - `src/python/`
    - `core/audio/` — text extraction, audio query shaping, WAV combining
    - `core/subtitles/` — segment extraction, timing analysis, SRT writer
    - `core/prompts/` — prompt extraction/deduplication from `sub.json`
    - `adapters/voicevox/` — VOICEVOX HTTP client
    - `cli/` — `audio.py`, `subtitles.py`, `prompts.py` wrappers (map 1:1 to today’s CLIs)
    - `types/` — scene and segment dataclasses/protocols
  - `src/ts/`
    - `imagegen/` — headless orchestration, status I/O, prompt loading
    - `adapters/playwright/` — selectors, waits, download helpers
    - `cli/` — `imagegen.ts` mapping to current resilient script
    - `types/` — RunStatus/RunItem/Config types
  - `scripts/` — pipeline glue (e.g., `pipeline.sh`, `pipeline.py`)
  - `tests/` — unit and light integration tests across Python/TS
  - `docs/` — architecture and operational notes
- Typed interfaces (spec excerpt):
  - Python
    - `Scene` dataclass: `title: str`, `contents: list[Content]`, `image_prompt?: str`
    - `Content` dataclass: `texts: list[str]`, `image_prompt?: str`
    - `SubtitleSegment` dataclass: `index:int, start:float, end:float, text:str, kana:str, kind:str`
    - `VoicevoxClient` protocol: `create_audio_query(text:str, speaker:int, host:str, port:int) -> dict`
  - TypeScript
    - `type ItemStatus = 'success' | 'failed'`
    - `interface RunItem { prompt: string; status: ItemStatus; attempt_count: number; started_at: string; finished_at: string; outputs?: string[]; last_error?: string; }`
    - `interface RunStatus { project: string; updated_at: string; items: RunItem[] }`
    - `interface ImageGenConfig { project: string; userDataDir: string; generationTimeoutMs: number; }`
- Backwards‑compat mapping:
  - `scene_voice_generator.py` → `src/python/cli/audio.py` (calls `core/audio` and `core/subtitles`)
  - `scene_subtitle_generator.py` → `src/python/cli/subtitles.py`
  - `get_image_prompts.py` → `src/python/cli/prompts.py`
  - `generateImageLoop_resilient.ts` → `src/ts/cli/imagegen.ts`
  - `pipeline.sh` → remains; add `pipeline.py` for Python‑only pipeline if desired

**Testing (plan)**
- Python (pytest):
  - `core/prompts`: extraction and de‑dup with sample `sub.json`
  - `core/subtitles`: timing mapping from sample `voice_query.json` fixtures
  - `core/audio`: WAV combine correctness (channels/rate, silence insertion)
- TypeScript (vitest or jest):
  - `imagegen`: prompt loader fallback logic; status append/merge; skip set composition
  - `adapters/playwright`: unit test pure helpers (URL selection, MIME → ext)

**Troubleshooting**
- No audio or HTTP  connection refused
  - Ensure VOICEVOX engine is running at `--host`/`--port`
- `sub.json not found` in prompt extractor
  - Update base path (see Configuration) or place file at `t_sozai/upload_movies/<project>/sub.json`
- Playwright cannot find composer / login required
  - Run `cd chatgpt-playwright && npx ts-node setupLogin.ts` and complete login
- Playwright images never appear / timeout
  - UI may have changed or rate limits apply; check `artifacts/error.*` and logs
- Missing browsers
  - Run `cd chatgpt-playwright && npx playwright install`
- Subtitle alignment assertions fail
  - `kana_text` may not match VOICEVOX moras; verify `scene_sub.json` enrichment and adjust text

**Operational Notes**
- Idempotent runs: The image generator skips prompts that succeeded or were already sent; clear `runs/<project>` to rerun all.
- Artifacts: Images saved under `chatgpt-playwright/artifacts/<project>` with numeric prefixes.
- Logs and status: See `chatgpt-playwright/runs/<project>/status.json` and `send_prompts.json`.

**Next Steps (to reach the proposed architecture)**
- Introduce `config.yaml` + `.env` and wire into existing CLIs without changing defaults
- Extract pure modules into `src/python/core` and `src/ts/imagegen`, keeping current commands intact
- Add tests and fixtures for prompt extraction and subtitle timing
- Stabilize Playwright selectors into adapter layer with retry/backoff utilities

**Credits**
- VOICEVOX for TTS
- Playwright for browser automation

