MM_PER_MIL = 0.0254
MIL_PER_MM = 1.0 / MM_PER_MIL


def mm_to_mils(mm: float) -> float:
    return mm * MIL_PER_MM


def mils_to_mm(mils: float) -> float:
    return mils * MM_PER_MIL


def mm_to_px(mm: float, dpi: float = 96.0) -> float:
    inches = mm / 25.4
    return inches * dpi


def px_to_mm(px: float, dpi: float = 96.0) -> float:
    inches = px / dpi
    return inches * 25.4
