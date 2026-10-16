"""Lista videos em YAML e aplica a organizacao preenchida pelo usuario."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path, PureWindowsPath

import yaml

from edicao_video.cortar_trechos_fala import SUPPORTED_EXTENSIONS


def validate_roots(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"Origem inexistente ou invalida: {source}")
    if source == destination or source.is_relative_to(destination):
        raise ValueError("O destino nao pode ser igual a origem nem conter a origem.")
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"O destino precisa ser uma pasta: {destination}")


def list_videos(source: Path, manifest: Path, destination: Path | None = None) -> int:
    source = source.expanduser().resolve()
    manifest = manifest.expanduser()
    if not manifest.is_absolute():
        manifest = source / manifest
    destination = (
        destination.expanduser().resolve()
        if destination is not None
        else source.with_name(f"{source.name}_organizados")
    )
    validate_roots(source, destination)
    videos = []

    def scan_error(error: OSError) -> None:
        raise error

    for directory, folders, files in os.walk(source, onerror=scan_error, followlinks=False):
        parent = Path(directory)
        folders[:] = [
            name
            for name in folders
            if not (parent / name).is_symlink()
            and not (parent / name).resolve().is_relative_to(destination)
        ]
        for name in files:
            video = parent / name
            if video.suffix.lower() in SUPPORTED_EXTENSIONS and not video.is_symlink():
                videos.append(video)
    videos.sort(key=lambda path: (path.relative_to(source).as_posix().casefold(), str(path)))
    if not videos:
        raise ValueError("Nenhum video suportado encontrado na origem.")
    data = {
        "origem": str(source),
        "destino": str(destination),
        "arquivos": [
            {
                "diretorio": str(video.parent.relative_to(source)),
                "arquivo": video.name,
                "ordem": None,
                "novo_nome": "",
            }
            for video in videos
        ],
    }
    # Modo exclusivo: uma nova listagem nunca apaga o YAML ja preenchido.
    with manifest.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
    print(f"YAML criado no diretorio: {manifest.resolve().parent}")
    print(f"Arquivo: {manifest.name} ({len(videos)} videos). Preencha ordem e novo_nome.")
    return len(videos)


def text_field(record: dict, name: str) -> str:
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo '{name}' precisa ser um texto preenchido.")
    return value


def root_path(value: str, manifest: Path) -> Path:
    path = Path(value).expanduser()
    return (manifest.parent / path).resolve() if not path.is_absolute() else path.resolve()


def build_plan(manifest: Path) -> list[tuple[Path, Path]]:
    with manifest.open(encoding="utf-8-sig") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("O YAML precisa conter origem, destino e arquivos.")
    source = root_path(text_field(data, "origem"), manifest)
    destination = root_path(text_field(data, "destino"), manifest)
    validate_roots(source, destination)
    records = data.get("arquivos")
    if not isinstance(records, list) or not records:
        raise ValueError("'arquivos' precisa ser uma lista nao vazia.")
    orders, sources, targets = set(), set(), set()
    plan = []
    for index, record in enumerate(records, 1):
        try:
            if not isinstance(record, dict):
                raise ValueError("Cada item precisa ser um mapeamento.")
            order = record.get("ordem")
            if type(order) is not int or order < 1:
                raise ValueError("'ordem' precisa ser um inteiro positivo (exemplo: 1).")
            if order in orders:
                raise ValueError(f"Ordem repetida: {order}.")
            name = text_field(record, "novo_nome")
            if re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " ")):
                raise ValueError(
                    "'novo_nome' contem caracteres invalidos ou termina em ponto/espaco."
                )
            directory = text_field(record, "diretorio")
            filename = text_field(record, "arquivo")
            if "/" in filename or "\\" in filename or filename in {".", ".."}:
                raise ValueError("'arquivo' deve conter apenas o nome original com extensao.")
            relative = Path(directory.replace("\\", "/"))
            if relative.is_absolute() or PureWindowsPath(directory).drive:
                raise ValueError("'diretorio' precisa ser relativo a origem.")
            original = source / relative / filename
            video = original.resolve()
            if not video.is_relative_to(source) or video.is_relative_to(destination):
                raise ValueError("Arquivo fora da origem ou dentro do destino.")
            if any(part.is_symlink() for part in [original, *original.parents]):
                raise ValueError("Links simbolicos nao sao aceitos.")
            if not video.is_file() or video.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Video inexistente ou formato nao suportado: {video}")
            target = destination / f"{order:02d}.{name}{video.suffix}"
            if len(target.name.encode("utf-16-le")) // 2 > 255:
                raise ValueError("Nome final excede o limite de 255 caracteres do Windows.")
            source_key, target_key = str(video).casefold(), str(target).casefold()
            if source_key in sources:
                raise ValueError(f"Arquivo de origem repetido: {video}")
            if target_key in targets or os.path.lexists(target):
                raise ValueError(f"Destino repetido ou ja existente: {target}")
            orders.add(order)
            sources.add(source_key)
            targets.add(target_key)
            plan.append((order, video, target))
        except ValueError as error:
            raise ValueError(f"Item {index}: {error}") from error
    return [(video, target) for _, video, target in sorted(plan)]


def move_exclusive(source: Path, target: Path) -> None:
    # A copia exclusiva funciona entre discos e nunca substitui um destino concorrente.
    created = False
    try:
        with target.open("xb") as output:
            created = True
            with source.open("rb") as input_stream:
                shutil.copyfileobj(input_stream, output)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    shutil.copystat(source, target)
    source.unlink()


def apply_manifest(manifest: Path, *, simulate: bool = False) -> int:
    plan = build_plan(manifest.resolve())
    for source, target in plan:
        print(f"{source} -> {target}")
    if simulate:
        print(f"Simulacao: {len(plan)} videos; nenhum arquivo movido.")
        return len(plan)
    plan[0][1].parent.mkdir(parents=True, exist_ok=True)
    for index, (source, target) in enumerate(plan, 1):
        move_exclusive(source, target)
        print(f"[{index}/{len(plan)}] Movido: {target.name}")
    return len(plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("listar", help="Catalogar videos recursivamente em YAML.")
    listing.add_argument("origem", type=Path)
    listing.add_argument(
        "--yaml",
        required=True,
        type=Path,
        help="YAML novo; caminho relativo a origem. Nao sobrescreve.",
    )
    listing.add_argument("--destino", type=Path, help="Padrao: pasta irma <origem>_organizados.")
    applying = commands.add_parser("aplicar", help="Validar, renomear e mover os videos.")
    applying.add_argument("--yaml", required=True, type=Path)
    applying.add_argument("--simular", action="store_true", help="Validar e mostrar sem mover.")
    args = parser.parse_args(argv)
    try:
        if args.command == "listar":
            list_videos(args.origem, args.yaml, args.destino)
        else:
            apply_manifest(args.yaml, simulate=args.simular)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido. Confira os arquivos ja movidos antes de retomar.", file=sys.stderr)
        return 130
    return 0
