# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "faster-whisper>=1.2.1",
#   "truststore>=0.10.0",
# ]
# ///

from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

# Use the Windows certificate store for downloads from Hugging Face.
import truststore

truststore.inject_into_ssl()

from faster_whisper import WhisperModel


DEFAULT_AUDIO = Path(
    r"C:\yourPath\audio-instrucao-handson.m4a"
)
DEFAULT_OUTPUT = Path("transcricao-audio-instrucao-handson.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcreve um arquivo de audio para Markdown usando faster-whisper."
    )
    parser.add_argument(
        "audio",
        nargs="?",
        type=Path,
        default=DEFAULT_AUDIO,
        help=f"Arquivo de audio de entrada. Padrao: {DEFAULT_AUDIO}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Arquivo Markdown de saida. Padrao: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Modelo Whisper a usar. Exemplos: tiny, base, small, medium, large-v3.",
    )
    parser.add_argument(
        "--language",
        default="pt",
        help="Idioma do audio. Use 'pt' para portugues. Deixe vazio para autodetectar.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Dispositivo de execucao. Use 'cpu' ou 'cuda' se houver GPU configurada.",
    )
    parser.add_argument(
        "--compute-type",
        default="int8",
        help="Tipo de computacao do faster-whisper. Para CPU, 'int8' costuma ser uma boa escolha.",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Desativa VAD, o filtro de trechos sem fala.",
    )
    return parser.parse_args()


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def build_markdown(
    audio: Path,
    output: Path,
    model_name: str,
    language: str | None,
    segments: list[tuple[float, float, str]],
) -> str:
    title = output.stem.replace("-", " ")
    transcript_text = " ".join(text for _, _, text in segments)

    lines = [
        f"# Transcricao - {title}",
        "",
        f"- Arquivo de origem: `{audio}`",
        f"- Modelo: `{model_name}`",
        f"- Idioma: `{language or 'auto'}`",
        f"- Gerado em: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Transcricao com timestamps",
        "",
    ]

    for start, end, text in segments:
        lines.append(f"[{format_timestamp(start)} - {format_timestamp(end)}] {text}")

    lines.extend(["", "## Texto corrido", "", transcript_text])
    return "\n".join(lines) + "\n"


def main() -> None:
    started_at = time.perf_counter()
    args = parse_args()
    audio = args.audio.expanduser().resolve()
    output = args.output.expanduser()

    if not audio.exists():
        raise FileNotFoundError(f"Arquivo de audio nao encontrado: {audio}")

    output.parent.mkdir(parents=True, exist_ok=True)

    language = args.language.strip() or None
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )
    raw_segments, info = model.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=not args.no_vad,
    )

    segments: list[tuple[float, float, str]] = []
    for segment in raw_segments:
        text = segment.text.strip()
        if text:
            segments.append((segment.start, segment.end, text))

    markdown = build_markdown(audio, output, args.model, language, segments)
    output.write_text(markdown, encoding="utf-8")

    print(f"Arquivo gerado: {output.resolve()}")
    print(f"Segmentos: {len(segments)}")
    print(f"Duracao aproximada: {format_timestamp(getattr(info, 'duration', 0) or 0)}")
    print(f"Tempo total de transcricao: {format_timestamp(time.perf_counter() - started_at)}")


if __name__ == "__main__":
    main()
