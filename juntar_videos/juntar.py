"""Junta dois ou mais videos na ordem do YAML, sem recodificar os streams."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath

import yaml

# Bitrate, duracao, numero de frames e tags podem diferir entre os trechos.
# A configuracao de decodificacao e as bases de tempo precisam ser compativeis.
STREAM_FIELDS = (
    "codec_type",
    "codec_name",
    "profile",
    "level",
    "time_base",
    "width",
    "height",
    "pix_fmt",
    "sample_aspect_ratio",
    "field_order",
    "r_frame_rate",
    "avg_frame_rate",
    "color_range",
    "color_space",
    "color_transfer",
    "color_primaries",
    "sample_fmt",
    "sample_rate",
    "channels",
    "channel_layout",
    "bits_per_sample",
    "bits_per_raw_sample",
    "extradata_hash",
)


def required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo '{field}' precisa ser um texto preenchido.")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValueError(f"Campo '{field}' contem quebra de linha ou caractere nulo.")
    return value


def resolve_root(value: str, manifest: Path) -> Path:
    path = Path(value).expanduser()
    return (manifest.parent / path).resolve()


def load_manifest(manifest: Path) -> tuple[list[Path], Path]:
    manifest = manifest.expanduser().resolve()
    with manifest.open(encoding="utf-8-sig") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("O YAML precisa conter origem, saida e arquivos.")
    source = resolve_root(required_text(data, "origem"), manifest)
    output = resolve_root(required_text(data, "saida"), manifest)
    if not source.is_dir():
        raise ValueError(f"Diretorio de origem inexistente ou invalido: {source}")
    entries = data.get("arquivos")
    if not isinstance(entries, list) or len(entries) < 2:
        raise ValueError("'arquivos' precisa ser uma lista com pelo menos dois videos.")
    videos = []
    for index, entry in enumerate(entries, 1):
        value = required_text({"arquivo": entry}, "arquivo")
        relative = Path(value.replace("\\", "/"))
        if relative.is_absolute() or PureWindowsPath(value).anchor:
            raise ValueError(f"Item {index}: o arquivo precisa ser relativo a origem.")
        video = (source / relative).resolve()
        if not video.is_relative_to(source):
            raise ValueError(f"Item {index}: caminho fora da origem: {value}")
        if not video.is_file():
            raise ValueError(f"Item {index}: video inexistente ou invalido: {video}")
        if output == video:
            raise ValueError("A saida precisa ser diferente de todos os arquivos de entrada.")
        videos.append(video)
    if os.path.lexists(output):
        raise ValueError(f"A saida ja existe; escolha outro nome: {output}")
    if not output.suffix:
        raise ValueError("A saida precisa ter extensao de conteiner, como .mp4 ou .mkv.")
    for parent in output.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"O diretorio de saida contem um caminho que nao e pasta: {parent}")
    return videos, output


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            f"Instale FFmpeg e ffprobe no PATH. Nao encontrado: {', '.join(missing)}"
        )


def probe_streams(video: Path) -> list[dict]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_data_hash",
            "sha256",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao inspecionar '{video}':\n{result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") if isinstance(data, dict) else None
        if not isinstance(streams, list) or not all(isinstance(s, dict) for s in streams):
            raise ValueError("lista de streams invalida")
    except ValueError as error:
        raise RuntimeError(f"Resposta invalida do ffprobe para '{video}': {error}") from error
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError(f"Arquivo sem stream de video: {video}")
    return streams


def validate_compatibility(videos: list[Path]) -> None:
    reference = probe_streams(videos[0])
    for video in videos[1:]:
        streams = probe_streams(video)
        differences = []
        if len(streams) != len(reference):
            differences.append(f"quantidade de streams: {len(streams)} != {len(reference)}")
        for index, (actual, expected) in enumerate(zip(streams, reference)):
            for field in STREAM_FIELDS:
                if actual.get(field) != expected.get(field):
                    differences.append(
                        f"stream {index}, {field}: {actual.get(field)!r} != {expected.get(field)!r}"
                    )
        if differences:
            raise ValueError(
                f"Video incompativel: {video}\nReferencia: {videos[0]}\n"
                + "\n".join(differences)
                + "\nA juncao exige streams compativeis; nao sera feita recodificacao."
            )


def concat_entry(video: Path) -> str:
    # Sintaxe de quoting do FFmpeg (nao de shell): fecha, escapa e reabre o apostrofo.
    value = video.as_posix()
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValueError(f"Caminho invalido para a lista concat: {video!s}")
    return "file '" + value.replace("'", "'\\''") + "'\n"


def publish_exclusive(temporary: Path, output: Path) -> None:
    if os.name == "nt":
        # No Windows, rename falha se o destino existir. Mesmo disco do temporario.
        temporary.rename(output)
    else:
        # Em POSIX, rename sobrescreveria; link cria o nome final de forma exclusiva.
        os.link(temporary, output)
        temporary.unlink()


def join_videos(manifest: Path, *, simulate: bool = False) -> Path:
    videos, output = load_manifest(manifest)
    require_ffmpeg()
    validate_compatibility(videos)
    # Validar os caminhos da lista tambem em simulacoes, antes de criar diretorios.
    concat_text = "ffconcat version 1.0\n" + "".join(concat_entry(video) for video in videos)
    for index, video in enumerate(videos, 1):
        print(f"{index:02d}. {video}")
    print(f"Saida: {output}")
    if simulate:
        print("Simulacao concluida: entradas compativeis; nenhum video gerado.")
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".juntar_videos-", dir=output.parent) as directory:
        temp_root = Path(directory)
        listing = temp_root / "entradas.ffconcat"
        listing.write_text(concat_text, encoding="utf-8")
        temporary = temp_root / f"resultado{output.suffix}"
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-map",
            "0",
            "-c",
            "copy",
            "-n",
            str(temporary),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Falha ao juntar os videos sem recodificacao. Confira os arquivos e se o "
                f"conteiner '{output.suffix}' suporta todos os streams.\n{result.stderr.strip()}"
            )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("FFmpeg nao gerou um arquivo de saida valido.")
        publish_exclusive(temporary, output)
    print(f"Video gerado sem recodificacao: {output}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yaml", required=True, type=Path, help="YAML com origem, saida e arquivos."
    )
    parser.add_argument("--simular", action="store_true", help="Validar e exibir sem gerar video.")
    args = parser.parse_args(argv)
    try:
        join_videos(args.yaml, simulate=args.simular)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido. Arquivos originais preservados.", file=sys.stderr)
        return 130
    return 0
