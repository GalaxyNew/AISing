import math
import logging
import shlex
import shutil
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.storage import StorageService


logger = logging.getLogger(__name__)


class PipelineConfigurationError(RuntimeError):
    pass


class PipelineExecutionError(RuntimeError):
    pass


def write_tone(path: Path, seconds: float = 3.0, frequency: float = 440.0) -> None:
    sample_rate = 44100
    frames = int(sample_rate * seconds)
    audio = bytearray()
    for i in range(frames):
        sample = int(16000 * math.sin(2 * math.pi * frequency * i / sample_rate))
        audio.extend(sample.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(audio))


class CommandTemplateRunner:
    def run(
        self,
        template: str,
        values: dict[str, str],
        output_callback: Callable[[str], None] | None = None,
    ) -> None:
        command = template.format(**values).strip()
        if not command:
            raise PipelineConfigurationError("Empty command template")
        logger.info("Running command: %s", command)
        process = subprocess.Popen(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        output: list[str] = []
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                output.append(line)
                logger.info("Command output: %s", line)
                if output_callback:
                    output_callback(line)
        returncode = process.wait()
        if returncode != 0:
            raise PipelineExecutionError(
                f"Command failed with exit code {returncode}: {command}\n" + "\n".join(output)
            )


class RealAudioPipelines:
    def __init__(
        self,
        storage: StorageService | None = None,
        settings: Settings | None = None,
        runner: CommandTemplateRunner | None = None,
    ) -> None:
        self.storage = storage or StorageService()
        self.settings = settings or get_settings()
        self.runner = runner or CommandTemplateRunner()

    def run_voice_training(self, job_id: int, input_path: str, progress_callback: Callable[[int], None]) -> str:
        source = self._require_file(input_path, "Input file")
        logger.info("Starting RVC training job_id=%s input=%s", job_id, source)
        if not self.settings.rvc_train_command:
            raise PipelineConfigurationError(
                "AIS_RVC_TRAIN_COMMAND is required for real voice training. "
                "Template variables: {input}, {model_dir}, {job_id}."
            )

        model_dir = self.storage.model_output_dir(job_id)
        reported_progress = 0

        def report_progress(value: int) -> None:
            nonlocal reported_progress
            if value > reported_progress:
                reported_progress = value
                progress_callback(value)

        def parse_progress(line: str) -> None:
            if not line.startswith("AIS_PROGRESS="):
                return
            try:
                report_progress(int(line.removeprefix("AIS_PROGRESS=")))
            except ValueError:
                logger.warning("Ignoring invalid training progress marker: %s", line)

        report_progress(10)
        self.runner.run(
            self.settings.rvc_train_command,
            {
                "input": str(source),
                "model_dir": str(model_dir),
                "job_id": str(job_id),
            },
            parse_progress,
        )
        report_progress(35)

        model_path = model_dir / self.settings.rvc_model_filename
        index_path = model_dir / self.settings.rvc_index_filename
        if not model_path.exists():
            raise FileNotFoundError(f"RVC training finished but model file is missing: {model_path}")
        report_progress(75)
        if self.settings.rvc_index_filename and not index_path.exists():
            raise FileNotFoundError(f"RVC training finished but index file is missing: {index_path}")

        (model_dir / "manifest.txt").write_text(
            "real RVC training output\n"
            f"source={source}\n"
            f"model={model_path}\n"
            f"index={index_path}\n",
            encoding="utf-8",
        )
        report_progress(100)
        logger.info("Finished RVC training job_id=%s model=%s", job_id, model_path)
        return str(model_path)

    def run_song_processing(
        self,
        job_id: int,
        input_path: str,
        progress_callback: Callable[[int], None],
        model_path: str | None = None,
        lyrics_path: str | None = None,
    ) -> str:
        source = self._require_file(input_path, "Input file")
        logger.info("Starting song processing job_id=%s input=%s", job_id, source)
        if not self.settings.demucs_command:
            raise PipelineConfigurationError(
                "AIS_DEMUCS_COMMAND is required for real song processing. "
                "Template variables: {input}, {output_dir}, {demucs_dir}, {vocals}, {instrumental}, {job_id}."
            )
        if not self.settings.rvc_infer_command:
            raise PipelineConfigurationError(
                "AIS_RVC_INFER_COMMAND is required for real song processing. "
                "Template variables: {vocals}, {ai_vocal}, {model_path}, {output_dir}, {job_id}."
            )
        selected_model_path = model_path or self.settings.active_model_path
        if not selected_model_path:
            raise PipelineConfigurationError("AIS_ACTIVE_MODEL_PATH is required for RVC inference.")

        active_model = self._require_file(selected_model_path, "Active RVC model")
        output_dir = self.storage.song_output_dir(job_id)
        demucs_dir = output_dir / "demucs"
        vocals = output_dir / "vocals.wav"
        instrumental = output_dir / "instrumental.wav"
        ai_vocal = output_dir / "ai_vocal.wav"
        lyrics_output = self._copy_lyrics(lyrics_path, output_dir)

        progress_callback(10)
        self.runner.run(
            self.settings.demucs_command,
            {
                "input": str(source),
                "output_dir": str(output_dir),
                "demucs_dir": str(demucs_dir),
                "vocals": str(vocals),
                "instrumental": str(instrumental),
                "job_id": str(job_id),
            },
        )
        self._discover_demucs_outputs(demucs_dir, vocals, instrumental)
        self._require_file(vocals, "Demucs vocals output")
        self._require_file(instrumental, "Demucs instrumental output")
        progress_callback(45)

        self.runner.run(
            self.settings.rvc_infer_command,
            {
                "vocals": str(vocals),
                "ai_vocal": str(ai_vocal),
                "model_path": str(active_model),
                "output_dir": str(output_dir),
                "job_id": str(job_id),
            },
        )
        self._require_file(ai_vocal, "RVC inference output")
        progress_callback(80)
        (output_dir / "manifest.txt").write_text(
            "real song processing output\n"
            f"source={source}\n"
            f"vocals={vocals}\n"
            f"instrumental={instrumental}\n"
            f"ai_vocal={ai_vocal}\n"
            f"lyrics={lyrics_output or ''}\n"
            f"model={active_model}\n",
            encoding="utf-8",
        )
        progress_callback(100)
        logger.info("Finished song processing job_id=%s ai_vocal=%s", job_id, ai_vocal)
        return str(ai_vocal)

    def _require_file(self, path: str | Path, label: str) -> Path:
        target = Path(path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"{label} missing: {target}")
        return target

    def _discover_demucs_outputs(self, demucs_dir: Path, vocals: Path, instrumental: Path) -> None:
        if vocals.exists() and instrumental.exists():
            return
        if not demucs_dir.exists():
            return
        found_vocals = next(demucs_dir.rglob("vocals.wav"), None)
        found_instrumental = next(demucs_dir.rglob("no_vocals.wav"), None)
        if found_vocals and not vocals.exists():
            vocals.write_bytes(found_vocals.read_bytes())
        if found_instrumental and not instrumental.exists():
            instrumental.write_bytes(found_instrumental.read_bytes())

    def _copy_lyrics(self, lyrics_path: str | None, output_dir: Path) -> Path | None:
        if not lyrics_path:
            return None
        source = self._require_file(lyrics_path, "Lyrics file")
        suffix = source.suffix.lower() if source.suffix else ".txt"
        if suffix not in {".lrc", ".txt"}:
            suffix = ".txt"
        target = output_dir / f"lyrics{suffix}"
        shutil.copy2(source, target)
        return target


class PlaceholderPipelines:
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    def run_voice_training(self, job_id: int, input_path: str, progress_callback: Callable[[int], None]) -> str:
        source = Path(input_path)
        if not source.exists():
            raise FileNotFoundError(f"Input file missing: {input_path}")
        output_dir = self.storage.model_output_dir(job_id)
        for progress in (15, 40, 70, 90):
            progress_callback(progress)
        model_path = output_dir / "rvc_model_placeholder.txt"
        model_path.write_text("placeholder RVC model artifact\n", encoding="utf-8")
        return str(model_path)

    def run_song_processing(
        self,
        job_id: int,
        input_path: str,
        progress_callback: Callable[[int], None],
        lyrics_path: str | None = None,
    ) -> str:
        source = Path(input_path)
        if not source.exists():
            raise FileNotFoundError(f"Input file missing: {input_path}")
        output_dir = self.storage.song_output_dir(job_id)
        for progress in (10, 35, 65, 90):
            progress_callback(progress)
        ai_vocal = output_dir / "ai_vocal_placeholder.wav"
        write_tone(ai_vocal)
        lyrics_output = self._copy_lyrics(lyrics_path, output_dir)
        (output_dir / "manifest.txt").write_text(
            "placeholder song processing output\n"
            f"source={source}\n"
            f"ai_vocal={ai_vocal}\n"
            f"lyrics={lyrics_output or ''}\n",
            encoding="utf-8",
        )
        return str(ai_vocal)

    def _copy_lyrics(self, lyrics_path: str | None, output_dir: Path) -> Path | None:
        if not lyrics_path:
            return None
        source = Path(lyrics_path)
        if not source.is_file():
            raise FileNotFoundError(f"Lyrics file missing: {source}")
        suffix = source.suffix.lower() if source.suffix else ".txt"
        if suffix not in {".lrc", ".txt"}:
            suffix = ".txt"
        target = output_dir / f"lyrics{suffix}"
        shutil.copy2(source, target)
        return target
