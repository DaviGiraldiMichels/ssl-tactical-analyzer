"""
Match Analytics Report Generator for RoboCup SSL.
Generates comprehensive terminal summaries and standalone HTML dashboards.
"""

from pathlib import Path
from typing import Dict, List, Optional

from src.metrics.passing import PassingStats
from src.metrics.pitch_control import SpatialSnapshotMetrics
from src.metrics.possession import PossessionStats
from src.metrics.xg import ShotStats


class TacticalReportGenerator:
    """Generates formatted reports aggregating all tactical metrics."""

    def __init__(
        self,
        possession: PossessionStats,
        yellow_passing: PassingStats,
        blue_passing: PassingStats,
        yellow_shots: ShotStats,
        blue_shots: ShotStats,
        spatial_history: Optional[List[SpatialSnapshotMetrics]] = None,
        yellow_team_name: str = "Yellow Team",
        blue_team_name: str = "Blue Team",
    ):
        self.possession = possession
        self.yp = yellow_passing
        self.bp = blue_passing
        self.ys = yellow_shots
        self.bs = blue_shots
        self.spatial = spatial_history or []
        self.yellow_name = yellow_team_name
        self.blue_name = blue_team_name

    def generate_terminal_summary(self) -> str:
        """Returns a formatted plain text table for CLI output."""
        lines = [
            "=" * 70,
            f"          RELATÓRIO TÁTICO PÓS-JOGO - ROBOCUP SSL",
            f"          {self.yellow_name} (Amarelo) vs {self.blue_name} (Azul)",
            "=" * 70,
            f"Duração Total Analisada: {self.possession.total_time_sec:.1f} s",
            "-" * 70,
            f"{'MÉTRICA':<35} | {self.yellow_name:^15} | {self.blue_name:^15}",
            "-" * 70,
            f"{'Posse de Bola (Tempo)':<35} | {self.possession.yellow_time_sec:>13.1f}s | {self.possession.blue_time_sec:>13.1f}s",
            f"{'Posse de Bola (%)':<35} | {self.possession.yellow_possession_pct:>14.1f}% | {self.possession.blue_possession_pct:>14.1f}%",
            f"{'  - Terço Defensivo':<35} | {self.possession.yellow_defensive_sec:>13.1f}s | {self.possession.blue_defensive_sec:>13.1f}s",
            f"{'  - Terço Central':<35} | {self.possession.yellow_middle_sec:>13.1f}s | {self.possession.blue_middle_sec:>13.1f}s",
            f"{'  - Terço Ofensivo':<35} | {self.possession.yellow_offensive_sec:>13.1f}s | {self.possession.blue_offensive_sec:>13.1f}s",
            f"{'Perdas de Posse (Turnovers)':<35} | {self.possession.yellow_turnovers:>15} | {self.possession.blue_turnovers:>15}",
            "-" * 70,
            f"{'Passes Totais':<35} | {self.yp.total_passes:>15} | {self.bp.total_passes:>15}",
            f"{'Passes Certos':<35} | {self.yp.completed_passes:>15} | {self.bp.completed_passes:>15}",
            f"{'Acurácia de Passe (%)':<35} | {self.yp.accuracy_pct:>14.1f}% | {self.bp.accuracy_pct:>14.1f}%",
            f"{'Passes Interceptados':<35} | {self.yp.intercepted_passes:>15} | {self.bp.intercepted_passes:>15}",
            "-" * 70,
            f"{'Finalizações (Chutes)':<35} | {self.ys.total_shots:>15} | {self.bs.total_shots:>15}",
            f"{'Expected Goals (xG Total)':<35} | {self.ys.total_xg:>15.2f} | {self.bs.total_xg:>15.2f}",
            "=" * 70,
        ]

        if self.spatial:
            avg_y_ctrl = sum(s.yellow_control_pct for s in self.spatial) / len(self.spatial)
            avg_b_ctrl = sum(s.blue_control_pct for s in self.spatial) / len(self.spatial)
            avg_y_comp = sum(s.yellow_compactness_radius for s in self.spatial) / len(self.spatial)
            avg_b_comp = sum(s.blue_compactness_radius for s in self.spatial) / len(self.spatial)
            lines.extend([
                f"{'Domínio Espacial Médio (Pitch Ctrl)':<35} | {avg_y_ctrl:>14.1f}% | {avg_b_ctrl:>14.1f}%",
                f"{'Compactação Média (Raio Spread)':<35} | {avg_y_comp:>13.2f}m | {avg_b_comp:>13.2f}m",
                "=" * 70,
            ])

        return "\n".join(lines)

    def generate_html_report(self, output_path: str):
        """Generates a standalone modern HTML tactical dashboard."""
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        avg_y_ctrl = 50.0
        avg_b_ctrl = 50.0
        if self.spatial:
            avg_y_ctrl = sum(s.yellow_control_pct for s in self.spatial) / len(self.spatial)
            avg_b_ctrl = sum(s.blue_control_pct for s in self.spatial) / len(self.spatial)

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>SSL Analytics - {self.yellow_name} vs {self.blue_name}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      padding: 24px 0;
      border-bottom: 2px solid #334155;
      margin-bottom: 32px;
    }}
    h1 {{
      margin: 0 0 8px 0;
      color: #38bdf8;
      font-size: 28px;
    }}
    .subtitle {{
      color: #94a3b8;
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 20px;
      margin-bottom: 28px;
    }}
    .card {{
      background: #1e293b;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
      border: 1px solid #334155;
    }}
    .card h2 {{
      margin-top: 0;
      font-size: 18px;
      color: #cbd5e1;
      border-bottom: 1px solid #475569;
      padding-bottom: 8px;
    }}
    .stat-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 12px 0;
      font-size: 15px;
    }}
    .bar-container {{
      display: flex;
      height: 24px;
      border-radius: 6px;
      overflow: hidden;
      margin: 14px 0;
      background: #475569;
    }}
    .bar-yellow {{
      background: #eab308;
      color: #000;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      transition: width 0.3s;
    }}
    .bar-blue {{
      background: #3b82f6;
      color: #fff;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      transition: width 0.3s;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }}
    th, td {{
      padding: 10px;
      text-align: left;
      border-bottom: 1px solid #334155;
      font-size: 14px;
    }}
    th {{
      color: #94a3b8;
      font-weight: 600;
    }}
    .badge-y {{
      color: #eab308;
      font-weight: 600;
    }}
    .badge-b {{
      color: #60a5fa;
      font-weight: 600;
    }}
    footer {{
      text-align: center;
      padding: 20px;
      color: #64748b;
      font-size: 13px;
      border-top: 1px solid #1e293b;
      margin-top: 40px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Sistema de Avaliação Tática SSL</h1>
      <div class="subtitle">UDESC CEPLAN | PROBIC NPP3262-2022 | {self.yellow_name} (Amarelo) vs {self.blue_name} (Azul)</div>
    </header>

    <div class="grid">
      <!-- Posse de Bola -->
      <div class="card">
        <h2>Posse de Bola e Controle</h2>
        <div class="stat-row">
          <span class="badge-y">{self.yellow_name}: {self.possession.yellow_possession_pct:.1f}%</span>
          <span class="badge-b">{self.blue_name}: {self.possession.blue_possession_pct:.1f}%</span>
        </div>
        <div class="bar-container">
          <div class="bar-yellow" style="width: {self.possession.yellow_possession_pct:.1f}%">{self.possession.yellow_possession_pct:.0f}%</div>
          <div class="bar-blue" style="width: {self.possession.blue_possession_pct:.1f}%">{self.possession.blue_possession_pct:.0f}%</div>
        </div>
        <div class="stat-row">
          <span>Tempo Efetivo Amarelo</span>
          <span>{self.possession.yellow_time_sec:.1f} s</span>
        </div>
        <div class="stat-row">
          <span>Tempo Efetivo Azul</span>
          <span>{self.possession.blue_time_sec:.1f} s</span>
        </div>
        <div class="stat-row">
          <span>Disputa / Bola Contestada</span>
          <span>{self.possession.contested_time_sec:.1f} s</span>
        </div>
        <div class="stat-row">
          <span>Turnovers (Perdas de Posse)</span>
          <span>{self.possession.yellow_turnovers} Y / {self.possession.blue_turnovers} B</span>
        </div>
      </div>

      <!-- Passes -->
      <div class="card">
        <h2>Passes e Distribuição</h2>
        <div class="stat-row">
          <span class="badge-y">Acurácia Amarelo</span>
          <span>{self.yp.accuracy_pct:.1f}% ({self.yp.completed_passes}/{self.yp.total_passes})</span>
        </div>
        <div class="bar-container">
          <div class="bar-yellow" style="width: {self.yp.accuracy_pct:.1f}%">{self.yp.accuracy_pct:.0f}%</div>
        </div>
        <div class="stat-row">
          <span class="badge-b">Acurácia Azul</span>
          <span>{self.bp.accuracy_pct:.1f}% ({self.bp.completed_passes}/{self.bp.total_passes})</span>
        </div>
        <div class="bar-container">
          <div class="bar-blue" style="width: {self.bp.accuracy_pct:.1f}%">{self.bp.accuracy_pct:.0f}%</div>
        </div>
        <div class="stat-row">
          <span>Interceptações Sofridas</span>
          <span>{self.yp.intercepted_passes} Y / {self.bp.intercepted_passes} B</span>
        </div>
      </div>

      <!-- Finalizações & xG -->
      <div class="card">
        <h2>Ataque & Expected Goals (xG)</h2>
        <div class="stat-row">
          <span>Finalizações Totais</span>
          <span><b class="badge-y">{self.ys.total_shots}</b> vs <b class="badge-b">{self.bs.total_shots}</b></span>
        </div>
        <div class="stat-row">
          <span>Expected Goals (xG Acumulado)</span>
          <span><b class="badge-y">{self.ys.total_xg:.2f}</b> vs <b class="badge-b">{self.bs.total_xg:.2f}</b></span>
        </div>
        <div class="stat-row">
          <span>xG Médio por Finalização</span>
          <span>
            {f"{self.ys.total_xg / self.ys.total_shots:.2f}" if self.ys.total_shots else "0.00"} Y vs 
            {f"{self.bs.total_xg / self.bs.total_shots:.2f}" if self.bs.total_shots else "0.00"} B
          </span>
        </div>
        <div class="stat-row">
          <span>Domínio Espacial Médio (Pitch Control)</span>
          <span>{avg_y_ctrl:.1f}% Y / {avg_b_ctrl:.1f}% B</span>
        </div>
      </div>
    </div>

    <!-- Tabela de Passes por Robô -->
    <div class="card">
      <h2>Volume de Passes e Recompensas por Robô (Amarelo)</h2>
      <table>
        <thead>
          <tr>
            <th>ID do Robô</th>
            <th>Passes Executados</th>
            <th>Recepções Concluídas</th>
            <th>Tempo em Posse (s)</th>
          </tr>
        </thead>
        <tbody>
"""
        yellow_bot_ids = sorted(
            set(list(self.yp.passes_by_robot.keys()) + list(self.possession.robot_possession_sec["yellow"].keys()))
        )
        if not yellow_bot_ids:
            html += "<tr><td colspan='4'>Nenhum dado registrado para esta equipe.</td></tr>"
        for b_id in yellow_bot_ids:
            passes = self.yp.passes_by_robot.get(b_id, 0)
            receptions = self.yp.receptions_by_robot.get(b_id, 0)
            pos_sec = self.possession.robot_possession_sec["yellow"].get(b_id, 0.0)
            html += f"""
          <tr>
            <td><b>Robô #{b_id}</b></td>
            <td>{passes}</td>
            <td>{receptions}</td>
            <td>{pos_sec:.2f} s</td>
          </tr>
"""

        html += f"""
        </tbody>
      </table>
    </div>

    <footer>
      Relatório gerado automaticamente pelo Sistema de Análise de Dados e Avaliação Tática SSL | UDESC CEPLAN 2026/2027
    </footer>
  </div>
</body>
</html>
"""
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html)
