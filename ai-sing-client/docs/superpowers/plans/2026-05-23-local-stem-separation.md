# Local Stem Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a client-only Demucs tool page that separates a local song into vocals and accompaniment, attempts GPU first with CPU fallback, and previews either output.

**Architecture:** Introduce a UI-independent `StemSeparator` service that runs Demucs as a subprocess and returns resolved output stems. A new PySide6 page owns a worker thread and preview player, while the existing top-level page container gains only navigation wiring. The FastAPI client and task queue remain untouched.

**Tech Stack:** Python 3.11, PySide6, Demucs CLI, PyTorch CUDA runtime, `sounddevice`/`soundfile`, pytest.

**Workspace Note:** `client/aising_client/ui/jobs.py` and `client/aising_client/api.py` already contain uncommitted user work. Implement in the current workspace, preserve those edits, and do not create an automatic implementation commit that would absorb unrelated changes.

---

## File Map

- Create `client/aising_client/audio/separator.py`: local Demucs execution, device fallback, result discovery.
- Create `client/aising_client/ui/separator.py`: page widgets, background worker, stem preview, output-folder action.
- Modify `client/aising_client/ui/jobs.py`: add the third page and navigation button only.
- Create `tests/client/test_separator.py`: service command and fallback tests.
- Create `tests/client/test_separator_widget.py`: initial UI-state and navigation integration tests.
- Create `client/requirements-gpu.txt`: CUDA PyTorch packages.
- Modify `client/requirements.txt`: add Demucs while keeping ordinary packages on the Tsinghua index.
- Modify `client/environment.yml`: install the GPU requirements before normal requirements.
- Modify `client/README.md`: install and run instructions plus local separation behavior.

### Task 1: Demucs Separation Service

**Files:**
- Create: `client/aising_client/audio/separator.py`
- Create: `tests/client/test_separator.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/client/test_separator.py`:

```python
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from aising_client.audio.separator import SeparationError, StemSeparator


def create_stems(root: Path, song: Path) -> None:
    target = root / "htdemucs" / song.stem
    target.mkdir(parents=True)
    (target / "vocals.wav").write_bytes(b"voice")
    (target / "no_vocals.wav").write_bytes(b"music")


def test_build_command_selects_requested_demucs_device(tmp_path):
    separator = StemSeparator(python_executable="python")
    song = tmp_path / "demo.wav"

    assert separator.build_command(song, tmp_path / "out", "cuda") == [
        "python",
        "-m",
        "demucs",
        "--two-stems=vocals",
        "--device",
        "cuda",
        "--out",
        str(tmp_path / "out"),
        str(song),
    ]


def test_separate_uses_gpu_when_available(tmp_path):
    song = tmp_path / "demo.wav"
    song.write_bytes(b"song")
    output = tmp_path / "result"
    calls = []

    def runner(command, on_log):
        calls.append(command)
        create_stems(output, song)
        return CompletedProcess(command, 0, "finished", "")

    separator = StemSeparator(cuda_available=lambda: True, runner=runner)
    result = separator.separate(song, output)

    assert calls[0][calls[0].index("--device") + 1] == "cuda"
    assert result.device == "cuda"
    assert result.vocals.name == "vocals.wav"
    assert result.accompaniment.name == "no_vocals.wav"


def test_failed_gpu_attempt_retries_on_cpu(tmp_path):
    song = tmp_path / "demo.wav"
    song.write_bytes(b"song")
    output = tmp_path / "result"
    devices = []

    def runner(command, on_log):
        device = command[command.index("--device") + 1]
        devices.append(device)
        if device == "cuda":
            return CompletedProcess(command, 1, "", "cuda unavailable")
        create_stems(output, song)
        return CompletedProcess(command, 0, "finished", "")

    separator = StemSeparator(cuda_available=lambda: True, runner=runner)
    result = separator.separate(song, output)

    assert devices == ["cuda", "cpu"]
    assert result.device == "cpu"


def test_missing_output_stems_raises_clear_error(tmp_path):
    song = tmp_path / "demo.wav"
    song.write_bytes(b"song")
    separator = StemSeparator(
        cuda_available=lambda: False,
        runner=lambda command, on_log: CompletedProcess(command, 0, "", ""),
    )

    with pytest.raises(SeparationError, match="vocals.wav"):
        separator.separate(song, tmp_path / "result")
```

- [ ] **Step 2: Run the tests and observe the missing service failure**

Run from the project root:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client\test_separator.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'aising_client.audio.separator'`.

- [ ] **Step 3: Implement the service**

Create `client/aising_client/audio/separator.py`:

```python
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SeparationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeparationResult:
    input_path: Path
    output_dir: Path
    vocals: Path
    accompaniment: Path
    device: str


Runner = Callable[[list[str], Callable[[str], None]], subprocess.CompletedProcess[str]]


class StemSeparator:
    def __init__(
        self,
        python_executable: str = sys.executable,
        cuda_available: Callable[[], bool] | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.python_executable = python_executable
        self.cuda_available = cuda_available or self._cuda_available
        self.runner = runner or self._run_command

    def build_command(self, input_path: Path, output_dir: Path, device: str) -> list[str]:
        return [
            self.python_executable,
            "-m",
            "demucs",
            "--two-stems=vocals",
            "--device",
            device,
            "--out",
            str(output_dir),
            str(input_path),
        ]

    def separate(
        self,
        input_path: Path,
        output_dir: Path,
        on_log: Callable[[str], None] | None = None,
    ) -> SeparationResult:
        log = on_log or (lambda message: None)
        source = Path(input_path)
        if not source.is_file():
            raise SeparationError(f"Input audio file does not exist: {source}")
        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        devices = ["cuda", "cpu"] if self.cuda_available() else ["cpu"]
        last_error = ""
        for device in devices:
            log(f"Running local separation on {device.upper()}.")
            result = self.runner(self.build_command(source, target, device), log)
            if result.returncode == 0:
                vocals, accompaniment = self._find_stems(target)
                return SeparationResult(source, target, vocals, accompaniment, device)
            last_error = result.stderr or result.stdout or f"Demucs exited with {result.returncode}."
            log(last_error.strip())
            if device == "cuda" and "cpu" in devices:
                log("GPU separation failed. Retrying on CPU.")
        raise SeparationError(last_error or "Local separation failed.")

    def _find_stems(self, output_dir: Path) -> tuple[Path, Path]:
        vocals = next(output_dir.rglob("vocals.wav"), None)
        accompaniment = next(output_dir.rglob("no_vocals.wav"), None)
        if vocals is None or accompaniment is None:
            raise SeparationError("Demucs completed but vocals.wav or no_vocals.wav is missing.")
        return vocals, accompaniment

    def _cuda_available(self) -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except ImportError:
            return False

    def _run_command(
        self,
        command: list[str],
        on_log: Callable[[str], None],
    ) -> subprocess.CompletedProcess[str]:
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        for line in (process.stdout + "\n" + process.stderr).splitlines():
            if line.strip():
                on_log(line)
        return process
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client\test_separator.py -v
```

Expected: `4 passed`.

### Task 2: Local Separation Page And Worker

**Files:**
- Create: `client/aising_client/ui/separator.py`
- Create: `tests/client/test_separator_widget.py`

- [ ] **Step 1: Write failing widget-state test**

Create `tests/client/test_separator_widget.py`:

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from aising_client.ui.separator import LocalSeparationWidget


def test_local_separator_disables_preview_until_results_exist():
    app = QApplication.instance() or QApplication([])
    widget = LocalSeparationWidget()

    assert not widget.play_vocals_button.isEnabled()
    assert not widget.play_accompaniment_button.isEnabled()
    assert not widget.open_output_button.isEnabled()

    widget.deleteLater()
    app.processEvents()
```

- [ ] **Step 2: Run test to confirm the missing widget failure**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client\test_separator_widget.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'aising_client.ui.separator'`.

- [ ] **Step 3: Implement the worker and page**

Create `client/aising_client/ui/separator.py` with these public classes and controls:

```python
from pathlib import Path
from subprocess import Popen

from PySide6.QtCore import QObject, QThread, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from aising_client.audio.engine import PlaybackEngine
from aising_client.audio.separator import SeparationResult, StemSeparator


class SeparationWorker(QObject):
    log = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, input_path: Path, output_dir: Path) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir

    @Slot()
    def run(self) -> None:
        try:
            result = StemSeparator().separate(self.input_path, self.output_dir, self.log.emit)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class LocalSeparationWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.input_path: Path | None = None
        self.output_dir = Path("data/local_separation")
        self.result: SeparationResult | None = None
        self.engine = PlaybackEngine()
        self.thread: QThread | None = None
        self.worker: SeparationWorker | None = None

        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        self.output_edit = QLineEdit(str(self.output_dir))
        self.output_edit.setReadOnly(True)
        self.status = QLabel("请选择歌曲文件。")
        self.status.setObjectName("SubtleText")
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMinimumHeight(160)

        self.select_input_button = QPushButton("选择歌曲")
        self.select_output_button = QPushButton("选择输出目录")
        self.start_button = QPushButton("开始分离")
        self.start_button.setObjectName("PrimaryButton")
        self.play_vocals_button = QPushButton("试听人声")
        self.play_accompaniment_button = QPushButton("试听伴奏")
        self.stop_button = QPushButton("停止试听")
        self.open_output_button = QPushButton("打开输出目录")

        self.select_input_button.clicked.connect(self.choose_input)
        self.select_output_button.clicked.connect(self.choose_output)
        self.start_button.clicked.connect(self.start_separation)
        self.play_vocals_button.clicked.connect(lambda: self.play_stem("vocals"))
        self.play_accompaniment_button.clicked.connect(lambda: self.play_stem("accompaniment"))
        self.stop_button.clicked.connect(self.engine.stop)
        self.open_output_button.clicked.connect(self.open_output)
        self.set_results_enabled(False)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        title = QLabel("本地人声分离")
        title.setObjectName("SectionTitle")
        panel_layout.addWidget(title)
        panel_layout.addLayout(self._path_row(self.input_edit, self.select_input_button))
        panel_layout.addLayout(self._path_row(self.output_edit, self.select_output_button))
        controls = QHBoxLayout()
        controls.addWidget(self.start_button)
        controls.addWidget(self.open_output_button)
        controls.addStretch()
        panel_layout.addLayout(controls)
        panel_layout.addWidget(self.status)
        panel_layout.addWidget(self.logs)
        preview = QHBoxLayout()
        preview.addWidget(self.play_vocals_button)
        preview.addWidget(self.play_accompaniment_button)
        preview.addWidget(self.stop_button)
        preview.addStretch()
        panel_layout.addLayout(preview)
        layout = QVBoxLayout(self)
        layout.addWidget(panel)

    def _path_row(self, edit: QLineEdit, button: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(edit, 1)
        row.addWidget(button)
        return row

    def choose_input(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择歌曲", "", "Audio Files (*.wav *.mp3 *.flac *.m4a);;All Files (*)"
        )
        if filename:
            self.input_path = Path(filename)
            self.input_edit.setText(filename)

    def choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录", str(self.output_dir))
        if folder:
            self.output_dir = Path(folder)
            self.output_edit.setText(folder)

    def start_separation(self) -> None:
        if self.input_path is None:
            self.status.setText("请先选择歌曲文件。")
            return
        self.logs.clear()
        self.set_results_enabled(False)
        self.start_button.setEnabled(False)
        self.status.setText("正在本地分离音轨...")
        self.thread = QThread(self)
        self.worker = SeparationWorker(self.input_path, self.output_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(lambda: self.start_button.setEnabled(True))
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_completed(self, result: SeparationResult) -> None:
        self.result = result
        self.status.setText(f"分离完成，使用设备: {result.device.upper()}")
        self.set_results_enabled(True)

    def on_failed(self, message: str) -> None:
        self.status.setText(f"分离失败: {message}")

    def set_results_enabled(self, enabled: bool) -> None:
        self.play_vocals_button.setEnabled(enabled)
        self.play_accompaniment_button.setEnabled(enabled)
        self.open_output_button.setEnabled(enabled)

    def play_stem(self, stem: str) -> None:
        if self.result is None:
            return
        self.engine.stop()
        target = self.result.vocals if stem == "vocals" else self.result.accompaniment
        self.engine.load(target)
        self.engine.start()

    def open_output(self) -> None:
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.output_dir.resolve())))
```

Before committing implementation, remove unused imports such as `Popen` if not used by the final file.

- [ ] **Step 4: Run widget test**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client\test_separator_widget.py -v
```

Expected: `1 passed`.

### Task 3: Add Top-Level Navigation

**Files:**
- Modify: `client/aising_client/ui/jobs.py`
- Modify: `tests/client/test_separator_widget.py`

- [ ] **Step 1: Add failing navigation test**

Append to `tests/client/test_separator_widget.py`:

```python
from aising_client.ui.jobs import JobsWidget


class FakeApi:
    def list_jobs(self, user_id):
        return []


def test_jobs_widget_can_open_local_separation_page():
    app = QApplication.instance() or QApplication([])
    widget = JobsWidget(FakeApi(), {"user_id": 1, "username": "demo"}, lambda: "light")

    widget.show_separator()

    assert widget.stack.currentWidget() is widget.separator
    assert widget.separator_button.isChecked()

    widget.deleteLater()
    app.processEvents()
```

- [ ] **Step 2: Run the navigation test to observe missing wiring**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client\test_separator_widget.py::test_jobs_widget_can_open_local_separation_page -v
```

Expected: FAIL because `JobsWidget` has no `show_separator` method.

- [ ] **Step 3: Wire the page into the existing stack without discarding pending changes**

In `client/aising_client/ui/jobs.py`:

```python
from aising_client.ui.separator import LocalSeparationWidget
```

After `self.tasks` is created:

```python
self.separator = LocalSeparationWidget()
self.stack.addWidget(self.separator)
```

After `self.tasks_button` setup:

```python
self.separator_button = QPushButton("本地分离")
self.separator_button.setCheckable(True)
self.separator_button.clicked.connect(self.show_separator)
```

Add it to `header` immediately after `self.tasks_button`:

```python
header.addWidget(self.separator_button)
```

Update existing page switches and add:

```python
def show_playback(self) -> None:
    self.stack.setCurrentWidget(self.playback)
    self.play_button.setChecked(True)
    self.tasks_button.setChecked(False)
    self.separator_button.setChecked(False)

def show_tasks(self) -> None:
    self.stack.setCurrentWidget(self.tasks)
    self.play_button.setChecked(False)
    self.tasks_button.setChecked(True)
    self.separator_button.setChecked(False)

def show_separator(self) -> None:
    self.stack.setCurrentWidget(self.separator)
    self.play_button.setChecked(False)
    self.tasks_button.setChecked(False)
    self.separator_button.setChecked(True)
```

Preserve all unrelated existing changes in `jobs.py`, including current server-task handling and any visible text fixes already in progress.

- [ ] **Step 4: Run client UI tests**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client -v
```

Expected: existing playback tests and new separator widget tests pass.

### Task 4: Installable Client Dependencies And Documentation

**Files:**
- Create: `client/requirements-gpu.txt`
- Modify: `client/requirements.txt`
- Modify: `client/environment.yml`
- Modify: `client/README.md`

- [ ] **Step 1: Add GPU dependency file**

Create `client/requirements-gpu.txt`:

```text
--index-url https://download.pytorch.org/whl/cu126
--trusted-host download.pytorch.org

torch==2.7.0
torchaudio==2.7.0
torchvision==0.22.0
```

- [ ] **Step 2: Add Demucs to normal client requirements**

Append to `client/requirements.txt`, which retains its Tsinghua index:

```text
demucs>=4.0.1
```

- [ ] **Step 3: Install GPU packages before normal client packages in Conda creation**

Change the pip block in `client/environment.yml` to:

```yaml
  - pip:
      - -r requirements-gpu.txt
      - -r requirements.txt
```

- [ ] **Step 4: Document the local tool setup and output**

Add to `client/README.md`:

```markdown
## Local Stem Separation

The `本地分离` page runs Demucs on the client computer only. It does not upload the selected song or create a server task.

The client environment installs CUDA-enabled PyTorch first and all remaining packages from the Tsinghua PyPI mirror. When CUDA is available, local separation uses the NVIDIA GPU; if GPU inference fails, the page retries on CPU.

Outputs are written under the chosen destination in Demucs folders and can be previewed from the page:

```text
vocals.wav
no_vocals.wav
```
```

- [ ] **Step 5: Verify dependency files are parsable and tests still pass**

Run:

```powershell
$env:PYTHONPATH='client'
.\.venv\Scripts\python.exe -m pytest tests\client -v
.\.venv\Scripts\python.exe -m compileall client\aising_client tests\client
```

Expected: all client tests pass and compilation completes without syntax errors.

### Task 5: Manual Desktop Verification

**Files:**
- No new files.

- [ ] **Step 1: Start the client from its Conda environment**

Run from `client/`:

```powershell
conda activate ai-sing-client
python -m aising_client.main
```

Expected: the login window opens, followed by a header containing `播放`, `任务与上传`, and `本地分离` after login.

- [ ] **Step 2: Verify local separation behavior**

Use a short local song and check:

```text
1. 本地分离 page accepts an audio file and output folder.
2. 开始分离 leaves the UI responsive while log lines appear.
3. Status reports GPU when CUDA succeeds, or CPU after an automatic fallback.
4. Successful output enables 试听人声, 试听伴奏, and 打开输出目录.
5. Neither server jobs nor the server upload API are invoked by this action.
```

- [ ] **Step 3: Review the dirty workspace before any commit**

Run:

```powershell
git -C client status --short
git -C client diff -- aising_client/ui/jobs.py aising_client/api.py
```

Expected: review confirms that pre-existing edits in `api.py` and `jobs.py` remain intact. Do not commit implementation changes automatically unless the user explicitly approves including the combined `jobs.py` changes.
