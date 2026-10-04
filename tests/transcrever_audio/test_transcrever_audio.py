from pathlib import Path
from types import SimpleNamespace

from transcrever_audio import transcrever_audio as transcription


def test_markdown_contains_timestamps_and_plain_text():
    result = transcription.build_markdown(
        Path("audio.m4a"),
        Path("aula-um.md"),
        "small",
        "pt",
        [(1.5, 4, "Bom dia."), (5, 65, "Segunda frase.")],
    )
    assert "[00:00:01 - 00:00:04] Bom dia." in result
    assert "[00:00:05 - 00:01:05] Segunda frase." in result
    assert "Bom dia. Segunda frase." in result


def test_transcription_with_fake_model(tmp_path, monkeypatch):
    import sys

    audio = tmp_path / "audio.m4a"
    audio.touch()
    output = tmp_path / "transcricao.md"

    class FakeModel:
        def __init__(self, model, **kwargs):
            assert model == "small"

        def transcribe(self, path, **kwargs):
            assert path == str(audio.resolve())
            return iter([SimpleNamespace(start=0, end=2, text=" Ola. ")]), SimpleNamespace(
                duration=2
            )

    monkeypatch.setitem(sys.modules, "truststore", SimpleNamespace(inject_into_ssl=lambda: None))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(sys, "argv", ["transcrever_audio", str(audio), "-o", str(output)])
    transcription.main()
    assert "Ola." in output.read_text(encoding="utf-8")
