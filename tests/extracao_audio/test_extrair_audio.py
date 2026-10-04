import subprocess
from pathlib import Path

import pytest

from extracao_audio import extrair_audio as extraction


def test_probe_failure_is_not_mistaken_for_video_without_audio(monkeypatch):
    monkeypatch.setattr(
        extraction.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 1, "", "corrompido"),
    )
    with pytest.raises(RuntimeError, match="corrompido"):
        extraction.has_audio(Path("video.mp4"))


@pytest.mark.parametrize(("stdout", "expected"), [("", False), ("1\n", True)])
def test_audio_presence(monkeypatch, stdout, expected):
    monkeypatch.setattr(
        extraction.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout, ""),
    )
    assert extraction.has_audio(Path("video.mp4")) == expected


@pytest.mark.parametrize("reencode", [False, True])
def test_audio_extraction_options(monkeypatch, reencode):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(extraction.subprocess, "run", run)
    extraction.extract_audio(Path("entrada.mp4"), Path("saida.m4a"), reencode, False)
    command = commands[0]
    assert command[command.index("-c:a") + 1] == ("aac" if reencode else "copy")
    assert "-nostdin" in command
    assert "-n" in command
