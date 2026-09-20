# ClipGauge v0.6.0 Native Product Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the v0.6.0 native creator contract without merging, tagging, or releasing.

**Architecture:** Keep Python as the source of truth for creator state. Store title overrides separately from pipeline checkpoints. Expose bounded JSON CLI operations through Tauri. Make Review consume those operations using stable clip and collection IDs. Keep collection rendering on the existing FFmpeg path.

**Tech Stack:** Python, pytest, TypeScript, React, Vitest, Rust, Tauri, serde_json, GitHub Actions.

**Spec:** `C:/Users/Pavithran R A/.codex/attachments/14f5e166-501d-4235-8de4-a4d731641471/pasted-text.txt`

## Global Constraints

- Work only on `feat/v060-capability-suite` and PR #53.
- Preserve baseline main `17197ee631db4a941786a3209e2d44fb51204635`.
- Do not merge, tag, release, or rewrite history.
- Never mutate score, enrich, or other deterministic checkpoints for creator edits.
- Use stable clip IDs and collection IDs exclusively.
- Keep private grouping local and honor the job provider snapshot.
- Never send full source media to collection grouping.
- Keep Bilibili best-effort and bypass-free.
- Treat RSS and page-count telemetry as optional diagnostics.

## Review Focus

- A blank or oversized title must fail without changing stored state; test title validation.
- A stale or invented clip ID must fail before JSON mutation; test every creator mutation boundary.
- A malformed provider grouping must fall back truthfully; test source labeling and membership rejection.
- A user-edited collection must survive regeneration; test manual preservation.
- Historical jobs without creator files must remain readable; test absent override and category fallback.

---

### Task 1: Title Override State And Results Overlay

**Files:**
- Create: `pipeline/clipgauge_pipeline/creator_state.py`
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `app/src-tauri/src/artifact.rs`
- Modify: `app/src/types.ts`
- Test: `pipeline/tests/test_creator_state.py`
- Test: `app/src-tauri/src/artifact.rs` unit tests

**Interfaces:**
- Produces `load_title_overrides(job)`, `set_title_override(job, clip_id, title, clips)`, and `reset_title_override(job, clip_id)`.
- Produces `creator-overrides.json` with schema version `1`.
- Produces result title precedence: user, model, deterministic.

- [ ] **Step 1: Write failing Python tests.**

```python
def test_title_override_is_atomic_and_unicode(tmp_path):
    job = make_job(tmp_path)
    clip_id = stable_clip_id({"start": 0, "end": 5}, 0)
    set_title_override(job, clip_id, "  Café — Résumé  ", [clip(0, 5)])
    assert load_title_overrides(job)["clips"][clip_id]["title"] == "Café — Résumé"
    assert not list(job.dir.glob(".creator-overrides.json.*.tmp"))

def test_invalid_title_and_unknown_clip_are_rejected(tmp_path):
    job = make_job(tmp_path)
    with pytest.raises(ValueError, match="title"):
        set_title_override(job, "clip-missing", "", [clip(0, 5)])
    with pytest.raises(ValueError, match="title length"):
        set_title_override(job, stable_clip_id(clip(0, 5), 0), "x" * 121, [clip(0, 5)])

def test_reset_removes_only_override(tmp_path):
    job = make_job(tmp_path)
    clip_id = stable_clip_id(clip(0, 5), 0)
    set_title_override(job, clip_id, "Edited", [clip(0, 5)])
    reset_title_override(job, clip_id)
    assert load_title_overrides(job)["clips"] == {}
```

- [ ] **Step 2: Run tests and verify expected RED.**

Run: `uv run --directory pipeline pytest -q tests/test_creator_state.py`
Expected: FAIL because title override APIs are absent.

- [ ] **Step 3: Implement atomic title state.**

```python
CREATOR_OVERRIDE_SCHEMA_VERSION = 1
TITLE_LIMIT = 120

def set_title_override(job, clip_id, title, clips):
    normalized = " ".join(str(title).split())
    if not normalized:
        raise ValueError("title cannot be blank")
    if len(normalized) > TITLE_LIMIT:
        raise ValueError("title length exceeds 120 characters")
    valid_ids = {stable_clip_id(item, index) for index, item in enumerate(clips)}
    if clip_id not in valid_ids:
        raise ValueError("unknown clip ID")
    value = load_title_overrides(job)
    value["clips"][clip_id] = {"title": normalized, "updated_at": datetime.now(timezone.utc).isoformat()}
    _atomic_write_json(job.dir / "creator-overrides.json", value)
    return value["clips"][clip_id]
```

- [ ] **Step 4: Run focused tests and verify GREEN.**

Run: `uv run --directory pipeline pytest -q tests/test_creator_state.py`
Expected: all title state tests pass.

- [ ] **Step 5: Add result overlay tests, then implement overlay.**

```rust
#[test]
fn job_results_applies_creator_title_without_changing_checkpoint() {
    // Fixture writes score, enrich, creator-overrides, and render files.
    // Assert returned score title is user text and score file bytes are unchanged.
}
```

Apply overrides in `artifact::job_results` after score/enrich merge. Set `title_source` to `user`. Do not write score or enrich files.

- [ ] **Step 6: Run Rust focused tests.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml artifact::tests`
Expected: overlay tests pass.

- [ ] **Step 7: Commit the independently testable title state.**

```text
git add pipeline/clipgauge_pipeline/creator_state.py pipeline/clipgauge_pipeline/cli.py pipeline/tests/test_creator_state.py app/src-tauri/src/artifact.rs app/src/types.ts
git commit -m "feat: persist creator title overrides"
```

### Task 2: Smart Grouping And Collection State Contract

**Files:**
- Modify: `pipeline/clipgauge_pipeline/collections/model.py`
- Modify: `pipeline/clipgauge_pipeline/collections/service.py`
- Modify: `pipeline/clipgauge_pipeline/collections/stage.py`
- Create: `pipeline/clipgauge_pipeline/collections/smart.py`
- Test: `pipeline/tests/test_collections.py`
- Test: `pipeline/tests/test_smart_collections.py`

**Interfaces:**
- Produces `regenerate_smart_collections(job, clips, category, group_provider)`.
- Accepts bounded finalist metadata only.
- Returns `source="ai"` only after validated provider grouping.
- Returns `source="deterministic"` after provider failure or malformed output.

- [ ] **Step 1: Write failing grouping tests.**

```python
def test_provider_groups_two_finalists_with_stable_ids(tmp_path):
    job = make_job(tmp_path)
    clips = [clip(0, 5, "payments"), clip(8, 12, "refunds"), clip(15, 20, "unrelated")]
    result = regenerate_smart_collections(
        job, clips, "knowledge",
        lambda prompt, schema: {"collections": [{"title": "Money lessons", "summary": "", "clip_ids": [stable_clip_id(clips[1], 1), stable_clip_id(clips[0], 0)]}]},
    )
    assert result[0]["source"] == "ai"
    assert result[0]["clip_ids"] == [stable_clip_id(clips[0], 0), stable_clip_id(clips[1], 1)]

def test_malformed_provider_membership_uses_truthful_fallback(tmp_path):
    result = regenerate_smart_collections(job, clips, "auto", lambda *_: {"collections": [{"clip_ids": ["clip-nope"]}]})
    assert result[0]["source"] == "deterministic"

def test_manual_collections_survive_regeneration(tmp_path):
    manual = create_collection(job, "My series", ids, clips=clips)
    result = regenerate_smart_collections(job, clips, "auto", lambda *_: {"collections": []})
    assert result[0]["id"] == manual["id"]
```

- [ ] **Step 2: Run grouping tests and verify RED.**

Run: `uv run --directory pipeline pytest -q tests/test_collections.py tests/test_smart_collections.py`
Expected: FAIL because provider grouping and truthful fallback are absent.

- [ ] **Step 3: Implement bounded validation and provider grouping.**

Use a strict schema with `collections`, title and summary limits, maximum eight groups, minimum two clips per group, no duplicates, and stable finalist ordering. Build prompts from clip IDs, title, description, premise, category, score, and platform. Pass only the configured provider snapshot to `make_adapter`.

- [ ] **Step 4: Implement manual collection validation.**

Require at least two valid stable clip IDs. Validate title length and whitespace. Raise typed `ValueError` for unknown IDs, duplicate IDs, missing collections, and invalid reorder requests. Preserve only manual/user-edited collections during regeneration.

- [ ] **Step 5: Run focused grouping tests and verify GREEN.**

Run: `uv run --directory pipeline pytest -q tests/test_collections.py tests/test_smart_collections.py`
Expected: all grouping and lifecycle tests pass.

- [ ] **Step 6: Commit the collection contract.**

```text
git add pipeline/clipgauge_pipeline/collections pipeline/tests/test_collections.py pipeline/tests/test_smart_collections.py
git commit -m "feat: add truthful smart collection grouping"
```

### Task 3: Canonical CLI And Tauri Creator Bridge

**Files:**
- Modify: `pipeline/clipgauge_pipeline/cli.py`
- Modify: `app/src-tauri/src/main.rs`
- Modify: `app/src/api.ts`
- Modify: `app/src/types.ts`
- Test: `pipeline/tests/test_cli.py`
- Test: `app/src-tauri/src/main.rs` unit tests

**Interfaces:**
- CLI verbs: `title get/set/reset` and `collections list/create/update/delete/regenerate/reorder/render`.
- Tauri commands wrap the same CLI verbs.
- JSON responses contain `{ "ok": true, ... }` or bounded typed errors.

- [ ] **Step 1: Write failing CLI tests.**

```python
def test_title_set_cli_returns_json(tmp_path, capsys):
    assert main(["title", "set", job.id, clip_id, "My title"]) == 0
    assert json.loads(capsys.readouterr().out)["title_source"] == "user"

def test_collection_create_cli_requires_two_clips(tmp_path, capsys):
    assert main(["collections", "create", job.id, "Series", clip_id]) == 2
    assert "at least two" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI tests and verify RED.**

Run: `uv run --directory pipeline pytest -q tests/test_cli.py -k "title or collection"`
Expected: FAIL because creator subcommands are absent.

- [ ] **Step 3: Implement canonical CLI handlers.**

Validate job IDs through `queue.get_job`, clip IDs through score/enrich data, and collection IDs through service methods. Use `--json` output for native callers. Keep all outputs inside the job directory. Never accept arbitrary filesystem paths.

- [ ] **Step 4: Add failing Rust bridge tests.**

```rust
#[test]
fn creator_arguments_reject_unknown_paths_and_invalid_ids() {
    assert!(validate_creator_job_id("20260920-000000-abcdef").is_ok());
    assert!(validate_creator_job_id("..\\escape").is_err());
}
```

- [ ] **Step 5: Implement Tauri bridge commands.**

Add title and collection commands that call one bounded `creator` sidecar helper. Add typed TypeScript interfaces and API methods. Redact sidecar stderr through existing diagnostics handling.

- [ ] **Step 6: Run bridge tests and commit.**

Run: `cargo test --manifest-path app/src-tauri/Cargo.toml`
Expected: all Rust tests pass.

```text
git add pipeline/clipgauge_pipeline/cli.py pipeline/tests/test_cli.py app/src-tauri/src/main.rs app/src/api.ts app/src/types.ts
git commit -m "feat: expose creator operations through native bridge"
```

### Task 4: Review Creator UX And Category Display

**Files:**
- Modify: `app/src/components/Review.tsx`
- Modify: `app/src/components/Review.test.tsx`
- Modify: `app/src/types.ts`
- Modify: `app/src/api.ts`
- Modify: `app/src/styles.css`

**Interfaces:**
- Review title editor uses stable `clip_id`.
- Collection cards use stable collection IDs and clip IDs.
- Category display reads persisted `enrich.category`, defaulting historical jobs to `auto`.

- [ ] **Step 1: Write failing frontend tests.**

```tsx
it('saves and resets a title without saving on cancel', async () => {
  render(<Review {...propsWithOneClip()} />)
  await user.click(screen.getByRole('button', { name: /edit title/i }))
  await user.clear(screen.getByRole('textbox', { name: /publishing title/i }))
  await user.type(screen.getByRole('textbox', { name: /publishing title/i }), 'Edited title')
  await user.click(screen.getByRole('button', { name: /^save$/i }))
  expect(api.setClipTitle).toHaveBeenCalledWith(jobId, clipId, 'Edited title')
  await user.click(screen.getByRole('button', { name: /reset to generated/i }))
  expect(api.resetClipTitle).toHaveBeenCalledWith(jobId, clipId)
})

it('creates a manual collection only after two clips are selected', async () => {
  render(<Review {...propsWithTwoClips()} />)
  await user.click(screen.getByRole('button', { name: /create collection/i }))
  expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled()
})
```

- [ ] **Step 2: Run frontend tests and verify RED.**

Run: `npm --prefix app test -- --run src/components/Review.test.tsx`
Expected: FAIL because creator controls are absent.

- [ ] **Step 3: Implement title editor.**

Show generated/model/deterministic source badges. Save only on explicit action. Keep cancel side-effect free. Show reset only for user overrides. Display typed errors and loading states.

- [ ] **Step 4: Implement collection cards and dialogs.**

Add create, regenerate, rename, add, remove, move up, move down, render, playback, and delete actions. Use checkboxes for finalists. Disable creation below two clips. Show source, count, ordered titles, render state, and errors.

- [ ] **Step 5: Implement category display.**

Render `Content type · Knowledge` from persisted category. Use `Auto` for historical jobs lacking category data.

- [ ] **Step 6: Run frontend tests and build.**

Run: `npm --prefix app test -- --run src/components/Review.test.tsx && npm --prefix app run build`
Expected: tests and production build pass.

- [ ] **Step 7: Commit the native Review surface.**

```text
git add app/src/components/Review.tsx app/src/components/Review.test.tsx app/src/types.ts app/src/api.ts app/src/styles.css
git commit -m "feat: complete native creator review controls"
```

### Task 5: Representative Non-Auto Qualification And Docker Review

**Files:**
- Modify: `.dockerignore` or `Dockerfile.headless` only if evidence proves safe.
- Modify: `docs/qa/v0.6.0-capability-suite-ledger.md`
- Test: existing relevant Python tests and Docker workflow.

- [ ] **Step 1: Add a controlled Knowledge enrichment test first.**

Use a fake structured provider and assert category `knowledge` appears in the enrichment prompt, then collection grouping receives the same category without changing score evidence.

- [ ] **Step 2: Run the new test and verify RED.**

Run: `uv run --directory pipeline pytest -q tests/test_enrichment.py tests/test_smart_collections.py -k knowledge`
Expected: FAIL until category propagation is asserted and grouping receives it.

- [ ] **Step 3: Implement only the smallest category propagation correction.**

Preserve the persisted settings category through enrich, grouping, and Review. Do not rerun full expensive category coverage.

- [ ] **Step 4: Verify the Docker dependency tree.**

Run: `docker build -f Dockerfile.headless -t clipgauge-headless:qualification .` and inspect installed torch packages. Change to CPU-only wheels only if ASR imports and controlled tests remain valid.

- [ ] **Step 5: Run Docker regression checks if changed.**

Run: `docker run --rm clipgauge-headless:qualification python -c "import torch, torchaudio, whisperx; print(torch.__version__)"`
Expected: imports pass and image size is recorded before and after.

- [ ] **Step 6: Record qualification evidence.**

Update the ledger with category, provider locality, grouping source, Docker size, and Bilibili best-effort status. Do not claim release authorization.

### Task 6: Full Verification And Exact-Head Remote Qualification

**Files:**
- Modify: `docs/qa/v0.6.0-capability-suite-ledger.md`
- Modify: PR #53 body through GitHub CLI.

- [ ] **Step 1: Run complete local verification.**

Run Python, frontend, build, Rust, fmt, clippy, npm audit, pip-audit, cargo audit, and secret scan. Read each result.

- [ ] **Step 2: Run native Windows qualification at `AppliedDPI=120`.**

Exercise title, collection, category, render, playback, restart, long text, keyboard, and overflow controls. Capture only real evidence.

- [ ] **Step 3: Push the same branch.**

```text
git push origin feat/v060-capability-suite
```

- [ ] **Step 4: Wait for exact-head CI, Secret Scan, Windows, and macOS checks.**

Use bounded polling. Do not rerun speculative jobs.

- [ ] **Step 5: Update PR #53 body with exact head and truthful status.**

Remove obsolete unavailable-feature claims only after native evidence passes. Keep Bilibili environmentally unverified if still blocked.

- [ ] **Step 6: Verify no merge, tag, or release occurred.**

Confirm PR remains open, branch head matches, main and v0.5.22 remain unchanged, and v0.6.0 remains untagged.

---

## Self-Review Checklist

- [ ] Every promised native feature maps to a task.
- [ ] Every new production API has a failing test first.
- [ ] Title overrides never mutate deterministic checkpoints.
- [ ] Smart grouping never labels fallback as AI.
- [ ] Provider locality follows job settings.
- [ ] Stable IDs replace array-position mutation.
- [ ] Historical jobs remain readable.
- [ ] Docker optimization never changes Windows CUDA behavior.
- [ ] Bilibili remains bypass-free and best-effort.
- [ ] Final report remains PARTIAL until every release gate passes.
