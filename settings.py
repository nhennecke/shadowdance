from pathlib import Path

APP_NAME = "ShadowDance"
APP_VERSION = "0.1.0"

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
    ".ico", ".tga", ".avif", ".ppm", ".pgm", ".pbm",
    # RAW
    ".raw", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".pef", ".ptx", ".rw2", ".rwl", ".srw", ".x3f",
    ".raf", ".3fr", ".fff", ".mef", ".mos", ".mrw", ".erf",
    # HEIC/HEIF
    ".heic", ".heif",
}

RAW_EXTENSIONS = {
    ".raw", ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".dng", ".orf", ".pef", ".ptx", ".rw2", ".rwl", ".srw", ".x3f",
    ".raf", ".3fr", ".fff", ".mef", ".mos", ".mrw", ".erf",
}

HEIC_EXTENSIONS = {".heic", ".heif"}

DEFAULT_WINDOW_WIDTH = 1024
DEFAULT_WINDOW_HEIGHT = 768
DEFAULT_WINDOW_X = 100
DEFAULT_WINDOW_Y = 100

DEFAULT_SLIDESHOW_INTERVAL = 5000  # ms
DEFAULT_SLIDESHOW_LOOP = True

SLIDESHOW_EXTENSION = ".sdshow"
