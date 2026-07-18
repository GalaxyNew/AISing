from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


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
                vocals, accompaniment = self._find_stems(target, source)
                return SeparationResult(source, vocals.parent, vocals, accompaniment, device)
            last_error = result.stderr or result.stdout or f"Demucs exited with {result.returncode}."
            log(last_error.strip())
            if device == "cuda" and len(devices) > 1:
                log("GPU separation failed. Retrying on CPU.")

        raise SeparationError(last_error or "Local separation failed.")

    def _find_stems(self, output_dir: Path, input_path: Path) -> tuple[Path, Path]:
        song_dir = output_dir / "htdemucs" / input_path.stem
        vocals = song_dir / "vocals.wav"
        accompaniment = song_dir / "no_vocals.wav"
        if not vocals.is_file() or not accompaniment.is_file():
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
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        lines: list[str] = []
        self._forward_output(process.stdout, lines, on_log)
        returncode = process.wait()
        output = "\n".join(lines)
        return subprocess.CompletedProcess(command, returncode, output, output if returncode else "")

    def _forward_output(
        self,
        output: TextIO | None,
        lines: list[str],
        on_log: Callable[[str], None],
    ) -> None:
        if output is None:
            return
        for raw_line in output:
            line = raw_line.rstrip()
            if line:
                lines.append(line)
                on_log(line)
