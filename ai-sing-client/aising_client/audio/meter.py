import numpy as np
import sounddevice as sd


class MicrophoneMeter:
    def __init__(self) -> None:
        self.level = 0.0
        self.stream: sd.InputStream | None = None

    def start(self) -> None:
        if self.stream is not None:
            return
        self.stream = sd.Stream(channels=1, callback=self._callback)
        self.stream.start()

    def stop(self) -> None:
        if self.stream is None:
            return
        self.stream.stop()
        self.stream.close()
        self.stream = None

    def _callback(self, *args) -> None:
        if len(args) == 5:
            indata, outdata, frames, time, status = args
            outdata[: len(indata)] = indata
        else:
            indata, frames, time, status = args
        if len(indata):
            self.level = float(np.sqrt(np.mean(np.square(indata))))
