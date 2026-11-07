"""Entry points must be safe to import during pytest collection."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("module_name", ["main", "test_main"])
def test_import_does_not_initialize_pygame(module_name):
    script = """
import importlib
import sys
from unittest.mock import patch
import pygame
with patch.object(pygame, 'init', side_effect=AssertionError('pygame initialized on import')):
    with patch.object(pygame.display, 'set_mode', side_effect=AssertionError('window opened on import')):
        module = importlib.import_module(sys.argv[1])
assert callable(module.main)
"""
    env = os.environ.copy()
    env.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, module_name],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
