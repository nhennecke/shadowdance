import shutil
from pathlib import Path

from PIL import Image, ImageOps


def rotate_image(
    path: str,
    degrees: int,
    overwrite: bool = False,
    output_path: str | None = None,
) -> str:
    src = Path(path)
    with Image.open(src) as img:
        img.load()
        # Pillow rotate is counter-clockwise; negate for intuitive CW input
        rotated = img.rotate(-degrees, expand=True)
    out = _resolve_output(src, overwrite, output_path)
    if overwrite:
        _backup_if_needed(src)
    rotated.save(out)
    return str(out)


def flip_image(
    path: str,
    horizontal: bool = True,
    overwrite: bool = False,
    output_path: str | None = None,
) -> str:
    src = Path(path)
    with Image.open(src) as img:
        img.load()
        result = ImageOps.mirror(img) if horizontal else ImageOps.flip(img)
    out = _resolve_output(src, overwrite, output_path)
    if overwrite:
        _backup_if_needed(src)
    result.save(out)
    return str(out)


def crop_image(
    path: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    overwrite: bool = False,
    output_path: str | None = None,
) -> str:
    src = Path(path)
    with Image.open(src) as img:
        img.load()
        cropped = img.crop((left, top, right, bottom))
    out = _resolve_output(src, overwrite, output_path)
    if overwrite:
        _backup_if_needed(src)
    cropped.save(out)
    return str(out)


def _backup_if_needed(src: Path) -> None:
    orig = src.with_suffix(src.suffix + ".orig")
    if not orig.exists():
        shutil.copy2(src, orig)


def _resolve_output(src: Path, overwrite: bool, output_path: str | None) -> Path:
    if output_path:
        return Path(output_path)
    if overwrite:
        return src
    stem, suffix = src.stem, src.suffix
    candidate = src.with_name(f"{stem}_edit{suffix}")
    counter = 1
    while candidate.exists():
        candidate = src.with_name(f"{stem}_edit_{counter}{suffix}")
        counter += 1
    return candidate
