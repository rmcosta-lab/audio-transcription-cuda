import sys
from types import SimpleNamespace

import pytest

from transcrever_audio import transcrever_audio as transcription


@pytest.fixture
def fake_model(monkeypatch):
    state = SimpleNamespace(initializations=[], calls=[], failures=set())

    class FakeModel:
        def __init__(self, name, **kwargs):
            state.initializations.append((name, kwargs))

        def transcribe(self, path, **kwargs):
            state.calls.append((path, kwargs))

            def segments():
                if path in state.failures:
                    raise ValueError("Audio ilegivel")
                yield SimpleNamespace(start=0, end=2, text=" Texto transcrito. ")

            return segments(), SimpleNamespace(duration=2)

    monkeypatch.setitem(sys.modules, "truststore", SimpleNamespace(inject_into_ssl=lambda: None))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    return state


def input_file(root, relative):
    """Somente um marcador de caminho; o modelo substituto nao le midia."""
    audio = root / relative
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.touch()
    return audio


def test_batch_reuses_model_preserves_subfolders_and_forwards_options(tmp_path, fake_model):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    first = input_file(source, "modulo 1/aula.M4A")
    second = input_file(source, "modulo 2/aula.mp3")
    input_file(source, "notas.txt")

    transcription.main(
        [
            str(source),
            "-o",
            str(destination),
            "--model",
            "medium",
            "--device",
            "cuda",
            "--compute-type",
            "float16",
            "--language",
            "en",
            "--no-vad",
        ]
    )

    assert fake_model.initializations == [("medium", {"device": "cuda", "compute_type": "float16"})]
    assert [path for path, _ in fake_model.calls] == [str(first), str(second)]
    assert all(
        options == {"language": "en", "beam_size": 5, "vad_filter": False}
        for _, options in fake_model.calls
    )
    for relative in ("modulo 1/aula.md", "modulo 2/aula.md"):
        assert "Texto transcrito." in (destination / relative).read_text(encoding="utf-8")


def test_batch_skips_existing_files_without_loading_model(tmp_path, fake_model, capsys):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    input_file(source, "aula.wav")
    output = input_file(destination, "aula.md")
    output.write_text("Transcricao revisada", encoding="utf-8")

    transcription.main([str(source), "--output", str(destination)])

    assert output.read_text(encoding="utf-8") == "Transcricao revisada"
    assert not fake_model.initializations
    assert "ignorados: 1" in capsys.readouterr().out

    transcription.main([str(source), "--saida", str(destination), "--overwrite"])
    assert "Texto transcrito." in output.read_text(encoding="utf-8")


def test_failure_in_segments_continues_batch_and_returns_error(tmp_path, fake_model, capsys):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    broken = input_file(source, "a_invalido.m4a")
    input_file(source, "b_valido.flac")
    fake_model.failures.add(str(broken))

    with pytest.raises(SystemExit) as error:
        transcription.main([str(source), "-o", str(destination)])

    assert error.value.code == 1
    assert not (destination / "a_invalido.md").exists()
    assert (destination / "b_valido.md").is_file()
    assert "Audio ilegivel" in capsys.readouterr().err
    assert len(fake_model.initializations) == 1


def test_failed_overwrite_preserves_previous_transcript(tmp_path, fake_model):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    audio = input_file(source, "aula.m4a")
    output = input_file(destination, "aula.md")
    output.write_text("Original", encoding="utf-8")
    fake_model.failures.add(str(audio))

    with pytest.raises(SystemExit):
        transcription.main([str(source), "-o", str(destination), "--overwrite"])
    assert output.read_text(encoding="utf-8") == "Original"


def test_name_collision_is_reported_before_loading_model(tmp_path, fake_model, capsys):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    input_file(source, "aula.m4a")
    input_file(source, "aula.wav")

    with pytest.raises(SystemExit) as error:
        transcription.main([str(source), "-o", str(destination), "--overwrite"])
    assert error.value.code == 1
    assert "Conflito de nomes" in capsys.readouterr().err
    assert not fake_model.initializations
    assert not destination.exists()


@pytest.mark.parametrize(
    "case", ["missing_input", "empty", "missing_output", "output_file", "output_directory_conflict"]
)
def test_invalid_batch_does_not_load_model(tmp_path, fake_model, case):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    arguments = [str(source), "-o", str(destination)]
    if case != "missing_input":
        source.mkdir()
    if case not in {"missing_input", "empty"}:
        input_file(source, "aula.m4a")
    if case == "missing_output":
        arguments = [str(source)]
    elif case == "output_file":
        destination.touch()
    elif case == "output_directory_conflict":
        (destination / "aula.md").mkdir(parents=True)

    with pytest.raises(SystemExit) as error:
        transcription.main(arguments)
    assert error.value.code == 1
    assert not fake_model.initializations


def test_nested_destination_is_excluded(tmp_path, fake_model):
    source = tmp_path / "audios"
    destination = source / "transcricoes"
    audio = input_file(source, "aula.m4a")
    input_file(destination, "nao_transcrever.mp3")

    transcription.main([str(source), "-o", str(destination)])
    assert [path for path, _ in fake_model.calls] == [str(audio)]


def test_single_file_keeps_default_output_and_overwrite(tmp_path, fake_model, monkeypatch):
    monkeypatch.chdir(tmp_path)
    audio = input_file(tmp_path, "aula.m4a")
    output = tmp_path / transcription.DEFAULT_OUTPUT
    output.write_text("Versao anterior", encoding="utf-8")

    transcription.main([str(audio), "--language", ""])

    assert "Texto transcrito." in output.read_text(encoding="utf-8")
    assert fake_model.calls[0][1]["language"] is None


def test_interrupt_exits_without_processing_next_file(tmp_path, fake_model, monkeypatch):
    source, destination = tmp_path / "audios", tmp_path / "transcricoes"
    input_file(source, "a.m4a")
    input_file(source, "b.m4a")

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(transcription, "transcribe_file", interrupt)
    with pytest.raises(SystemExit) as error:
        transcription.main([str(source), "-o", str(destination)])
    assert error.value.code == 130
