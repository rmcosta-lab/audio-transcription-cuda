import json
from pathlib import Path

import pytest

import pipeline
from edicao_video.cortar_trechos_fala import VideoPlan


@pytest.fixture
def fake_media(monkeypatch):
    monkeypatch.setattr(pipeline, "require_ffmpeg", lambda: None)
    monkeypatch.setattr(pipeline, "has_audio", lambda video: True)

    def analyze(video, args, *, output_name):
        output_dir = args.saida / f"{output_name}_trechos"
        output_dir.mkdir(parents=True, exist_ok=True)
        return VideoPlan(video, 120, [(0, 120)], output_dir, args.saida / "tempos.txt")

    def cut(plan, args):
        output = plan.output_dir / f"{plan.video.stem}_trecho_001.mp4"
        output.write_bytes(b"video")
        return [output]

    def extract(video, output, reencode, overwrite):
        assert video.read_bytes() == b"video"
        output.write_bytes(b"audio")

    monkeypatch.setattr(pipeline, "analyze_video", analyze)
    monkeypatch.setattr(pipeline, "generate_cuts", cut)
    monkeypatch.setattr(pipeline, "extract_audio", extract)


def make_video(root, name):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def read_report(destination):
    return json.loads((destination / "relatorio_pipeline.json").read_text(encoding="utf-8"))


def test_batch_preserves_subdirectories_and_distinguishes_extensions(tmp_path, fake_media):
    source, destination = tmp_path / "origem", tmp_path / "destino"
    for name in ("modulo 1/aula.mp4", "modulo 2/aula.mp4", "modulo 1/aula.mkv"):
        make_video(source, name)
    # Um corte antigo nao pode entrar na extracao deste lote.
    make_video(destination, "antigo.mp4")

    assert pipeline.main([str(source), "--saida", str(destination)]) == 0

    report = read_report(destination)
    assert len(report["videos"]) == 3
    assert len(list((destination / "audios_extraidos").rglob("*.m4a"))) == 3
    for record in report["videos"]:
        assert record["status"] == "concluido"
        relative = Path(record["video"]).relative_to(source)
        expected = destination / "audios_extraidos" / relative.parent / f"{relative.name}_trechos"
        assert Path(record["audios"][0]).parent == expected


def test_destination_inside_source_is_excluded(tmp_path, fake_media):
    make_video(tmp_path, "original.mp4")
    destination = tmp_path / "saida"
    make_video(destination, "corte_antigo.mp4")

    assert pipeline.main([str(tmp_path), "--saida", str(destination)]) == 0
    assert len(read_report(destination)["videos"]) == 1


def test_failure_does_not_prevent_next_video(tmp_path, fake_media, monkeypatch):
    source, destination = tmp_path / "origem", tmp_path / "destino"
    make_video(source, "a.mp4")
    make_video(source, "b.mp4")
    extract = pipeline.extract_audio

    def fail_first(video, output, **kwargs):
        if video.name.startswith("a_"):
            raise RuntimeError("Falha simulada na extracao")
        extract(video, output, **kwargs)

    monkeypatch.setattr(pipeline, "extract_audio", fail_first)
    assert pipeline.main([str(source), "--saida", str(destination)]) == 1
    assert [r["status"] for r in read_report(destination)["videos"]] == ["erro", "concluido"]


@pytest.mark.parametrize("stage", ["audio", "trechos"])
def test_skips_video_without_audio_or_segments(tmp_path, fake_media, monkeypatch, stage):
    source, destination = tmp_path / "origem", tmp_path / "destino"
    make_video(source, "aula.mp4")
    if stage == "audio":
        monkeypatch.setattr(pipeline, "has_audio", lambda _: False)
    else:
        analyze = pipeline.analyze_video

        def empty_plan(*args, **kwargs):
            plan = analyze(*args, **kwargs)
            plan.segments = []
            return plan

        monkeypatch.setattr(pipeline, "analyze_video", empty_plan)
    assert pipeline.main([str(source), "--saida", str(destination)]) == 0
    assert read_report(destination)["videos"][0]["status"] == f"sem_{stage}"
    assert not list(destination.rglob("*.m4a"))


@pytest.mark.parametrize("existing", ["video", "audio"])
def test_existing_outputs_are_protected(tmp_path, fake_media, existing):
    source, destination = tmp_path / "origem", tmp_path / "destino"
    make_video(source, "aula.mp4")
    base = destination if existing == "video" else destination / "audios_extraidos"
    suffix = ".mp4" if existing == "video" else ".m4a"
    output = make_video(base, f"aula.mp4_trechos/aula_trecho_001{suffix}")
    output.write_bytes(b"original")

    command = [str(source), "--saida", str(destination)]
    assert pipeline.main(command) == 1
    assert output.read_bytes() == b"original"
    assert pipeline.main([*command, "--overwrite"]) == 0
    assert output.read_bytes() != b"original"


@pytest.mark.parametrize("case", ["missing", "empty", "same", "ancestor"])
def test_invalid_directories(tmp_path, fake_media, case):
    source = tmp_path / "origem"
    destination = tmp_path / "destino"
    if case != "missing":
        source.mkdir()
    if case == "same":
        destination = source
    elif case == "ancestor":
        destination = tmp_path
    assert pipeline.main([str(source), "--saida", str(destination)]) == 1


def test_interrupt_is_recorded(tmp_path, fake_media, monkeypatch):
    source, destination = tmp_path / "origem", tmp_path / "destino"
    make_video(source, "aula.mp4")

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "generate_cuts", interrupt)
    assert pipeline.main([str(source), "--saida", str(destination)]) == 130
    assert read_report(destination)["videos"][0]["status"] == "interrompido"


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_invalid_timing_options(value):
    with pytest.raises(SystemExit) as error:
        pipeline.build_parser().parse_args(["origem", "--saida", "destino", "--padding", value])
    assert error.value.code == 2
