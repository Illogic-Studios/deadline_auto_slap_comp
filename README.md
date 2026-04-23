# SlapComp
 
Automated Nuke slap comp generator for [Deadline](https://www.awsthinkbox.com/deadline) render jobs, designed for [Prism Pipeline](https://prism-pipeline.com/) projects.
 
SlapComp picks up completed render layers from a Deadline job or batch, assembles them into a Nuke script using a stack of `Merge2` nodes, and optionally submits the result back to Deadline as a dependent render job. It ships with an interactive Qt UI, a one-click automated mode, and an unattended nightly mode for batch processing.
 
---
 
## Table of Contents
 
- [Features](#features)
- [Architecture](#architecture)
- [Repository Layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Interactive Mode — `slapIt.py`](#interactive-mode--slapitpy)
  - [Auto Mode — `autoSlapIt.py`](#auto-mode--autoslapitpy)
  - [Nightly Mode — `NightAutoSlapComp.py`](#nightly-mode--nightautoslapcomppy)
- [Naming Conventions](#naming-conventions)
- [Prism Folder Structure](#prism-folder-structure)
- [Preset System](#preset-system)
- [Core API Reference](#core-api-reference)
- [Troubleshooting](#troubleshooting)
- [Extending the Tool](#extending-the-tool)
- [License](#license)
---
 
## Features
 
- **Auto-discovery of render layers** from Deadline jobs, Deadline batches, or directly from the Prism filesystem.
- **Combined completion tracking** for `_high_prio_render` + `_render` job pairs, with filesystem-verification fallback when Deadline's `JobCompletedTasks` is empty.
- **Interactive Qt UI** for selecting layers, versions, and merge operations, plus save/load of project and shot presets.
- **One-click auto mode** that picks the latest complete version of every layer and submits immediately.
- **Unattended nightly mode** that scans Deadline for jobs completed within a configurable time window and processes them in batch — ideal for overnight farm idle time.
- **Smart versioning** that auto-increments `v001 → v002 → …` based on existing scenefiles in the shot's `Scenefiles/Compo/SlapComp` directory.
- **Deadline dependencies** — the submitted Nuke job waits for any still-running source render jobs before starting.
- **Prism-aware paths** — outputs land in the canonical `Scenefiles/Compo/SlapComp/` and `Renders/2dRender/SlapComp/vXXX/` folders.
- **OCIO colorspace** configured via `path_config.ini` (studio ACES config by default).
---
 
## Architecture
 
```
┌──────────────────────────────────────────────────────────────────────┐
│                      ENTRY POINTS (Deadline scripts)                 │
│                                                                      │
│  slapIt.py             autoSlapIt.py          NightAutoSlapComp.py   │
│  (right-click +        (right-click,          (scheduled via .bat,   │
│   Qt dialog)            no UI)                 scans recent jobs)    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   SlapCompCore.py  (business logic)                  │
│                                                                      │
│  • Deadline job grouping     • Prism path parsing                    │
│  • Image sequence detection  • Nuke script generation                │
│  • Preset loading/saving     • Deadline submission                   │
│  • Completion aggregation    • Filesystem fallback                   │
└─────────────┬─────────────────────────────────┬──────────────────────┘
              │                                 │
              ▼                                 ▼
┌──────────────────────────┐      ┌────────────────────────────────────┐
│   SlapCompUI_Qt.py       │      │  SubmitSlapCompToDeadline.py       │
│   (Qt table dialog)      │      │  (writes .job files + runs         │
│                          │      │   deadlinecommand.exe)             │
└──────────────────────────┘      └────────────────────────────────────┘
```
 
**Data flow (interactive mode):**
 
1. User selects a job (or batch) in the Deadline Monitor and runs `slapIt.py`.
2. `SlapCompCore.get_output_dirs()` gathers render layers — first by walking the selected jobs and their batches, then by scanning the shot's `Renders/3dRender/` tree for any additional versions on disk.
3. The Qt dialog (`SlapCompUI_Qt.show_slap_comp_dialog`) lets the user include/exclude layers, pick versions, set merge operations, and apply presets.
4. `SlapCompCore.call_nuke_script()` builds a temporary Python script, launches Nuke in terminal mode (`-t`) to generate the `.nk`, and calls `submit_to_deadline()` with the source job IDs as dependencies.
5. `SubmitSlapCompToDeadline.submit_slap_comp_job()` writes the job info / plugin info files to temp and submits via `deadlinecommand.exe`.
---
 
## Repository Layout
 
When deployed into the Deadline Repository, the files are organised as follows:
 
```
<DeadlineRepository>/custom/
├── scripts/
│   ├── Jobs/
│   │   ├── slapIt.py                    # Interactive entry point
│   │   └── autoSlapIt.py                # Automated entry point
│   │
│   └── General/
│       ├── SlapCompCore.py              # Business logic (core module)
│       ├── SlapCompUI_Qt.py             # Qt dialog for interactive mode
│       ├── SlapCompUI.py                # Legacy (pre-Qt) dialog — kept for reference
│       ├── path_config.ini              # Studio paths (log dir, OCIO, fallback Nuke)
│       │
│       └── NightSlapComp/
│           ├── NightAutoSlapComp.py     # Nightly batch entry point
│           ├── NightSlapCompUI.py       # Config editor for nightly job
│           ├── config.json              # Time window + exclude lists
│           └── standaloneNightSlap.bat  # Scheduled-task wrapper
│
└── scripts/Submission/SlapComp/
    └── SubmitSlapCompToDeadline.py      # Deadline submitter for the Nuke job
```
 
> **Note.** The `.bat` file and `path_config.ini` are gitignored because they contain machine-specific paths and should be deployed per site.
 
---
 
## Prerequisites
 
| Component | Version | Notes |
|-----------|---------|-------|
| Deadline | 10.x | Repository must be accessible from all render workers |
| Nuke | 15.x | Path resolved from Deadline's Nuke plugin config or `FALLBACK_NUKE` in `path_config.ini` |
| Python | 3.x | Provided by Deadline's embedded Python |
| PySide2 or PyQt5 | — | The UI auto-detects both |
| Prism Pipeline | Any recent version | Used for folder structure conventions only; SlapComp has no runtime dependency on Prism |
| OCIO config | — | Path declared in `path_config.ini` |
 
---
 
## Installation
 
1. Copy the files from this repository into your Deadline Repository, preserving the layout shown in [Repository Layout](#repository-layout).
2. Create `path_config.ini` alongside `SlapCompCore.py` (see [Configuration](#configuration)).
3. Create `NightSlapComp/config.json` if you plan to use the nightly mode.
4. (Optional) Edit `standaloneNightSlap.bat` to match your Deadline install path, and register it in Windows Task Scheduler on a workstation that has `I:` and `R:` mapped.
5. Restart the Deadline Monitor — the scripts should now appear under **Scripts** in the right-click menu on jobs.
---
 
## Configuration
 
### `path_config.ini`
 
Studio-wide paths consumed by `SlapCompCore.get_file_path_from_config()`.
 
```ini
[DEFAULT]
LOG_DIR = Path/to/logDir
FALLBACK_NUKE = Pah/to/NukeXX.X.exe
OCIO = "Path/To/your_ocio_config.ocio"
```
 
| Key | Purpose |
|-----|---------|
| `LOG_DIR` | Destination for `SlapDependencyDebug<YYYYMMDD>.log`. If missing, logs only go to Deadline's console. |
| `FALLBACK_NUKE` | Used when the Nuke plugin's `RenderExecutable` can't be read from the Deadline Repository. |
| `OCIO` | Custom OCIO config path injected into the generated Nuke script. Keep the surrounding quotes — they end up verbatim in the `.nk` file. This field MUST be in quotes|
 
### `NightSlapComp/config.json`
 
Controls the nightly scan window and exclusions.
 
```json
{
    "min_time": 20,
    "max_time": 8,
    "project_exclude": [],
    "user_exclude": []
}
```
 
| Key | Meaning |
|-----|---------|
| `min_time` | Hour (0–23) at which the scan window **starts**. If `min_time >= max_time`, the window is interpreted as crossing midnight (yesterday's `min_time` → today's `max_time`). |
| `max_time` | Hour (0–23) at which the scan window **ends**. |
| `project_exclude` | Deadline `JobPool` names to skip. |
| `user_exclude` | Deadline `JobUserName` values to skip. |
 
The file can be edited directly or through the `NightSlapCompUI.py` dialog.
 
---
 
## Usage
 
### Interactive Mode — `slapIt.py`
 
1. Select one or more jobs (or a batch) in the Deadline Monitor.
2. **Right-click → Scripts → slapIt**.
3. The Qt dialog opens and displays every discovered layer with:
   - An **Include** checkbox
   - A **Version** dropdown (all versions found on disk or in Deadline)
   - A **Completion** indicator (percentage + color-coded progress bar)
   - A **Merge operation** dropdown (`over`, `plus`, `multiply`, `screen`, `under`, …)
4. Reorder layers with **Move Up / Move Down**, optionally **Load Preset**, then choose a render mode:
   - **Do not render** — write the `.nk` only
   - **Render locally** — launch Nuke in `-x` mode on the calling workstation
   - **Submit to Deadline** — create a dependent farm job (recommended)
5. Click **OK**. The tool auto-increments the version and writes:
   - `<shot>/Scenefiles/Compo/SlapComp/<seq>_<shot>_SlapComp_v###.nk`
   - `<shot>/Scenefiles/Compo/SlapComp/<seq>_<shot>_SlapComp_v###_versioninfo.json`
### Auto Mode — `autoSlapIt.py`
 
Identical entry point and selection logic as `slapIt.py`, but:
 
- No UI.
- Every layer is automatically included.
- The latest 100%-complete version of each layer is selected.
- Merge operation defaults to `over` (unless overridden by a preset).
- The job is always submitted to Deadline.
Use it when you trust the project preset and just want one click from job selection to a queued slap comp.
 
### Nightly Mode — `NightAutoSlapComp.py`
 
Runs unattended on a schedule. Two launch patterns:
 
**Manually via .bat file** — useful for manual triggering:

If you wish to add it to the monitor scripts, simply drag it out of the NightSlapComp directory.

```
Right-click in Monitor → Scripts → General → NightAutoSlapComp
```
 
**Via `standaloneNightSlap.bat`** — registered in Windows Task Scheduler:
```bat
"C:\Program Files\Thinkbox\Deadline10\bin\deadlinecommand.exe" ^
    -ExecuteScript "R:\...\NightSlapComp\NightAutoSlapComp.py"
```
 
The script:
 
1. Reads the time window from `config.json`.
2. Calls `RepositoryUtils.GetJobs(True)` and filters on `JobCompletedDateTime` falling inside the window.
3. Drops any job whose `JobUserName` or `JobPool` is in the exclude lists, and requires `JobComment` to contain `Prism-Submission-Python`.
4. For each remaining job, groups by batch, selects the latest complete versions, loads the appropriate preset (**skipping the slap comp if no preset is found**), and submits to Deadline.
All log output is tee'd to Deadline's console **and** to `LOG_DIR/SlapDependencyDebug<YYYYMMDD>.log`.
 
---
 
## Naming Conventions
 
> **Critical rule — dual naming system.**
> Scene and render filenames **do not** include the project name. The Deadline job name **does**.
 
| Artifact | Contains project? | Example |
|----------|-------------------|---------|
| `.nk` scenefile | ❌ | `CAPS03_SH0230_SlapComp_v001.nk` |
| Rendered `.exr` | ❌ | `CAPS03_SH0230_SlapComp_v001.0042.exr` |
| Deadline job name | ✅ | `VCA_Perlee_2510_CAPS03_SH0230_SlapComp_v001` |
| Deadline batch name | ✅ | `VCA_Perlee_2510_CAPS03_SH0230_SlapComp_v001` |
 
This is handled by `build_prism_slapcomp_paths()`, which returns both `base_name` (for files) and `job_name` (for Deadline).
 
---
 
## Prism Folder Structure
 
The tool expects (and produces) this layout:
 
```
I:/<PROJECT>/03_Production/Shots/<SEQUENCE>/<SHOT>/
├── Scenefiles/
│   └── Compo/
│       └── SlapComp/
│           ├── <SEQ>_<SHOT>_SlapComp_v001.nk
│           └── <SEQ>_<SHOT>_SlapComp_v001_versioninfo.json
└── Renders/
    ├── 3dRender/
    │   └── <LAYER>/
    │       └── v###/
    │           └── beauty/               # scanned recursively; also found at root
    │               └── *.exr
    └── 2dRender/
        └── SlapComp/
            └── v001/
                └── <SEQ>_<SHOT>_SlapComp_v001.%04d.exr
```
 
Prism metadata is extracted with two strategies, tried in order:
 
1. **Filesystem path** (preferred, fast, single regex). Matches `<drive>:/<project>/03_Production/Shots/<seq>/<shot>`.
2. **Job name fallback** (7 regex patterns). Used when the job's `JobOutputDirectories` is empty or doesn't follow Prism conventions.
See `extract_prism_from_filesystem_path()` and `extract_prism_from_job_name()`.
 
---
 
## Preset System
 
Presets let you freeze a layer order and per-layer merge operations per project, with optional shot-level overrides.
 
**Preset root:** `I:/<PROJECT>/00_Pipeline/Presets/SlapComp/`
 
```
SlapComp/
├── project_preset.json      # Default for every shot in the project
└── shot_overrides.json      # Shot-specific overrides (keyed "<SEQ>-<SHOT>")
```
 
### Format
 
```json
{
  "layer_order": ["BG", "CHARS", "FX", "VEGET"],
  "default_merge_ops": {
    "BG":    "over",
    "CHARS": "over",
    "FX":    "plus",
    "VEGET": "over"
  }
}
```
 
### Resolution order
 
1. `shot_overrides.json[<SEQ>-<SHOT>]` — if present
2. `project_preset.json` — fallback
### Behavior
 
- Layers listed in `layer_order` are **included** and reordered accordingly.
- Layers **not** in `layer_order` are appended **unchecked** by default (they still appear in the UI so you can opt them in manually).
- In nightly mode, **a shot with no matching preset is skipped entirely** — this prevents noisy comps with unpredictable layer stacks.
### Shot overrides file
 
```json
{
  "CAPS03-SH0230": {
    "layer_order": ["BG", "CHARS", "FX_RAIN"],
    "default_merge_ops": { "FX_RAIN": "plus" }
  },
  "CAPS03-SH0240": {
    "layer_order": ["BG", "CHARS"]
  }
}
```
 
---
 
## Core API Reference
 
Key entry points in `SlapCompCore.py`. All functions log through `addLog()`, which writes both to the Deadline console and (when `LOG_DIR` is configured) to a daily log file.
 
### Deadline integration
 
| Function | Purpose |
|----------|---------|
| `get_job_batch(batch_name)` | Return all jobs belonging to a Deadline batch. |
| `group_high_prio_and_render_jobs(jobs)` | Group `_high_prio_render` + `_render` siblings by `(base_name, version)` and discover **all** versions in Deadline for each base name. |
| `get_combined_frame_range(jobs)` | `(first, last)` covering every job in the group. |
| `get_combined_job_completion(jobs)` | Aggregated status / completion dict. Falls back to filesystem scan when Deadline reports 0 completed tasks on a "Completed" job. |
| `get_nuke_executable()` | Resolve Nuke path via Deadline's `Nuke.param`, or `FALLBACK_NUKE`. |
 
### Prism parsing
 
| Function | Purpose |
|----------|---------|
| `extract_prism_from_filesystem_path(path)` | Fast regex on a render folder path — the preferred strategy. |
| `extract_prism_from_job_name(job)` | 7-pattern fallback using `JobName` / `JobBatchName`. |
| `get_prism_info_smart(job, output_dirs)` | Wrapper: filesystem first, then job metadata. |
| `scan_prism_render_layers(project_root, seq, shot)` | List every `(layer, version)` pair on disk under `Renders/3dRender/`. |
| `build_prism_slapcomp_paths(...)` | Return `scenefile_dir`, `scenefile_path`, `render_dir`, `render_filename`, `job_name` — enforcing the dual naming rule. |
| `detect_department(shot_path)` | Returns `Compo`, `Comp`, `2D`, or `Compositing` based on what exists on disk (default `Compo`). |
 
### Image sequence detection
 
| Function | Purpose |
|----------|---------|
| `detect_image_sequence_info(directory)` | Scan a folder (and its one-level subfolders such as `beauty/`) for `.exr` sequences. Returns `pattern`, `first_frame`, `last_frame`, `total_frames`, and optional `subfolder`. |
 
### Output collection
 
| Function | Purpose |
|----------|---------|
| `get_output_dirs(jobs_to_process, filter_qc_layers=True)` | **Main entry point for discovery.** 3-pass algorithm: (1) collect Prism contexts, (2) process Deadline jobs, (3) augment with filesystem-only layers. Filters out layer names starting with `QC` by default. |
| `group_output_info_for_ui(output_info)` | Reshape the flat list into `{layer_name: {versions: [...], …}}` for the Qt dialog. |
 
### Nuke script generation & rendering
 
| Function | Purpose |
|----------|---------|
| `call_nuke_script(output_info, render_mode)` | **Main entry point for generation.** Resolves Prism info, auto-increments the version, builds a temp Python script, launches Nuke in `-t` mode to save the `.nk`, then optionally renders locally or submits to Deadline. `render_mode` ∈ `{"none", "local", "deadline"}`. |
| `render_nuke_script(nk, first, last)` | Run Nuke in `-x` mode on the local machine. |
| `submit_to_deadline(...)` | Collect source job IDs, deduplicate, and delegate to `SubmitSlapCompToDeadline.submit_slap_comp_job()`. |
| `find_next_slapcomp_version(scenefile_dir, base)` | Walk the scenefile folder and return the next free version integer. |
| `generate_versioninfo(...)` | Write a Prism-compatible `_versioninfo.json` next to the `.nk`. |
 
### Presets
 
| Function | Purpose |
|----------|---------|
| `load_preset(project, sequence, shot)` | Shot override → project preset → `None`. |
| `apply_preset_data(output_info, preset_data)` | Reorder + apply merge operations. Layers not in the preset are appended with `included=False`. |
| `save_preset_project(project, preset_data)` | Persist `project_preset.json`. |
| `save_preset_shot(project, sequence, shot, preset_data)` | Update `shot_overrides.json[<SEQ>-<SHOT>]`. |
 
### Automation helpers
 
| Function | Purpose |
|----------|---------|
| `select_latest_complete_versions(output_info)` | Per layer, pick the highest version that's 100% complete. Falls back to the latest incomplete version with a warning. |
 
---
 
## Troubleshooting
 
### Files saved to the wrong location
 
**Cause.** Prism info couldn't be extracted — the first element of `output_info` doesn't contain a recognisable `<project>/03_Production/Shots/<seq>/<shot>` path and the job-name fallback also failed.
 
**Check.** The first layer's `directory` field. The expected pattern is `<drive>:/<project>/03_Production/Shots/<SEQ>/<SHOT>/…`. When both strategies fail, the tool falls back to writing next to the source renders — useful for debugging but not for production.
 
### Completed jobs report 0% completion
 
**Cause.** Older Deadline jobs can have an empty `JobCompletedTasks` array even though `JobStatus == "Completed"`.
 
**Fix.** `get_combined_job_completion()` detects this case and re-scans the output directory with `detect_image_sequence_info()`. Look for this line in the log:
```
Jobs marked as Completed but 0/77 frames reported, checking filesystem...
```
 
### Deadline job dependencies not applied
 
**Cause.** `job_id` / `job_ids` didn't propagate through the pipeline.
 
**Check.** Both fields are populated in `group_output_info_for_ui()` and forwarded by `SlapCompUI_Qt.get_result()`. In `submit_to_deadline()`, the log line `Deps without dupes : […]` should show non-empty IDs. If it doesn't, the Deadline job will start immediately rather than waiting for sources.
 
### Nightly job skips everything
 
**Cause.** In nightly mode, **the job is skipped when no preset is found** for the shot. This is by design.
 
**Fix.** Either drop a `project_preset.json` in `I:/<PROJECT>/00_Pipeline/Presets/SlapComp/`, or add a shot override in `shot_overrides.json`.
 
### Preset not applied correctly
 
**Cause.** JSON format mismatch.
 
**Check.** `layer_order` is required; `default_merge_ops` is optional. Layer names in `layer_order` must match the layer names produced by `get_output_dirs()` (usually the folder name under `Renders/3dRender/`).
 
### Filename contains the project name
 
**Cause.** Code is using `job_name` where it should use `base_name`.
 
**Fix.** Use `paths["scenefile_path"]` and `paths["render_filename"]` from `build_prism_slapcomp_paths()` — never concatenate the project into file paths manually.
 
### `standaloneNightSlap.bat` fails with network drive errors
 
**Cause.** Mapped drives don't exist under the Scheduled Task's session.
 
**Fix.** Either run the task under the same user account that has `I:` and `R:` mapped, or uncomment the `net use` lines at the top of the `.bat` and use a UNC path in `SCRIPT_PATH`.
 
---
 
## Extending the Tool
 
### Adding a new layer name pattern
 
Edit `get_output_dirs()` in `SlapCompCore.py`, around the `layer_patterns` list (currently four patterns). Patterns use a `(regex, group_index)` tuple. Keep the most specific patterns first — the loop breaks on the first match.
 
### Adding a new merge operation
 
Add it to the `QComboBox` in `SlapCompUI_Qt.py::create_row()`. Every operation from Nuke's `Merge2` node is valid — the value is written straight into `merge.knob('operation').setValue(...)`.
 
### Changing the default colorspace
 
The OCIO config is set by the generated Nuke script via the value of `OCIO` in `path_config.ini`. To switch to Nuke's built-in management instead, edit the header of the generated script in `call_nuke_script()`:
 
```python
root.knob('colorManagement').setValue('Nuke')
root.knob('workingSpaceLUT').setValue('ACES - ACEScg')
```
 
## License
 
Internal studio tool — not currently licensed for external distribution.
 
---
 
*Maintained by the pipeline team.*