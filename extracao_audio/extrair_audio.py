"""Extrai o audio de varios videos para uma pasta de destino.

Exemplo:
    uv run -m extracao_audio "C:\\videos" --saida "D:\\audios"

Por padrao, o audio e copiado sem recodificacao para M4A. Use --reencode
quando o codec original nao for compativel com o arquivo de saida.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED_EXTENSIONS = {".trec", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mts", ".m2ts"}


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "FFmpeg nao encontrado no PATH. Instale o FFmpeg e confirme com "
            f"'{missing[0]} -version'."
        )


def discover_videos(input_dir: Path) -> list[Path]:
    if input_dir.is_file():
        if input_dir.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [input_dir]
        return []

    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def has_audio(video: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(video),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao inspecionar '{video}'.\n{result.stderr.strip()}")
    return bool(result.stdout.strip())


def extract_audio(video: Path, output: Path, reencode: bool, overwrite: bool) -> None:
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
    ]

    if reencode:
        command += ["-c:a", "aac", "-b:a", "192k"]
    else:
        command += ["-c:a", "copy"]

    command += ["-movflags", "+faststart", "-y" if overwrite else "-n", str(output)]
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or "sem detalhes adicionais"
        raise RuntimeError(f"Falha ao extrair '{video}'.\n{details}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai o audio de um video ou de todos os videos de uma pasta."
    )
    parser.add_argument(
        "entrada", type=Path, help="Arquivo de video ou pasta que contem os videos."
    )
    parser.add_argument(
        "--saida",
        required=True,
        type=Path,
        help="Pasta onde os arquivos de audio serao salvos.",
    )
    parser.add_argument(
        "--reencode",
        action="store_true",
        help="Recodifica o audio para AAC 192 kbps em vez de copiar o stream.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Substitui arquivos de audio que ja existirem.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        require_ffmpeg()
        if not args.entrada.exists():
            raise RuntimeError(f"O arquivo ou pasta de entrada nao existe: {args.entrada}")

        videos = discover_videos(args.entrada)
        if not videos:
            raise RuntimeError("Nenhum video suportado foi encontrado na pasta.")

        args.saida.mkdir(parents=True, exist_ok=True)
        print(f"Videos encontrados: {len(videos)}")
        extracted = 0
        skipped = 0

        for video in videos:
            if args.entrada.is_file():
                relative = Path(video.name).with_suffix(".m4a")
            else:
                relative = video.relative_to(args.entrada).with_suffix(".m4a")
            output = args.saida / relative
            output.parent.mkdir(parents=True, exist_ok=True)

            if not has_audio(video):
                print(f"Ignorado sem audio: {video}")
                skipped += 1
                continue

            print(f"Extraindo: {video}")
            extract_audio(video, output, args.reencode, args.overwrite)
            print(f"  Salvo em: {output}")
            extracted += 1

        print(f"Concluido. Audios extraidos: {extracted}; ignorados: {skipped}.")
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExecucao interrompida pelo usuario.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
