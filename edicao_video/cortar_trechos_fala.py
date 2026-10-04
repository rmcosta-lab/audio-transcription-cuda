"""Detecta fala em videos e salva cada trecho em um arquivo separado.

Exemplo:
    uv run -m edicao_video \
        "C:\\videos\\aula.mp4" \
        --saida "D:\\videos\\cortes"

O detector usa o filtro silencedetect do FFmpeg. Os parametros podem ser
ajustados para lidar com ruido de fundo ou com pausas curtas entre frases.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")
SUPPORTED_EXTENSIONS = {".trec", ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mts", ".m2ts"}


@dataclass
class VideoPlan:
    video: Path
    duration: float
    segments: list[tuple[float, float]]
    output_dir: Path
    times_file: Path


def run_command(
    command: list[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture_output,
        check=False,
    )


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError(
            "FFmpeg nao encontrado no PATH. Instale o FFmpeg e confirme com "
            f"'{missing[0]} -version'."
        )


def get_duration(video: Path) -> float:
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Nao foi possivel ler a duracao de '{video}'.\n{result.stderr.strip()}")

    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Duracao invalida retornada para '{video}'.") from exc

    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError(f"A duracao de '{video}' e invalida: {duration}.")
    return duration


def detect_speech(
    video: Path,
    duration: float,
    noise: str,
    min_silence: float,
    padding: float,
    merge_gap: float,
    min_segment: float,
) -> list[tuple[float, float]]:
    """Retorna intervalos com audio acima do limiar de silencio."""
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-nostats",
            "-i",
            str(video),
            "-vn",
            "-af",
            f"silencedetect=noise={noise}:d={min_silence}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao analisar o audio de '{video}'.\n{result.stderr.strip()}")

    speech: list[tuple[float, float]] = []
    current_start = 0.0
    in_silence = False

    for line in result.stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            silence_start = float(start_match.group(1))
            if not in_silence and silence_start > current_start:
                speech.append((current_start, min(silence_start, duration)))
            in_silence = True
            continue

        end_match = SILENCE_END_RE.search(line)
        if end_match:
            current_start = max(0.0, min(float(end_match.group(1)), duration))
            in_silence = False

    if not in_silence and current_start < duration:
        speech.append((current_start, duration))

    if not speech:
        return []

    padded = [
        (max(0.0, start - padding), min(duration, end + padding))
        for start, end in speech
        if end - start >= min_segment
    ]
    if not padded:
        return []

    merged: list[list[float]] = [[padded[0][0], padded[0][1]]]
    for start, end in padded[1:]:
        if start <= merged[-1][1] + merge_gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return [(start, end) for start, end in merged if end - start >= min_segment]


def format_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_progress_time(key: str, value: str) -> float | None:
    """Converte timestamps do progresso do FFmpeg quando disponiveis."""
    try:
        if key in {"out_time_us", "out_time_ms"}:
            seconds = int(value) / 1_000_000
        elif key == "out_time":
            hours, minutes, seconds_value = value.split(":")
            seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds_value)
        else:
            return None
    except (TypeError, ValueError):
        return None

    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def cut_segment(
    video: Path,
    output: Path,
    start: float,
    end: float,
    encoder: str,
    quality: int,
    overwrite: bool,
) -> None:
    duration = end - start
    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(video),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        "scale=1920:-2,format=yuv420p",
    ]

    if encoder == "libx264":
        command += ["-c:v", encoder, "-preset", "fast", "-crf", str(quality)]
    else:
        command += [
            "-c:v",
            encoder,
            "-preset",
            "p3",
            "-rc",
            "vbr",
            "-cq",
            str(quality),
            "-b:v",
            "0",
        ]

    command += [
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-y" if overwrite else "-n",
        str(output),
    ]

    command[1:1] = ["-progress", "pipe:1", "-nostats"]
    started_at = time.monotonic()
    process = subprocess.Popen(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )

    current_time = 0.0
    speed = "N/A"
    assert process.stdout is not None
    for line in process.stdout:
        key, separator, value = line.strip().partition("=")
        if not separator:
            continue
        parsed_time = parse_progress_time(key, value)
        if parsed_time is not None:
            current_time = parsed_time
        if key == "speed":
            speed = value

        if key in {"out_time_us", "out_time_ms", "out_time", "speed"}:
            print(
                f"\r    time={format_time(min(current_time, duration))}/{format_time(duration)} "
                f"| speed={speed} | elapsed={format_elapsed(time.monotonic() - started_at)}",
                end="",
                flush=True,
            )

    process.stdout.close()
    details = process.stderr.read().strip() if process.stderr is not None else ""
    process.wait()
    print()
    if process.returncode != 0:
        details = details or "sem detalhes adicionais"
        raise RuntimeError(f"Falha ao gerar '{output}'.\n{details}")


def discover_videos(inputs: list[Path]) -> list[Path]:
    videos: list[Path] = []
    for item in inputs:
        if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            videos.append(item)
        elif item.is_dir():
            videos.extend(
                path
                for path in sorted(item.rglob("*"))
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        else:
            print(f"Aviso: entrada ignorada ou inexistente: {item}", file=sys.stderr)
    return list(dict.fromkeys(videos))


def analyze_video(
    video: Path, args: argparse.Namespace, *, output_name: str | None = None
) -> VideoPlan:
    name = output_name or video.stem
    times_file = args.saida / f"{name}_tempos.txt"
    if times_file.exists() and not args.overwrite:
        raise RuntimeError(f"Relatorio ja existe: {times_file}. Use --overwrite para substituir.")

    duration = get_duration(video)
    print(f"Analisando: {video}")
    segments = detect_speech(
        video,
        duration,
        args.noise,
        args.min_silence,
        args.padding,
        args.merge_gap,
        args.min_segment,
    )

    output_dir = args.saida / f"{name}_trechos"
    output_dir.mkdir(parents=True, exist_ok=True)

    with times_file.open("w", encoding="utf-8", newline="\n") as report:
        report.write(f"Video: {video}\n")
        report.write(f"Duracao: {format_time(duration)}\n")
        report.write(f"Trechos encontrados: {len(segments)}\n\n")

        for index, (start, end) in enumerate(segments, start=1):
            output = output_dir / f"{video.stem}_trecho_{index:03d}.mp4"
            print(f"  Trecho {index:03d}: {format_time(start)} -> {format_time(end)}")
            report.write(
                f"{index:03d}\t{format_time(start)}\t{format_time(end)}\t"
                f"{end - start:.3f}s\t{output}\n"
            )

    if not segments:
        print("  Nenhum trecho de fala encontrado.")
    print(f"  Relatorio: {times_file}")
    return VideoPlan(video, duration, segments, output_dir, times_file)


def generate_cuts(plan: VideoPlan, args: argparse.Namespace) -> list[Path]:
    outputs: list[Path] = []
    total = len(plan.segments)
    for index, (start, end) in enumerate(plan.segments, start=1):
        output = plan.output_dir / f"{plan.video.stem}_trecho_{index:03d}.mp4"
        print(f"Trecho {index:03d}/{total:03d}: {format_time(start)} -> {format_time(end)}")
        cut_segment(plan.video, output, start, end, args.encoder, args.quality, args.overwrite)
        outputs.append(output)
    return outputs


def nonnegative_seconds(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("Informe um numero finito maior ou igual a zero.")
    return number


def add_editing_arguments(parser: argparse.ArgumentParser) -> None:
    """Opcoes compartilhadas pelo editor independente e pelo pipeline."""
    parser.add_argument(
        "--encoder",
        choices=("libx264", "h264_nvenc", "hevc_nvenc"),
        default="libx264",
        help="Encoder de video. Padrao: libx264 (CPU).",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=None,
        help="CRF para libx264 ou CQ para NVENC. Padrao: 18 na CPU e 24 na GPU.",
    )
    parser.add_argument("--noise", default="-35dB", help="Limiar do silencio. Padrao: -35dB.")
    parser.add_argument(
        "--min-silence",
        type=nonnegative_seconds,
        default=5.0,
        help="Duracao minima de silencio em segundos. Padrao: 5.0.",
    )
    parser.add_argument(
        "--padding",
        type=nonnegative_seconds,
        default=0.25,
        help="Segundos adicionados antes e depois da fala. Padrao: 0.25.",
    )
    parser.add_argument(
        "--merge-gap",
        type=nonnegative_seconds,
        default=0.7,
        help="Une trechos separados por ate este intervalo. Padrao: 0.7.",
    )
    parser.add_argument(
        "--min-segment",
        type=nonnegative_seconds,
        default=60.0,
        help="Ignora trechos menores que este valor em segundos. Padrao: 60.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Substitui cortes que ja existirem.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detecta trechos com fala e gera um arquivo MP4 para cada trecho."
    )
    parser.add_argument(
        "entradas",
        nargs="+",
        type=Path,
        help="Arquivos de video ou pastas para procurar recursivamente.",
    )
    parser.add_argument(
        "--saida",
        required=True,
        type=Path,
        help="Pasta onde os cortes e os arquivos TXT serao salvos.",
    )
    add_editing_arguments(parser)
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Gera os cortes sem pedir confirmacao.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.quality = (
        args.quality if args.quality is not None else (18 if args.encoder == "libx264" else 24)
    )

    try:
        args.saida.mkdir(parents=True, exist_ok=True)
        require_ffmpeg()
        videos = discover_videos(args.entradas)
        if not videos:
            raise RuntimeError("Nenhum video suportado foi encontrado.")

        print(f"Videos encontrados: {len(videos)}")
        plans: list[VideoPlan] = []
        for video in videos:
            plans.append(analyze_video(video, args))

        total_segments = sum(len(plan.segments) for plan in plans)
        if total_segments == 0:
            print("Nenhum trecho de fala foi encontrado. Nenhum video foi gerado.")
            return 0

        print(f"\nAnalise concluida. Foram encontrados {total_segments} trecho(s).")
        print("Os arquivos TXT ja foram gerados.")
        answer = "y" if args.yes else ""
        if not args.yes:
            try:
                answer = input(
                    "Digite 'y' para gerar os videos cortados ou qualquer outra tecla para interromper: "
                )
            except EOFError:
                answer = ""

        if answer.strip().lower() != "y":
            print("Operacao interrompida. Nenhum video cortado foi gerado.")
            return 0

        for plan in plans:
            generate_cuts(plan, args)
    except (OSError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExecucao interrompida pelo usuario.", file=sys.stderr)
        return 130

    print("Concluido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
