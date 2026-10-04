"""Executa edicao de videos e extracao do audio dos cortes em lote."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edicao_video.cortar_trechos_fala import (
    add_editing_arguments,
    analyze_video,
    discover_videos,
    generate_cuts,
    require_ffmpeg,
)
from extracao_audio.extrair_audio import extract_audio, has_audio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Corta os videos de uma pasta e extrai o audio dos cortes para "
            "<saida>/audios_extraidos, sem confirmacoes interativas."
        )
    )
    parser.add_argument("entrada", type=Path, help="Diretorio dos videos; inclui subpastas.")
    parser.add_argument(
        "--saida",
        "--destino-videos",
        required=True,
        type=Path,
        help="Destino dos cortes. Os audios ficam na subpasta audios_extraidos.",
    )
    add_editing_arguments(parser)
    return parser


def run_pipeline(args: argparse.Namespace) -> int:
    source = args.entrada.expanduser().resolve()
    destination = args.saida.expanduser().resolve()
    if not source.is_dir():
        raise RuntimeError(f"Diretorio de entrada inexistente ou invalido: {source}")
    if source == destination or source.is_relative_to(destination):
        raise RuntimeError("O destino nao pode ser igual a entrada nem conter a pasta de entrada.")
    if destination.exists() and not destination.is_dir():
        raise RuntimeError(f"O destino precisa ser um diretorio: {destination}")

    require_ffmpeg()
    # A lista e fechada antes de gerar arquivos. Exclui tambem saidas de lotes anteriores.
    videos = [
        video
        for video in discover_videos([source])
        if not video.resolve().is_relative_to(destination)
    ]
    if not videos:
        raise RuntimeError("Nenhum video suportado foi encontrado na entrada.")

    args.quality = (
        args.quality if args.quality is not None else (18 if args.encoder == "libx264" else 24)
    )
    audio_root = destination / "audios_extraidos"
    audio_root.mkdir(parents=True, exist_ok=True)
    manifest = destination / "relatorio_pipeline.json"
    # Reservado para audios: impede que uma pasta de entrada homonima misture os destinos.
    if any(video.relative_to(source).parts[0].casefold() == "audios_extraidos" for video in videos):
        raise RuntimeError("A entrada contem videos em 'audios_extraidos'; renomeie essa subpasta.")

    records: list[dict] = []
    summary = {
        "entrada": str(source),
        "destino_videos": str(destination),
        "destino_audios": str(audio_root),
        "configuracao": {
            name: getattr(args, name)
            for name in (
                "encoder",
                "quality",
                "noise",
                "min_silence",
                "padding",
                "merge_gap",
                "min_segment",
                "overwrite",
            )
        },
        "videos": records,
    }

    def save_summary() -> None:
        manifest.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"Videos encontrados: {len(videos)}")
    print(f"Destino dos audios: {audio_root}")
    for index, video in enumerate(videos, start=1):
        print(f"\n[{index}/{len(videos)}] {video}")
        record = {"video": str(video), "status": "em_andamento", "cortes": [], "audios": []}
        records.append(record)
        try:
            if not has_audio(video):
                record["status"] = "sem_audio"
                print("  Ignorado: video sem faixa de audio.")
                continue

            # Inclui a extensao no nome da saida para distinguir aula.mp4 de aula.mkv.
            video_args = argparse.Namespace(**vars(args))
            video_args.saida = destination / video.relative_to(source).parent
            plan = analyze_video(video, video_args, output_name=video.name)
            record["tempos"] = str(plan.times_file)
            if not plan.segments:
                record["status"] = "sem_trechos"
                continue

            outputs = [
                plan.output_dir / f"{video.stem}_trecho_{number:03d}.mp4"
                for number in range(1, len(plan.segments) + 1)
            ]
            audios = [
                audio_root / path.relative_to(destination).with_suffix(".m4a") for path in outputs
            ]
            if not args.overwrite:
                existing = next((path for path in [*outputs, *audios] if path.exists()), None)
                if existing is not None:
                    raise RuntimeError(
                        f"Arquivo ja existe: {existing}. Use --overwrite para substituir."
                    )

            cuts = generate_cuts(plan, video_args)
            record["cortes"] = [str(cut) for cut in cuts]
            # Extrai somente os cortes desta execucao, nunca varre o destino em busca de videos.
            for cut, audio in zip(cuts, audios):
                audio.parent.mkdir(parents=True, exist_ok=True)
                extract_audio(cut, audio, reencode=False, overwrite=args.overwrite)
                record["audios"].append(str(audio))
                print(f"  Audio: {audio}")
            record["status"] = "concluido"
        except (OSError, RuntimeError) as exc:
            record["status"] = "erro"
            record["erro"] = str(exc)
            print(f"Erro: {exc}", file=sys.stderr)
        except KeyboardInterrupt:
            record["status"] = "interrompido"
            raise
        finally:
            save_summary()

    failures = sum(record["status"] == "erro" for record in records)
    completed = sum(record["status"] == "concluido" for record in records)
    skipped = len(records) - failures - completed
    print(f"\nConcluidos: {completed}; ignorados: {skipped}; falhas: {failures}.")
    print(f"Relatorio: {manifest}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_pipeline(args)
    except (OSError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExecucao interrompida pelo usuario.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
