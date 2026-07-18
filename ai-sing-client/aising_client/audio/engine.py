from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


class PlaybackEngine:
    def __init__(self) -> None:
        self.data = None
        self.ai_vocal = None
        self.accompaniment = None
        self.sample_rate = 44100
        self.position = 0
        self.volume = 1.0
        self.ai_voice_volume = 1.0
        self.mic_monitor_volume = 0.0
        self.input_level = 0.0
        self.stream: sd.Stream | None = None

    def load(self, path: Path) -> None:
        self.data, self.sample_rate = sf.read(str(path), dtype="float32")
        self.data = self._as_channel_data(self.data)
        self.ai_vocal = None
        self.accompaniment = None
        self.position = 0

    def load_layers(self, ai_vocal_path: Path, accompaniment_path: Path) -> None:
        ai_vocal, ai_rate = sf.read(str(ai_vocal_path), dtype="float32")
        accompaniment, accompaniment_rate = sf.read(str(accompaniment_path), dtype="float32")
        if ai_rate != accompaniment_rate:
            target_rate = max(ai_rate, accompaniment_rate)
            ai_vocal = self._resample(ai_vocal, ai_rate, target_rate)
            accompaniment = self._resample(accompaniment, accompaniment_rate, target_rate)
        else:
            target_rate = ai_rate
        self.load_arrays(ai_vocal, accompaniment, target_rate)

    def load_arrays(self, ai_vocal, accompaniment, sample_rate: int) -> None:
        self.ai_vocal = self._as_channel_data(ai_vocal)
        self.accompaniment = self._as_channel_data(accompaniment)
        self.data = None
        self.sample_rate = sample_rate
        self.position = 0
        self.ai_voice_volume = 1.0

    def set_ai_enabled(self, enabled: bool) -> None:
        self.volume = 1.0 if enabled else 0.15

    def set_ai_voice_enabled(self, enabled: bool) -> None:
        self.ai_voice_volume = 1.0 if enabled else 0.0
        self.mic_monitor_volume = 0.0 if enabled else 1.0

    def ai_voice_energy(self, window: int = 2048) -> float:
        if self.ai_vocal is None or window <= 0:
            return 0.0
        chunk = self.ai_vocal[self.position : self.position + window]
        if len(chunk) == 0:
            return 0.0
        mono = chunk.mean(axis=1)
        return float(np.sqrt(np.mean(np.square(mono))))

    def waveform_peaks(self, bins: int = 240):
        source = self.ai_vocal if self.ai_vocal is not None else self.data
        if source is None or bins <= 0 or len(source) == 0:
            return np.zeros(max(0, bins), dtype="float32")
        mono = np.abs(source.mean(axis=1))
        edges = np.linspace(0, len(mono), bins + 1, dtype=int)
        peaks = np.zeros(bins, dtype="float32")
        for index in range(bins):
            start = edges[index]
            end = max(start + 1, edges[index + 1])
            peaks[index] = float(np.max(mono[start:end]))
        maximum = float(np.max(peaks))
        if maximum > 0:
            peaks = peaks / maximum
        return peaks

    @property
    def frame_count(self) -> int:
        if self.data is None:
            if self.accompaniment is None and self.ai_vocal is None:
                return 0
            return max(len(track) for track in (self.accompaniment, self.ai_vocal) if track is not None)
        return len(self.data)

    @property
    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.frame_count / self.sample_rate

    @property
    def position_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return min(self.position, self.frame_count) / self.sample_rate

    @property
    def progress_percent(self) -> int:
        if self.frame_count <= 0:
            return 0
        return int((min(self.position, self.frame_count) / self.frame_count) * 100)

    def seek_percent(self, percent: int) -> None:
        if self.frame_count <= 0:
            return
        clamped = max(0, min(100, percent))
        self.position = int(self.frame_count * clamped / 100)

    def start(self) -> None:
        if self.stream is not None:
            return
        if self.data is None and self.accompaniment is None and self.ai_vocal is None:
            return
        source = self.data if self.data is not None else self.accompaniment
        if source is None:
            source = self.ai_vocal
        channels = source.shape[1]
        self.stream = sd.Stream(samplerate=self.sample_rate, channels=channels, callback=self._callback)
        self.stream.start()

    def stop(self) -> None:
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.position = 0

    def _callback(self, *args) -> None:
        if len(args) == 5:
            indata, outdata, frames, time, status = args
        else:
            indata = None
            outdata, frames, time, status = args
        end = self.position + frames
        chunk = self._next_chunk(end, outdata.shape[1])
        if indata is not None and self.mic_monitor_volume > 0:
            mic = self._match_output_channels(indata[:frames], outdata.shape[1])
            self.input_level = float(np.sqrt(np.mean(np.square(mic)))) if len(mic) else 0.0
            chunk[: len(mic)] += mic[: len(chunk)] * self.mic_monitor_volume
        elif indata is not None and len(indata):
            self.input_level = float(np.sqrt(np.mean(np.square(indata))))
        chunk = self._match_output_channels(chunk, outdata.shape[1])
        if len(chunk) < frames:
            outdata[: len(chunk)] = chunk * self.volume
            outdata[len(chunk) :] = 0
            self.position = self.frame_count
            return
        outdata[:] = chunk * self.volume
        self.position = end

    def _next_chunk(self, end: int, channels: int):
        if self.data is not None:
            return self.data[self.position:end]
        mixed = np.zeros((max(0, end - self.position), channels), dtype="float32")
        if self.accompaniment is not None:
            accompaniment = self._slice_track(self.accompaniment, end, channels)
            mixed[: len(accompaniment)] += accompaniment
        if self.ai_vocal is not None and self.ai_voice_volume > 0:
            ai_vocal = self._slice_track(self.ai_vocal, end, channels)
            mixed[: len(ai_vocal)] += ai_vocal * self.ai_voice_volume
        remaining = max(len(track) for track in (self.accompaniment, self.ai_vocal) if track is not None) - self.position
        return mixed[: max(0, min(end - self.position, remaining))]

    def _slice_track(self, track, end: int, channels: int):
        chunk = track[self.position:end]
        return self._match_output_channels(chunk, channels)

    def _as_channel_data(self, data):
        if len(data.shape) == 1:
            return data.reshape(-1, 1)
        return data

    def _match_output_channels(self, chunk, channels: int):
        chunk = self._as_channel_data(chunk)
        if chunk.shape[1] == channels:
            return chunk
        if chunk.shape[1] == 1:
            return np.repeat(chunk, channels, axis=1)
        if channels == 1:
            return chunk.mean(axis=1, keepdims=True)
        return chunk[:, :channels]

    def _resample(self, data, source_rate: int, target_rate: int):
        data = self._as_channel_data(data)
        if source_rate == target_rate or len(data) == 0:
            return data
        target_length = max(1, int(round(len(data) * target_rate / source_rate)))
        source_positions = np.arange(len(data), dtype="float32")
        target_positions = np.linspace(0, len(data) - 1, target_length, dtype="float32")
        channels = [
            np.interp(target_positions, source_positions, data[:, channel])
            for channel in range(data.shape[1])
        ]
        return np.stack(channels, axis=1).astype("float32")
