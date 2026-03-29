from __future__ import annotations

import torch
import torch.nn.functional as F


def resample(waveform, orig_freq: int, new_freq: int, **_kwargs):
    tensor = torch.as_tensor(waveform, dtype=torch.float32)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    if orig_freq == new_freq:
        return tensor

    orig_len = tensor.shape[-1]
    new_len = max(1, int(round(orig_len * float(new_freq) / float(orig_freq))))
    resized = F.interpolate(
        tensor.unsqueeze(1),
        size=new_len,
        mode="linear",
        align_corners=False,
    ).squeeze(1)
    return resized.contiguous()
