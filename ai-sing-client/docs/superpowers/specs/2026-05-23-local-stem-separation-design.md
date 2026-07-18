# Client Local Stem Separation Design

## Goal

Add a desktop-only vocal and accompaniment separation tool to the PySide6 client. The feature accepts a local song, processes it locally with Demucs, prefers NVIDIA GPU execution with automatic CPU fallback, and provides immediate playback of the two output stems.

## Scope

Included:

- A third top-level client page named `本地分离`, beside `播放` and `任务与上传`.
- Local file selection for an input song and an output directory.
- Background Demucs processing that does not call the FastAPI server or create database jobs.
- GPU-first execution with transparent CPU retry if GPU execution is unavailable or fails.
- Status and log feedback during separation.
- Playback controls for `vocals.wav` and `no_vocals.wav`.
- Opening the completed output directory in Windows Explorer.

Not included:

- Uploading locally separated stems to the server.
- Mixing stems into a new song.
- Feeding local stems directly into the live singing page.
- Installation of CUDA drivers or GPU runtime from inside the app.

## User Experience

After login, the header navigation contains three page buttons:

```text
播放 | 任务与上传 | 本地分离
```

The `本地分离` page is an operational tool surface with these regions:

1. Input selection: a file picker for audio files and a read-only selected path.
2. Output selection: a folder picker, defaulting to a client cache/output directory.
3. Action controls: `开始分离` and `打开输出目录`.
4. Processing status: selected execution device (`GPU` or `CPU`), current state, and compact log output.
5. Results: two fixed result rows for `人声 vocals.wav` and `伴奏 no_vocals.wav`, each with a play command, plus one shared stop command.

Controls for playback remain disabled until separation outputs exist. Processing controls are disabled while a separation task is active to prevent two model runs from colliding.

## Architecture

### Separation Service

Create `aising_client/audio/separator.py` as a UI-independent service. It owns:

- Building the Demucs command.
- Determining an output destination.
- Selecting initial device based on local CUDA visibility.
- Running Demucs in a subprocess.
- Retrying once on CPU when a GPU attempt fails.
- Discovering and returning the resulting stem paths.

Demucs runs through the active client Python environment:

```bash
python -m demucs --two-stems=vocals --device cuda --out <output_dir> <input_song>
```

On CPU fallback:

```bash
python -m demucs --two-stems=vocals --device cpu --out <output_dir> <input_song>
```

The service returns a structured result containing the input file, execution device ultimately used, `vocals.wav`, `no_vocals.wav`, and the output folder.

### Background Task

Create `aising_client/ui/separator.py` with a `QThread` worker or equivalent Qt worker object. The UI starts separation asynchronously so Demucs model loading and inference never freeze the main window. The worker emits:

- Device and state updates.
- Log text updates.
- A completed result.
- A user-facing failure message.

### Playback

The page uses one `PlaybackEngine` instance already established by the client audio layer. Selecting either result stops current local preview, loads the chosen stem, and begins output. A shared stop action terminates preview playback.

### Navigation Integration

Modify the existing container in `aising_client/ui/jobs.py` by adding:

- A `LocalSeparationWidget` instance to its `QStackedWidget`.
- A third checkable navigation button.
- A `show_separator()` page switch method.

Existing server task refresh behavior remains unchanged and continues to update only the server-backed playback and task pages.

## Dependency Strategy

The client adds Demucs and a CUDA-capable PyTorch installation appropriate for the Windows machine. Dependencies should be separated similarly to the server build configuration where useful:

- General client and Demucs packages use the existing Tsinghua PyPI source.
- CUDA-enabled PyTorch packages use the PyTorch CUDA wheel source.

If PyTorch does not see a CUDA device at runtime, the separation service uses CPU without blocking the feature.

## Error Handling

- Missing input file: show a local validation message before starting work.
- Demucs package unavailable: report that local separation dependencies need installation.
- CUDA attempt fails: log the GPU failure and automatically retry once on CPU.
- CPU retry fails: show the collected error output and leave result controls disabled.
- Demucs completes without expected stems: report missing `vocals.wav` or `no_vocals.wav` rather than implying completion.
- Playback failure: show a short local playback error without losing completed output paths.

## Testing

Add unit coverage for the non-visual separation service:

- GPU command construction includes `--device cuda`.
- CPU command construction includes `--device cpu`.
- A failed GPU execution retries through CPU and returns the CPU result.
- Stem discovery resolves Demucs standard `vocals.wav` and `no_vocals.wav` outputs.
- Missing stem output raises a clear error.

Add focused UI integration coverage only if the existing test setup can instantiate Qt widgets without substantial harness work. Manual verification should cover navigation, disabled/enabled states, progress display, stem playback, and opening the result folder.

## Acceptance Criteria

- The client provides a visible `本地分离` top-level page after login.
- A song can be selected and processed without any server API call.
- Separation does not freeze the UI.
- NVIDIA GPU is attempted first when available; CPU is used automatically when necessary.
- Completed output stems can be previewed separately and their folder can be opened.
- Existing playback and task/upload workflows continue to operate.
