from dataclasses import dataclass


@dataclass
class Frame:
    idx: int
    next_idx: int
    size: int
    data: bytes
