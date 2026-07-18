# 妙唱 Client

PySide6 Windows desktop client for login, uploads, task queue polling, and threshold-based playback.

## Create Conda Environment

If Conda official sources are slow or blocked, configure a mirror first:

```powershell
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
conda config --remove channels defaults
conda config --set show_channel_urls yes
```

This environment file includes `nodefaults`, so Conda should not append `https://repo.anaconda.com`.

Run from `client/`:

```powershell
conda env create -f environment.yml
conda activate ai-sing-client
```

The requirements file already uses the Tsinghua PyPI mirror. After activating:

```powershell
python -m pip install -r requirements-gpu.txt
python -m pip install -r requirements.txt
```

## Run

Run from `client/`:

```powershell
conda activate ai-sing-client
python -m aising_client.main
```

## Build Windows Desktop Package

Run from `client/` after installing requirements:

```powershell
.\build_windows.ps1
```

The packaged desktop app is generated at:

```text
dist\妙唱\妙唱.exe
```

## Local Stem Separation

The `本地分离` page runs Demucs on the client computer only. It does not upload the selected song or create a server task.

CUDA-enabled PyTorch is installed through `requirements-gpu.txt`; the rest of the application and Demucs dependencies use the Tsinghua PyPI source in `requirements.txt`. When CUDA is available, the tool attempts NVIDIA GPU separation first and automatically retries on CPU if the GPU attempt fails.

After processing, the tool can preview both result tracks and open the output folder directly:

```text
vocals.wav
no_vocals.wav
```

### Repair An Existing Environment

If the separation log reports `Running local separation on CPU` on a computer with an NVIDIA GPU, or reports that `torchcodec` is missing, check the installed PyTorch runtime:

```powershell
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
```

For this client, the expected result is a CUDA-enabled `torch 2.7.0` runtime with `True` for CUDA availability. Repair an environment that contains CPU-only or newer incompatible TorchAudio packages with:

```powershell
python -m pip uninstall -y torch torchaudio torchvision torchcodec
python -m pip install --force-reinstall -r requirements-gpu.txt
python -m pip install -r requirements.txt
```
