from pathlib import Path

from cookit import auto_import


def load_handlers():
    auto_import(Path(__file__).parent, __package__)
