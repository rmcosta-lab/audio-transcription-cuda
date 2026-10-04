"""Transcreve um audio ou uma pasta de audios para Markdown."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

DEFAULT_OUTPUT = Path("transcricao-audio-instrucao-handson.md")
SUPPORTED_AUDIO_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcreve um arquivo ou uma pasta de audios usando faster-whisper."
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="Arquivo de audio ou diretorio de entrada (inclui subpastas).",
    )
    parser.add_argument(
        "-o",
        "--output",
        "--saida",
        type=Path,
        help=(
            "Arquivo Markdown para entrada individual ou diretorio de destino para lote. "
            f"Obrigatorio para lote; padrao individual: {DEFAULT_OUTPUT}"
        ),
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
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="No lote, substitui transcricoes existentes em vez de ignora-las.",
    )
    return parser.parse_args(argv)


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


def load_model(args: argparse.Namespace):
    # Carregamento tardio permite usar --help sem instalar o extra de transcricao.
    try:
        import truststore

        truststore.inject_into_ssl()
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Dependencias de transcricao ausentes. Execute com "
            "'uv run --extra transcricao -m transcrever_audio <audio>'."
        ) from exc

    return WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )


def transcribe_file(model, audio: Path, output: Path, args: argparse.Namespace) -> None:
    """Compartilha a transcricao individual entre os dois modos de execucao."""
    started_at = time.perf_counter()
    language = args.language.strip() or None
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")

    print(f"Arquivo gerado: {output.resolve()}")
    print(f"Segmentos: {len(segments)}")
    print(f"Duracao aproximada: {format_timestamp(getattr(info, 'duration', 0) or 0)}")
    print(f"Tempo total de transcricao: {format_timestamp(time.perf_counter() - started_at)}")


def plan_batch(source: Path, destination: Path) -> list[tuple[Path, Path]]:
    """Preserva subpastas e valida nomes antes de carregar o modelo ou gravar saidas."""
    if destination.exists() and not destination.is_dir():
        raise RuntimeError(f"O destino do lote precisa ser um diretorio: {destination}")

    plans: list[tuple[Path, Path]] = []
    owners: dict[Path, Path] = {}
    nested_destination = destination != source and destination.is_relative_to(source)
    for audio in sorted(source.rglob("*")):
        if not audio.is_file() or audio.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            continue
        if nested_destination and audio.resolve().is_relative_to(destination):
            continue
        output = destination / audio.relative_to(source).with_suffix(".md")
        if output in owners:
            raise RuntimeError(
                f"Conflito de nomes: '{owners[output]}' e '{audio}' gerariam '{output}'. "
                "Renomeie um dos audios ou coloque-os em subpastas distintas."
            )
        if output.exists() and not output.is_file():
            raise RuntimeError(f"O caminho de uma transcricao ja existe como diretorio: {output}")
        owners[output] = audio
        plans.append((audio, output))
    if not plans:
        raise RuntimeError(f"Nenhum arquivo de audio suportado foi encontrado: {source}")
    return plans


def run(args: argparse.Namespace) -> int:
    source = args.audio.expanduser().resolve()
    if source.is_file():
        output = (args.output or DEFAULT_OUTPUT).expanduser().resolve()
        if output == source:
            raise RuntimeError("O arquivo de saida nao pode ser o proprio audio de entrada.")
        if output.is_dir():
            raise RuntimeError(f"Informe um arquivo Markdown para a saida individual: {output}")
        transcribe_file(load_model(args), source, output, args)
        return 0
    if not source.is_dir():
        raise FileNotFoundError(f"Arquivo ou diretorio de audio nao encontrado: {source}")
    if args.output is None:
        raise RuntimeError("Para transcrever em lote, informe o diretorio de destino com -o.")

    destination = args.output.expanduser().resolve()
    plans = plan_batch(source, destination)
    print(f"Audios encontrados: {len(plans)}")
    print(f"Destino das transcricoes: {destination}")
    started_at = time.perf_counter()
    model = None
    completed = skipped = failed = 0
    for index, (audio, output) in enumerate(plans, start=1):
        print(f"\n[{index}/{len(plans)}] {audio}")
        if output.exists() and not args.overwrite:
            print(f"Ignorado: transcricao ja existe: {output}")
            skipped += 1
            continue
        # Um unico modelo para todo o lote. Falhas na inicializacao encerram a execucao.
        if model is None:
            model = load_model(args)
        try:
            transcribe_file(model, audio, output, args)
            completed += 1
        except Exception as exc:
            # Inclui falhas de decodificacao e de iteracao dos segmentos do Whisper.
            print(f"Erro ao transcrever '{audio}': {exc}", file=sys.stderr)
            failed += 1

    print(f"\nConcluidos: {completed}; ignorados: {skipped}; falhas: {failed}.")
    print(f"Tempo total do lote: {format_timestamp(time.perf_counter() - started_at)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        status = run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        status = 1
    except KeyboardInterrupt:
        print("\nExecucao interrompida pelo usuario.", file=sys.stderr)
        status = 130
    # Propaga falhas para o terminal em qualquer modo de execucao.
    if status:
        raise SystemExit(status)


if __name__ == "__main__":
    main()
