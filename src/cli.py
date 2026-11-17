"""
Command Line Interface (CLI) for SSL Tactical Analyzer.
Example:
    python3 -m src.cli --log data/sample_matches/synthetic_match.log.gz --output-dir output/
"""

import argparse
import sys
from pathlib import Path

from src.analyzer import SSLMatchAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="Sistema de Análise de Dados e Avaliação Tática para a Competição SSL"
    )
    parser.add_argument(
        "--log",
        required=True,
        help="Caminho para o arquivo de log SSL (.log ou .log.gz)",
    )
    parser.add_argument(
        "--division",
        default="B",
        choices=["A", "B", "a", "b"],
        help="Divisão da liga: B (padrão 6v6) ou A (11v11)",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Diretório onde relatórios HTML e imagens de pitch serão salvos",
    )
    parser.add_argument(
        "--save-pitch-frame",
        type=int,
        default=None,
        help="Índice opcional do snapshot para renderizar imagem PNG do campo 2D",
    )

    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"Erro: Arquivo de log não encontrado em '{log_path}'", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Carregando e analisando log: {log_path} (Divisão {args.division.upper()})...")
    analyzer = SSLMatchAnalyzer(division=args.division.upper())
    analyzer.analyze_log_file(str(log_path))

    html_report_path = out_dir / "relatorio_tatico.html"
    summary_text = analyzer.generate_report(output_html_path=str(html_report_path))

    print(summary_text)
    print(f"\n[+] Relatório HTML interativo salvo em: {html_report_path}")

    # Export keyframe if requested or if snapshots exist
    if args.save_pitch_frame is not None:
        png_path = out_dir / f"pitch_frame_{args.save_pitch_frame}.png"
        analyzer.export_keyframe_pitch(args.save_pitch_frame, str(png_path))
        print(f"[+] Imagem 2D do campo salva em: {png_path}")
    elif len(analyzer.snapshots) > 0:
        # Save middle frame by default
        mid = len(analyzer.snapshots) // 2
        png_path = out_dir / "pitch_overview.png"
        analyzer.export_keyframe_pitch(mid, str(png_path))
        print(f"[+] Imagem 2D do campo (overview frame #{mid}) salva em: {png_path}")


if __name__ == "__main__":
    main()
