from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import soundfile as sf
import torch

from .backend.common import AudioMetaData
from .functional import resample

__version__ = "local-shim"


def info(file, **_kwargs) -> AudioMetaData:
    path = Path(file)
    metadata = sf.info(str(path))
    return AudioMetaData(
        sample_rate=int(metadata.samplerate),
        num_frames=int(metadata.frames),
        num_channels=int(metadata.channels),
        bits_per_sample=16,
        encoding="PCM_S",
    )


def load(file, channels_first: bool = True, **_kwargs):
    data, sample_rate = sf.read(str(file), dtype="float32", always_2d=True)
    tensor = torch.from_numpy(data.T if channels_first else data)
    return tensor.contiguous(), int(sample_rate)


def save(file, audio, sample_rate: int, **_kwargs):
    tensor = torch.as_tensor(audio)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    data = tensor.detach().cpu().numpy().T
    sf.write(str(file), data, int(sample_rate))

