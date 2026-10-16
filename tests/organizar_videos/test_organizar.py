from pathlib import Path

import pytest
import yaml

from organizar_videos.organizar import apply_manifest, list_videos, main, move_exclusive


def make_file(root, relative, content=b"video"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def save(manifest, data):
    manifest.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def prepared_manifest(tmp_path):
    source, destination = tmp_path / "cortes", tmp_path / "organizados"
    make_file(source, "aula01/trecho.mp4", b"primeiro")
    make_file(source, "aula02/trecho.mp4", b"segundo")
    manifest = tmp_path / "organizacao.yaml"
    list_videos(source, manifest, destination)
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for record, order, name in zip(data["arquivos"], [100, 1], ["Conclusão", "Introdução"]):
        record.update(ordem=order, novo_nome=name)
    save(manifest, data)
    return source, destination, manifest, data


def test_listing_recursive_sorted_and_video_only(tmp_path):
    source = tmp_path / "cortes"
    make_file(source, "z/parte.MP4")
    make_file(source, "a/sub/parte.mkv")
    make_file(source, "raiz.mov")
    make_file(source, "tempos.txt")
    make_file(source, "audios/audio.m4a")
    destination = source / "organizados"
    make_file(destination, "antigo.mp4")
    manifest = tmp_path / "lista.yaml"
    assert list_videos(source, manifest, destination) == 3
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert Path(data["origem"]) == source
    assert [item["arquivo"] for item in data["arquivos"]] == ["parte.mkv", "raiz.mov", "parte.MP4"]
    assert data["arquivos"][1]["diretorio"] == "."
    assert all(item["ordem"] is None and item["novo_nome"] == "" for item in data["arquivos"])
    before = manifest.read_bytes()
    with pytest.raises(FileExistsError):
        list_videos(source, manifest, destination)
    assert manifest.read_bytes() == before


def test_apply_flat_names_padding_contents_and_preserved_unlisted_files(tmp_path):
    source, destination, manifest, _ = prepared_manifest(tmp_path)
    untouched = make_file(source, "aula01/tempos.txt", b"relatorio")
    before = manifest.read_bytes()
    assert apply_manifest(manifest) == 2
    assert sorted(path.name for path in destination.iterdir()) == [
        "01.Introdução.mp4",
        "100.Conclusão.mp4",
    ]
    assert (destination / "01.Introdução.mp4").read_bytes() == b"segundo"
    assert (destination / "100.Conclusão.mp4").read_bytes() == b"primeiro"
    assert not list(source.rglob("*.mp4"))
    assert untouched.read_bytes() == b"relatorio"
    assert manifest.read_bytes() == before


def test_list_command_defaults_to_sibling_destination(tmp_path, monkeypatch, capsys):
    source = tmp_path / "cortes"
    video = make_file(source, "trecho.mp4")
    monkeypatch.chdir(tmp_path)
    manifest = source / "lista.yaml"
    assert main(["listar", "cortes", "--yaml", "lista.yaml"]) == 0
    assert not (tmp_path / "lista.yaml").exists()
    assert f"YAML criado no diretorio: {source}" in capsys.readouterr().out
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert Path(data["destino"]) == tmp_path / "cortes_organizados"
    assert video.exists()


def test_long_final_name_is_rejected_before_moves(tmp_path):
    source, destination, manifest, data = prepared_manifest(tmp_path)
    data["arquivos"][-1]["novo_nome"] = "a" * 255
    save(manifest, data)
    with pytest.raises(ValueError, match="255"):
        apply_manifest(manifest)
    assert not destination.exists()
    assert len(list(source.rglob("*.mp4"))) == 2


def test_simulation_does_not_create_destination_or_move(tmp_path):
    source, destination, manifest, _ = prepared_manifest(tmp_path)
    assert main(["aplicar", "--yaml", str(manifest), "--simular"]) == 0
    assert not destination.exists()
    assert len(list(source.rglob("*.mp4"))) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("ordem", None),
        ("ordem", True),
        ("ordem", 0),
        ("ordem", "2"),
        ("ordem", 100),
        ("novo_nome", ""),
        ("novo_nome", "invalido/nome"),
        ("novo_nome", "invalido:nome"),
        ("novo_nome", "final."),
        ("diretorio", "../../fora"),
        ("diretorio", "D:\\fora"),
        ("arquivo", "../trecho.mp4"),
        ("arquivo", "inexistente.mp4"),
    ],
)
def test_invalid_last_item_prevents_all_moves(tmp_path, field, value):
    source, destination, manifest, data = prepared_manifest(tmp_path)
    data["arquivos"][-1][field] = value
    save(manifest, data)
    assert main(["aplicar", "--yaml", str(manifest)]) == 1
    assert not destination.exists()
    assert len(list(source.rglob("*.mp4"))) == 2


def test_duplicate_source_and_existing_target_prevent_moves(tmp_path):
    source, destination, manifest, data = prepared_manifest(tmp_path)
    second = data["arquivos"][1]
    second["diretorio"] = data["arquivos"][0]["diretorio"]
    save(manifest, data)
    with pytest.raises(ValueError, match="origem repetido"):
        apply_manifest(manifest)
    second["diretorio"] = "aula02"
    save(manifest, data)
    existing = make_file(destination, "01.Introdução.mp4", b"existente")
    with pytest.raises(ValueError, match="ja existente"):
        apply_manifest(manifest)
    assert existing.read_bytes() == b"existente"
    assert len(list(source.rglob("*.mp4"))) == 2


def test_relative_roots_are_resolved_from_yaml_location(tmp_path, monkeypatch):
    _, destination, manifest, data = prepared_manifest(tmp_path)
    data.update(origem="cortes", destino="organizados")
    save(manifest, data)
    elsewhere = tmp_path / "outra_pasta"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert apply_manifest(manifest) == 2
    assert (destination / "01.Introdução.mp4").exists()


@pytest.mark.parametrize("content", ["[", "[]", "origem: pasta", "!!python/object:obj {}"])
def test_malformed_yaml_reports_error(tmp_path, content):
    manifest = tmp_path / "lista.yaml"
    manifest.write_text(content, encoding="utf-8")
    assert main(["aplicar", "--yaml", str(manifest)]) == 1


def test_empty_source_does_not_write_manifest(tmp_path):
    manifest = tmp_path / "lista.yaml"
    assert main(["listar", str(tmp_path), "--yaml", str(manifest)]) == 1
    assert not manifest.exists()


def test_destination_must_not_equal_or_contain_source(tmp_path):
    source, _, manifest, data = prepared_manifest(tmp_path)
    for destination in (source, tmp_path):
        data["destino"] = str(destination)
        save(manifest, data)
        assert main(["aplicar", "--yaml", str(manifest)]) == 1
    assert len(list(source.rglob("*.mp4"))) == 2


def test_exclusive_move_does_not_overwrite(tmp_path):
    source = make_file(tmp_path, "origem.mp4", b"original")
    target = make_file(tmp_path, "destino.mp4", b"existente")
    with pytest.raises(FileExistsError):
        move_exclusive(source, target)
    assert source.read_bytes() == b"original"
    assert target.read_bytes() == b"existente"


def test_failed_copy_removes_partial_target_and_keeps_source(tmp_path, monkeypatch):
    source = make_file(tmp_path, "origem.mp4", b"original")
    target = tmp_path / "destino.mp4"

    def fail(input_stream, output):
        output.write(b"parcial")
        raise OSError("disco cheio")

    monkeypatch.setattr("organizar_videos.organizar.shutil.copyfileobj", fail)
    with pytest.raises(OSError, match="disco cheio"):
        move_exclusive(source, target)
    assert source.read_bytes() == b"original"
    assert not target.exists()
