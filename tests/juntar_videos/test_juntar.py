import copy
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from juntar_videos import juntar


def manifest_fixture(tmp_path):
    source = tmp_path / "vídeos d'aula"
    source.mkdir()
    for name in ("01.Introdução.mp4", "02.Conclusão.mp4"):
        (source / name).write_bytes(name.encode())
    manifest = tmp_path / "juncao.yaml"
    data = {
        "origem": source.name,
        "saida": "saida/final.mp4",
        "arquivos": ["02.Conclusão.mp4", "01.Introdução.mp4"],
    }
    save(manifest, data)
    return source, manifest, data


def save(manifest, data):
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def streams():
    return [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 320,
            "height": 240,
            "time_base": "1/12800",
            "pix_fmt": "yuv420p",
            "extradata_hash": "SHA256:abc",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "48000",
            "channels": 2,
            "channel_layout": "stereo",
            "time_base": "1/48000",
        },
    ]


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(juntar, "require_ffmpeg", lambda: None)
    monkeypatch.setattr(juntar, "probe_streams", lambda video: streams())
    calls = []

    def run(command, **kwargs):
        calls.append((command, Path(command[command.index("-i") + 1]).read_text(encoding="utf-8")))
        Path(command[-1]).write_bytes(b"video unido")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(juntar.subprocess, "run", run)
    return calls


def test_join_uses_yaml_order_copy_all_streams_and_preserves_sources(tmp_path, fake_ffmpeg):
    source, manifest, _ = manifest_fixture(tmp_path)
    originals = {p: p.read_bytes() for p in source.iterdir()}
    assert juntar.main(["--yaml", str(manifest)]) == 0
    output = tmp_path / "saida/final.mp4"
    assert output.read_bytes() == b"video unido"
    command, listing = fake_ffmpeg[0]
    assert command[command.index("-c") + 1] == "copy"
    assert command[command.index("-map") + 1] == "0"
    assert command[command.index("-f") + 1] == "concat"
    assert listing.startswith("ffconcat version 1.0\n")
    assert listing.index("02.Conclusão") < listing.index("01.Introdução")
    assert "d'\\''aula" in listing
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert list(output.parent.iterdir()) == [output]


def test_simulation_probes_without_creating_output(tmp_path, fake_ffmpeg):
    _, manifest, _ = manifest_fixture(tmp_path)
    assert juntar.main(["--yaml", str(manifest), "--simular"]) == 0
    assert not (tmp_path / "saida").exists()
    assert not fake_ffmpeg


@pytest.mark.parametrize(
    "entries",
    [
        [],
        ["01.Introdução.mp4"],
        None,
        "video.mp4",
        ["01.Introdução.mp4", "ausente.mp4"],
        [None, "01.Introdução.mp4"],
        ["../fora.mp4", "01.Introdução.mp4"],
        ["C:\\fora.mp4", "01.Introdução.mp4"],
        ["linha\n.mp4", "01.Introdução.mp4"],
    ],
)
def test_invalid_entries_do_not_create_output(tmp_path, entries):
    _, manifest, data = manifest_fixture(tmp_path)
    data["arquivos"] = entries
    save(manifest, data)
    assert juntar.main(["--yaml", str(manifest)]) == 1
    assert not (tmp_path / "saida").exists()


@pytest.mark.parametrize("content", ["[", "[]", "{}", "!!python/object:obj {}"])
def test_invalid_yaml(tmp_path, content):
    manifest = tmp_path / "juncao.yaml"
    manifest.write_text(content, encoding="utf-8")
    assert juntar.main(["--yaml", str(manifest)]) == 1


def test_roots_relative_to_yaml_not_current_directory(tmp_path, monkeypatch):
    source, manifest, _ = manifest_fixture(tmp_path)
    monkeypatch.chdir(source)
    videos, output = juntar.load_manifest(manifest)
    assert videos[0] == source / "02.Conclusão.mp4"
    assert output == tmp_path / "saida/final.mp4"


@pytest.mark.parametrize("same_input", [True, False])
def test_existing_output_or_input_as_output_rejected(tmp_path, same_input):
    source, manifest, data = manifest_fixture(tmp_path)
    output = source / "01.Introdução.mp4" if same_input else tmp_path / "existente.mp4"
    if not same_input:
        output.write_bytes(b"existente")
    before = output.read_bytes()
    data["saida"] = str(output)
    save(manifest, data)
    assert juntar.main(["--yaml", str(manifest)]) == 1
    assert output.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "order",
        "codec_name",
        "width",
        "time_base",
        "sample_rate",
        "channel_layout",
        "extradata_hash",
    ],
)
def test_incompatible_streams_rejected_before_ffmpeg(tmp_path, monkeypatch, fake_ffmpeg, change):
    _, manifest, _ = manifest_fixture(tmp_path)
    reference = streams()
    other = copy.deepcopy(reference)
    if change == "count":
        other.pop()
    elif change == "order":
        other.reverse()
    else:
        other[1 if change in {"sample_rate", "channel_layout"} else 0][change] = "different"
    responses = iter([reference, other])
    monkeypatch.setattr(juntar, "probe_streams", lambda video: next(responses))
    with pytest.raises(ValueError, match="Video incompativel") as error:
        juntar.join_videos(manifest)
    assert "01.Introdução.mp4" in str(error.value)
    assert not (tmp_path / "saida").exists()
    assert not fake_ffmpeg


@pytest.mark.parametrize("mode", ["error", "interrupt", "empty", "race"])
def test_failure_cleans_temporaries_and_preserves_originals(
    tmp_path, monkeypatch, fake_ffmpeg, mode
):
    source, manifest, _ = manifest_fixture(tmp_path)
    output = tmp_path / "saida/final.mp4"

    def run(command, **kwargs):
        temporary = Path(command[-1])
        temporary.write_bytes(b"parcial" if mode != "empty" else b"")
        if mode == "interrupt":
            raise KeyboardInterrupt
        if mode == "race":
            output.write_bytes(b"concorrente")
        return SimpleNamespace(returncode=1 if mode == "error" else 0, stderr="erro do muxer")

    monkeypatch.setattr(juntar.subprocess, "run", run)
    assert juntar.main(["--yaml", str(manifest)]) == (130 if mode == "interrupt" else 1)
    assert len(list(source.iterdir())) == 2
    assert not list(output.parent.glob(".juntar_videos-*"))
    if mode == "race":
        assert output.read_bytes() == b"concorrente"
    else:
        assert not output.exists()


@pytest.mark.parametrize("mode", ["failure", "invalid_json", "invalid_streams", "no_video"])
def test_probe_errors_are_explained(tmp_path, monkeypatch, mode):
    result = SimpleNamespace(returncode=0, stdout=json.dumps({"streams": streams()}), stderr="erro")
    if mode == "failure":
        result.returncode = 1
    elif mode == "invalid_json":
        result.stdout = "["
    elif mode == "invalid_streams":
        result.stdout = '{"streams": [1]}'
    else:
        result.stdout = '{"streams": []}'
    monkeypatch.setattr(juntar.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises((ValueError, RuntimeError)):
        juntar.probe_streams(tmp_path / "video.mp4")


def test_missing_ffmpeg_reports_error(monkeypatch):
    monkeypatch.setattr(juntar.shutil, "which", lambda executable: None)
    with pytest.raises(RuntimeError, match="PATH"):
        juntar.require_ffmpeg()


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="Requer FFmpeg"
)
def test_integration_real_join_codecs_duration_and_order(tmp_path):
    # Apenas as entradas sinteticas do teste sao codificadas. A juncao usa -c copy.
    source = tmp_path / "vídeos d'aula"
    source.mkdir()
    for name, color in (("01 vermelho.mp4", "red"), ("02 azul.mp4", "blue")):
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=160x120:r=25:d=0.6",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                "0.6",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-y",
                str(source / name),
            ],
            check=True,
            capture_output=True,
        )
    manifest = tmp_path / "juncao.yaml"
    output = tmp_path / "resultado.mp4"
    inputs = [source / "02 azul.mp4", source / "01 vermelho.mp4"]
    save(
        manifest,
        {"origem": str(source), "saida": str(output), "arquivos": [video.name for video in inputs]},
    )
    originals = [video.read_bytes() for video in inputs]
    assert juntar.main(["--yaml", str(manifest)]) == 0
    actual = juntar.probe_streams(output)
    assert [s["codec_name"] for s in actual] == ["h264", "aac"]
    assert float(actual[0]["duration"]) == pytest.approx(1.2, abs=0.1)
    # O primeiro frame deve continuar azul; a ordem dos nomes foi invertida no YAML.
    frame = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(output),
            "-frames:v",
            "1",
            "-vf",
            "scale=1:1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert frame[2] > frame[0] + 100
    assert [video.read_bytes() for video in inputs] == originals
    assert not list(tmp_path.glob(".juntar_videos-*"))
