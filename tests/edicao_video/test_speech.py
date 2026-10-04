import argparse
import subprocess
from pathlib import Path

import pytest

from edicao_video import cortar_trechos_fala as editor


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        ("", [(0, 10)]),
        ("silence_start: 0\nsilence_end: 10", []),
        ("silence_start: 3", [(0, 3)]),
        ("silence_start: 0\nsilence_end: 2\nsilence_start: 7", [(2, 7)]),
        ("silence_start: 3\nsilence_end: 6", [(0, 3), (6, 10)]),
    ],
)
def test_speech_intervals(monkeypatch, log, expected):
    monkeypatch.setattr(
        editor, "run_command", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", log)
    )
    assert editor.detect_speech(Path("video.mp4"), 10, "-35dB", 1, 0, 0, 1) == expected


def test_padding_merges_nearby_intervals(monkeypatch):
    log = "silence_start: 3\nsilence_end: 3.4"
    monkeypatch.setattr(
        editor, "run_command", lambda *a, **kw: subprocess.CompletedProcess([], 0, "", log)
    )
    assert editor.detect_speech(Path("video.mp4"), 10, "-35dB", 0.1, 0.25, 0, 1) == [(0, 10)]


def test_existing_report_is_not_modified(tmp_path):
    report = tmp_path / "video_tempos.txt"
    report.write_text("original", encoding="utf-8")
    args = argparse.Namespace(saida=tmp_path, overwrite=False)
    with pytest.raises(RuntimeError, match="Relatorio ja existe"):
        editor.analyze_video(Path("video.mp4"), args)
    assert report.read_text(encoding="utf-8") == "original"
