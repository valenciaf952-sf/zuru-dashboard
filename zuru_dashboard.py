#!/usr/bin/env python3
"""
ZURU Partners Program 2026 - Dashboard Generator
=================================================
Este script se conecta a la base de datos MySQL, extrae los datos de producción
de operadores y genera un dashboard HTML interactivo.

Requisitos:
    pip install mysql-connector-python

Uso:
    python zuru_dashboard.py

El script generará un archivo 'zuru_dashboard.html' en la misma carpeta.
"""

import json
import os
import sys
from datetime import datetime

try:
    import mysql.connector
except ImportError:
    print("=" * 60)
    print("ERROR: Necesitas instalar mysql-connector-python")
    print("Ejecuta: pip install mysql-connector-python")
    print("=" * 60)
    sys.exit(1)

# ─── Configuración de Base de Datos ───
DB_CONFIG = {
    "host": "34.125.225.64",
    "database": "EMI",
    "user": "ddi",
    "password": "DDI4ever%",
}

# ─── Rangos de Score ───
PRIMA_RANGES = [
    (40000, float("inf"), 100),
    (30000, 40000, 90),
    (20000, 30000, 80),
    (15000, 20000, 70),
    (10000, 15000, 60),
]

GROWTH_RANGES = [
    (0.60, float("inf"), 100),
    (0.50, 0.60, 95),
    (0.40, 0.50, 90),
    (0.30, 0.40, 80),
    (0.25, 0.30, 70),
    (0.20, 0.25, 60),
    (0.15, 0.20, 50),
    (0.10, 0.15, 40),
]

WEIGHT_SCORE1 = 0.60
WEIGHT_SCORE2 = 0.40
MIN_PRIMA_DEFAULT = 10000
MIN_PRIMA_BY_PRODUCT = {
    "Chubb - Int.": 10000,
    "Lampe - Carga": 20000,
}
MIN_GROWTH = 0.10


def get_score1(prima):
    for low, high, score in PRIMA_RANGES:
        if prima >= low:
            return score
    return 0


def get_score2(growth):
    if growth is None or growth < MIN_GROWTH:
        return 0
    for low, high, score in GROWTH_RANGES:
        if growth >= low:
            return score
    return 0


def fetch_data():
    print("Conectando a la base de datos...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT
            DashboardPeOperador,
            DashboardPePrimaOperador,
            DashboardPeFechaEmision,
            DashboardPeProducto
        FROM DashboardPe
        WHERE DashboardPeOperador IS NOT NULL
          AND DashboardPeOperador != ''
          AND DashboardPeEstado = 'Activo'
          AND DashboardPeTipoNegocio = 'B2B2B'
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    print(f"Se obtuvieron {len(rows)} registros.")
    return rows


def process_data(rows):
    operators = {}
    products_set = set()

    # Determine the max month in 2026 data to use as cutoff for same-period comparison
    max_month_2026 = 0
    for row in rows:
        fecha = row["DashboardPeFechaEmision"]
        if isinstance(fecha, str):
            try:
                fecha = datetime.strptime(fecha, "%Y-%m-%d")
            except ValueError:
                try:
                    fecha = datetime.strptime(fecha, "%d/%m/%Y")
                except ValueError:
                    continue
        if hasattr(fecha, "year") and fecha.year == 2026:
            if fecha.month > max_month_2026:
                max_month_2026 = fecha.month

    if max_month_2026 == 0:
        max_month_2026 = 12

    print(f"Periodo de comparacion: Enero - Mes {max_month_2026} (mismo periodo 2025 vs 2026)")

    for row in rows:
        name = row["DashboardPeOperador"].strip()
        prima = float(row["DashboardPePrimaOperador"] or 0)
        fecha = row["DashboardPeFechaEmision"]
        producto = (row.get("DashboardPeProducto") or "Sin Producto").strip()

        if producto:
            products_set.add(producto)

        if isinstance(fecha, str):
            try:
                fecha = datetime.strptime(fecha, "%Y-%m-%d")
            except ValueError:
                try:
                    fecha = datetime.strptime(fecha, "%d/%m/%Y")
                except ValueError:
                    continue

        year = fecha.year if hasattr(fecha, "year") else None
        month = fecha.month if hasattr(fecha, "month") else None
        if year not in (2025, 2026):
            continue

        if name not in operators:
            operators[name] = {"name": name, "prima_2025": 0, "prima_2025_total": 0, "prima_2026": 0, "products": {}}
        if producto not in operators[name]["products"]:
            operators[name]["products"][producto] = {"prima_2025": 0, "prima_2025_total": 0, "prima_2026": 0}

        if year == 2025:
            # Always add to full-year total
            operators[name]["prima_2025_total"] += prima
            operators[name]["products"][producto]["prima_2025_total"] += prima
            # Only add to same-period if within cutoff
            if month <= max_month_2026:
                operators[name]["prima_2025"] += prima
                operators[name]["products"][producto]["prima_2025"] += prima
        elif year == 2026:
            operators[name]["prima_2026"] += prima
            operators[name]["products"][producto]["prima_2026"] += prima

    results = []
    for name, data in operators.items():
        p25 = round(data["prima_2025"], 2)
        p25_total = round(data["prima_2025_total"], 2)
        p26 = round(data["prima_2026"], 2)

        if p25 > 0:
            growth = round((p26 - p25) / p25, 4)
        else:
            growth = None

        score1 = get_score1(p26)
        score2 = get_score2(growth)
        score_final = round((score1 * WEIGHT_SCORE1) + (score2 * WEIGHT_SCORE2), 1)

        # Check eligibility per product: operator qualifies if ANY of their products meets its threshold
        eligible = False
        for pname, pdata in data["products"].items():
            threshold = MIN_PRIMA_BY_PRODUCT.get(pname, MIN_PRIMA_DEFAULT)
            if pdata["prima_2026"] >= threshold:
                eligible = True
                break

        meets_growth = growth is not None and growth >= MIN_GROWTH

        # Build product breakdown list
        prod_list = []
        for pname, pdata in data["products"].items():
            threshold = MIN_PRIMA_BY_PRODUCT.get(pname, MIN_PRIMA_DEFAULT)
            prod_list.append({
                "producto": pname,
                "prima_2025": round(pdata["prima_2025"], 2),
                "prima_2025_total": round(pdata["prima_2025_total"], 2),
                "prima_2026": round(pdata["prima_2026"], 2),
                "threshold": threshold,
            })
        prod_list.sort(key=lambda x: x["prima_2026"], reverse=True)

        results.append({
            "name": name,
            "prima_2025": p25,
            "prima_2025_total": p25_total,
            "prima_2026": p26,
            "growth": growth,
            "growth_pct": round(growth * 100, 1) if growth is not None else None,
            "score1": score1,
            "score2": score2,
            "score_final": score_final,
            "eligible_program": eligible,
            "meets_growth": meets_growth,
            "qualified": eligible and meets_growth,
            "products": prod_list,
        })

    results.sort(key=lambda x: x["score_final"], reverse=True)

    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results, sorted(products_set)


def generate_html(data, products=None):
    if products is None:
        products = []
    total_operators = len(data)
    qualified = [d for d in data if d["qualified"]]
    total_prima_2026 = sum(d["prima_2026"] for d in data)
    avg_score = round(sum(d["score_final"] for d in data) / max(total_operators, 1), 1)
    total_prima_2025 = sum(d["prima_2025"] for d in data)
    overall_growth = round(((total_prima_2026 - total_prima_2025) / total_prima_2025 * 100), 1) if total_prima_2025 > 0 else 0

    data_json = json.dumps(data, ensure_ascii=False)
    products_json = json.dumps(products, ensure_ascii=False)
    generation_date = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Zuru Partners Program 2026 - Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {{
  --primary: #001C43;
  --primary-light: #003366;
  --accent: #00CA90;
  --accent-dark: #00A876;
  --accent-light: #E6FFF7;
  --blue: #005BE5;
  --blue-light: #E8F0FE;
  --danger: #E53935;
  --warning: #FF9800;
  --bg: #F5F7FA;
  --card: #FFFFFF;
  --text: #1A1A2E;
  --text-secondary: #6B7280;
  --border: #E5E7EB;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  --shadow-lg: 0 10px 25px rgba(0,28,67,0.1);
  --radius: 12px;
  --radius-sm: 8px;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

.header {{
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 50%, var(--blue) 100%);
  padding: 24px 40px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 4px 20px rgba(0,28,67,0.3);
}}
.header-left {{ display: flex; align-items: center; gap: 20px; }}
.header-logo {{ height: 40px; filter: brightness(0) invert(1); }}
.header-divider {{ width: 1px; height: 32px; background: rgba(255,255,255,0.3); }}
.header-title {{ color: white; }}
.header-title h1 {{ font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }}
.header-title p {{ font-size: 12px; color: rgba(255,255,255,0.7); margin-top: 2px; }}
.header-badge {{
  background: var(--accent);
  color: var(--primary);
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
}}

.container {{ max-width: 1400px; margin: 0 auto; padding: 24px 40px 60px; }}

.filter-bar {{
  background: var(--card);
  border-radius: var(--radius);
  padding: 16px 24px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--shadow);
  flex-wrap: wrap;
}}
.filter-bar label {{
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}}
.filter-bar select, .filter-bar input {{
  padding: 8px 14px;
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-family: inherit;
  background: white;
  color: var(--text);
  min-width: 220px;
  transition: border-color 0.2s;
}}
.filter-bar select:focus, .filter-bar input:focus {{
  outline: none;
  border-color: var(--blue);
  box-shadow: 0 0 0 3px rgba(0,91,229,0.1);
}}
.btn {{
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}}
.btn-primary {{ background: var(--accent); color: var(--primary); }}
.btn-primary:hover {{ background: var(--accent-dark); }}
.btn-outline {{ background: transparent; color: var(--text-secondary); border: 1.5px solid var(--border); }}
.btn-outline:hover {{ border-color: var(--text-secondary); }}

.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}}
.kpi-card {{
  background: var(--card);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: var(--shadow);
  position: relative;
  overflow: hidden;
}}
.kpi-card::before {{
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}}
.kpi-card.green::before {{ background: var(--accent); }}
.kpi-card.blue::before {{ background: var(--blue); }}
.kpi-card.orange::before {{ background: var(--warning); }}
.kpi-card.red::before {{ background: var(--danger); }}
.kpi-label {{ font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
.kpi-value {{ font-size: 28px; font-weight: 800; margin: 6px 0 2px; letter-spacing: -1px; }}
.kpi-sub {{ font-size: 12px; color: var(--text-secondary); }}
.kpi-card.green .kpi-value {{ color: var(--accent-dark); }}
.kpi-card.blue .kpi-value {{ color: var(--blue); }}
.kpi-card.orange .kpi-value {{ color: var(--warning); }}
.kpi-card.red .kpi-value {{ color: var(--danger); }}

.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 24px; }}
.grid-3 {{ display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 24px; }}

.card {{
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}}
.card-header {{
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.card-header h3 {{ font-size: 14px; font-weight: 700; color: var(--primary); }}
.card-body {{ padding: 20px 24px; }}

table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
thead th {{
  text-align: left;
  padding: 10px 12px;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid var(--border);
  white-space: nowrap;
}}
tbody td {{
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}}
tbody tr:hover {{ background: #F9FAFB; }}
tbody tr:last-child td {{ border-bottom: none; }}

.badge {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}}
.badge-success {{ background: var(--accent-light); color: #047857; }}
.badge-danger {{ background: #FEE2E2; color: #B91C1C; }}
.badge-warning {{ background: #FEF3C7; color: #92400E; }}
.badge-blue {{ background: var(--blue-light); color: var(--blue); }}

.score-bar {{
  width: 100%;
  height: 8px;
  background: #F3F4F6;
  border-radius: 4px;
  overflow: hidden;
  min-width: 60px;
}}
.score-bar-fill {{
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}}

.chart-container {{
  position: relative;
  width: 100%;
  padding: 10px 0;
}}
.bar-row {{
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  gap: 10px;
}}
.bar-label {{
  font-size: 12px;
  font-weight: 500;
  width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}}
.bar-group {{
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}}
.bar-track {{
  height: 18px;
  background: #F3F4F6;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}}
.bar {{
  height: 100%;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 6px;
  font-size: 10px;
  font-weight: 600;
  color: white;
  transition: width 0.8s ease;
  min-width: fit-content;
}}
.bar-2025 {{ background: linear-gradient(90deg, #94A3B8, #64748B); }}
.bar-2026 {{ background: linear-gradient(90deg, var(--accent), var(--accent-dark)); }}
.bar-values {{
  font-size: 11px;
  width: 100px;
  text-align: right;
  flex-shrink: 0;
  color: var(--text-secondary);
}}

.legend {{
  display: flex;
  gap: 20px;
  margin-bottom: 12px;
  font-size: 12px;
}}
.legend-item {{
  display: flex;
  align-items: center;
  gap: 6px;
}}
.legend-dot {{
  width: 10px;
  height: 10px;
  border-radius: 3px;
}}
.legend-dot.c2025 {{ background: #64748B; }}
.legend-dot.c2026 {{ background: var(--accent); }}

.operator-detail {{
  display: none;
  margin-bottom: 24px;
}}
.operator-detail.active {{ display: block; }}

.detail-header {{
  background: linear-gradient(135deg, var(--primary) 0%, var(--blue) 100%);
  border-radius: var(--radius) var(--radius) 0 0;
  padding: 24px 32px;
  color: white;
}}
.detail-header h2 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
.detail-header p {{ font-size: 13px; opacity: 0.8; }}
.detail-body {{
  background: var(--card);
  border-radius: 0 0 var(--radius) var(--radius);
  padding: 24px 32px;
  box-shadow: var(--shadow-lg);
}}
.detail-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 20px;
}}
.detail-metric {{
  text-align: center;
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius-sm);
}}
.detail-metric .label {{ font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
.detail-metric .value {{ font-size: 24px; font-weight: 800; margin: 6px 0; letter-spacing: -0.5px; }}
.detail-metric .sub {{ font-size: 11px; color: var(--text-secondary); }}

.gauge-container {{ display: flex; align-items: center; justify-content: center; gap: 24px; padding: 20px; }}
.gauge {{
  width: 120px;
  height: 120px;
  position: relative;
}}
.gauge svg {{ transform: rotate(-90deg); }}
.gauge-label {{
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
}}
.gauge-label .val {{ font-size: 22px; font-weight: 800; color: var(--primary); }}
.gauge-label .lbl {{ font-size: 9px; color: var(--text-secondary); font-weight: 600; text-transform: uppercase; }}

.score-formula {{
  background: var(--bg);
  border-radius: var(--radius-sm);
  padding: 16px;
  margin-top: 16px;
  font-size: 13px;
  text-align: center;
  color: var(--text-secondary);
}}
.score-formula strong {{ color: var(--primary); }}

.footer {{
  text-align: center;
  padding: 20px;
  font-size: 11px;
  color: var(--text-secondary);
}}

.empty-state {{
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}}
.empty-state svg {{ width: 48px; height: 48px; margin-bottom: 12px; opacity: 0.4; }}
.empty-state p {{ font-size: 14px; }}

@media (max-width: 1024px) {{
  .grid-2, .grid-3 {{ grid-template-columns: 1fr; }}
  .container {{ padding: 16px; }}
  .header {{ padding: 16px 20px; }}
  .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}

@media (max-width: 640px) {{
  .kpi-grid {{ grid-template-columns: 1fr; }}
  .filter-bar {{ flex-direction: column; align-items: stretch; }}
  .filter-bar select, .filter-bar input {{ min-width: unset; }}
}}

.scroll-table {{ overflow-x: auto; }}
.highlight-row {{ background: var(--accent-light) !important; }}
.text-right {{ text-align: right; }}
.text-center {{ text-align: center; }}
.mono {{ font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <img src="data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiPz4KPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxNzgiIGhlaWdodD0iNTAiIHZpZXdCb3g9IjAgMCAxNzggNTAiIGZpbGw9Im5vbmUiPgogIDxnIGNsaXAtcGF0aD0idXJsKCNjbGlwMF8wXzI4OSkiPgogICAgPHBhdGggZD0iTTQ0Ljk2MzYgMTUuMjAxNEM0NC44NTk3IDE4LjQzNTcgNDIuMTAwNSAyMC45NjQ0IDM4LjgzNjkgMjAuOTc5MUMzNy45NzY1IDIwLjk3OTEgMzcuMTE2MSAyMC43ODggMzYuMzE1IDIwLjQ2NDZDMzUuNjAzIDIwLjE4NTIgMzQuODMxNiAyMC4wMjM1IDM0LjAxNTcgMjAuMDIzNUMzMy42NTk2IDIwLjAyMzUgMzMuMzAzNiAyMC4wNTI5IDMyLjk2MjQgMjAuMTExN0MzMi4xNDY1IDIwLjI1ODcgMzEuMzg5OSAyMC41Njc1IDMwLjcyMjQgMjEuMDA4NUMyOS40NzYzIDIxLjgxNzEgMjguNTcxNCAyMy4wODE0IDI4LjIwMDUgMjQuNTUxNkMyOC4yMDA1IDI0LjU2NjMgMjguMjAwNSAyNC41ODEgMjguMjAwNSAyNC42MTA0QzI4LjE3MDggMjQuODQ1NiAyOC4xMjYzIDI1LjA2NjEgMjguMDgxOCAyNS4zMDE0QzI4LjA4MTggMjUuMzMwOCAyOC4wNjcgMjUuMzYwMiAyOC4wNTIyIDI1LjM4OTZDMjguMDUyMiAyNS4zODk2IDI4LjA1MjIgMjUuNDA0MyAyOC4wNTIyIDI1LjQxOUMyOC4wMzczIDI1LjQ3NzggMjguMDIyNSAyNS41MzY2IDI4LjAwNzcgMjUuNTk1NEMyNy45OTI4IDI1LjY1NDIgMjcuOTYzMiAyNS43Mjc3IDI3Ljk0ODMgMjUuNzg2NUMyNy45MzM1IDI1Ljg2IDI3LjkwMzggMjUuOTE4OCAyNy44NzQyIDI1Ljk3NzZDMjcuODc0MiAyNS45OTIzIDI3Ljg3NDIgMjYuMDIxNyAyNy44NDQ1IDI2LjAzNjRDMjcuODE0OCAyNi4xMDk5IDI3Ljc4NTEgMjYuMTY4OCAyNy43NTU1IDI2LjI0MjNDMjcuNzU1NSAyNi4yNDIzIDI3Ljc1NTUgMjYuMjcxNyAyNy43NDA2IDI2LjI3MTdDMjcuNjgxMyAyNi4zODkzIDI3LjYzNjggMjYuNTA2OSAyNy41NjI2IDI2LjYyNDVDMjcuNTMzIDI2LjY4MzMgMjcuNTAzMyAyNi43NDIxIDI3LjQ3MzYgMjYuODAwOUMyNy40NzM2IDI2LjgwMDkgMjcuNDE0MyAyNi45MTg1IDI3LjM2OTggMjYuOTc3M0MyNy4zNDAxIDI3LjAzNjEgMjcuMjk1NiAyNy4wOTUgMjcuMjY1OSAyNy4xMzkxQzI2LjEyMzcgMjguODU5MSAyNC4xMjEgMjkuOTYxOCAyMS44NjYyIDI5LjgyOTRDMjAuOTAxOSAyOS43NzA2IDE5Ljk4MjIgMjkuNDkxMyAxOS4xODExIDI5LjAyMDlDMTkuMDYyNCAyOC45NDczIDE4LjkyODkgMjguODg4NSAxOC43OTU0IDI4LjgyOTdDMTguNzUwOSAyOC44MTUgMTguNzIxMiAyOC44MDAzIDE4LjY3NjcgMjguNzg1NkMxOC4wODMzIDI4LjUyMSAxNy40MzA2IDI4LjM4ODcgMTYuNzMzNCAyOC4zODg3QzE0LjEwNzcgMjguNDAzNCAxMi4wMDEyIDMwLjUyMDQgMTIuMDE2IDMzLjEyMjZDMTIuMDMwOCAzNS43MjQ4IDE0LjE2NyAzNy44MTI0IDE2Ljc5MjcgMzcuNzk3N0MxNy42ODI4IDM3Ljc5NzcgMTguNTEzNSAzNy41NDc4IDE5LjIyNTYgMzcuMTIxNEMxOS4zNTkxIDM3LjAzMzIgMTkuNTA3NSAzNi45NDUgMTkuNjI2MSAzNi44NTY4QzIwLjU0NTkgMzYuMjgzNCAyMS42Mjg4IDM1Ljk2IDIyLjc4NTkgMzUuOTQ1M0MyNS4wNTU2IDM1Ljk0NTMgMjcuMDQzNCAzNy4xNjU1IDI4LjA4MTggMzkuMDE3OUMyOC42MDExIDM5Ljk0NDEgMjguODgyOSA0MS4wMDI2IDI4LjgzODQgNDIuMTQ5M0MyOC43MTk3IDQ1LjE2MzIgMjYuMjg2OSA0Ny42NzcxIDIzLjI0NTggNDcuODgzQzIwLjI0OTIgNDguMDg4OCAxNy42ODI4IDQ2LjExODggMTcuMDAwNCA0My40MTM3QzE2Ljk3MDcgNDMuMTQ5MSAxNi45MjYyIDQyLjg5OTEgMTYuODUyMSA0Mi42NDkyQzE2LjQ4MTIgNDEuMTc5IDE1LjU0NjYgMzkuOTE0NyAxNC4yODU3IDM5LjEwNjFDMTMuNjE4MSAzOC42Nzk4IDEyLjg2MTYgMzguMzcxIDEyLjAzMDggMzguMjM4N0MxMS42ODk2IDM4LjE3OTkgMTEuMzMzNiAzOC4xNTA1IDEwLjk3NzYgMzguMTUwNUMxMC4xNjE3IDM4LjE1MDUgOS4zOTAyOCAzOC4zMjY5IDguNjkzMDYgMzguNjA2M0M3Ljg5MTk5IDM4Ljk0NDQgNy4wNDY0MiAzOS4xMzU1IDYuMTcxMTggMzkuMTUwMkMyLjkwNzU4IDM5LjE2NDkgMC4xMTg2NzcgMzYuNjY1NyAtMC4wMjk2Njg5IDMzLjQ0NkMtMC4xNzgwMTUgMzAuMDUgMi41NTE1NSAyNy4yNDIgNS45NDg2NiAyNy4yMjczQzYuNzQ5NzMgMjcuMjI3MyA3LjUyMTEzIDI3LjM3NDMgOC4yMzMxOSAyNy42NTM2QzguMzUxODYgMjcuNzEyNCA4LjQ1NTcxIDI3Ljc1NjUgOC41NzQzOCAyNy44MDA2QzkuMjI3MSAyOC4wNTA2IDkuOTM5MTYgMjguMTk3NiAxMC42ODA5IDI4LjE5NzZDMTEuMTI1OSAyOC4xOTc2IDExLjU3MSAyOC4xMzg4IDExLjk4NjMgMjguMDM1OUMxMi42Njg3IDI3Ljg3NDEgMTMuMzA2NiAyNy41ODAxIDEzLjg3MDMgMjcuMTgzMkMxNS4xMDE2IDI2LjMxNTggMTUuOTc2OCAyNC45NjMyIDE2LjE4NDUgMjMuNDA0OUMxNi4xODQ1IDIzLjMzMTQgMTYuMTk5NCAyMy4yNTc4IDE2LjIxNDIgMjMuMTg0M0MxNi40MDcgMjEuNzQzNiAxNy4xMDQzIDIwLjQ3OTMgMTguMTI3OCAxOS41NTMxQzE4LjE1NzUgMTkuNTIzNiAxOC4xODcyIDE5LjQ5NDIgMTguMjE2OSAxOS40Nzk1QzE4LjI3NjIgMTkuNDM1NCAxOC4zMzU1IDE5LjM3NjYgMTguMzk0OSAxOS4zMzI1QzE5LjQxODUgMTguNDk0NSAyMC43Mzg3IDE3Ljk5NDcgMjIuMTYyOCAxNy45OTQ3QzIzLjQwOSAxNy45OTQ3IDI0LjU4MDkgMTguMzYyMiAyNS41NDUxIDE4Ljk5NDRDMjUuNzY3NiAxOS4xNDE0IDI1Ljk5MDIgMTkuMjg4NCAyNi4yNDI0IDE5LjM5MTNDMjYuODM1NyAxOS42NTYgMjcuNTAzMyAxOS44MDMgMjguMjAwNSAxOS43ODgzQzMwLjgyNjIgMTkuNzg4MyAzMi45MzI3IDE3LjY1NjYgMzIuOTE3OSAxNS4wNTQ0QzMyLjkwMzEgMTIuNDUyMiAzMC43NjY5IDEwLjM2NDYgMjguMTQxMiAxMC4zNzkzQzI3LjQ0NCAxMC4zNzkzIDI2Ljc5MTIgMTAuNTI2MyAyNi4yMTI3IDEwLjgwNTZDMjYuMTY4MiAxMC44MjAzIDI2LjEzODUgMTAuODM1IDI2LjA5NCAxMC44NDk3QzI1LjgyNyAxMC45NjczIDI1LjU4OTYgMTEuMTI5MSAyNS4zNTIzIDExLjI5MDhDMjUuMzIyNiAxMS4zMDU1IDI0LjUyMTUgMTEuOTUyMyAyMi42ODIxIDExLjk1MjNDMjAuNTMxIDExLjk1MjMgMTguNjMyMiAxMC44NDk3IDE3LjU0OTMgOS4xNzM3NUMxNi45NTU5IDguMjYyMjYgMTYuNjE0NyA3LjE3NDM0IDE2LjYxNDcgNi4wMTI5MkMxNi42MTQ3IDIuNzA1MDcgMTkuMjk5OCAwLjAxNDY4MjEgMjIuNjIyNyAtMS45NDMxM2UtMDVDMjUuNjc4NiAtMC4wMTQ3MjEgMjguMjE1MyAyLjIxOTkyIDI4LjYzMDcgNS4xMzA4MkMyOC42MzA3IDUuMjA0MzMgMjguNjQ1NiA1LjI3Nzg0IDI4LjY2MDQgNS4zNTEzNUMyOC44ODI5IDYuOTA5NzEgMjkuNzU4MSA4LjI0NzU1IDMxLjAwNDIgOS4xMDAyNUMzMS41NjggOS40ODI0OSAzMi4yMDU5IDkuNzc2NTIgMzIuOTAzMSA5LjkzODIzQzMzLjMxODQgMTAuMDQxMSAzMy43NjM1IDEwLjA4NTIgMzQuMjA4NSAxMC4wODUyQzM0Ljk1MDIgMTAuMDg1MiAzNS42NjIzIDkuOTM4MjMgMzYuMzAwMiA5LjY3MzYxQzM2LjQxODkgOS42Mjk1IDM2LjUyMjcgOS41ODU0IDM2LjY0MTQgOS41MjY1OUMzNy4zMzg2IDkuMjMyNTYgMzguMTEgOS4wNzA4NCAzOC45MTExIDkuMDcwODRDNDIuMzA4MiA5LjA1NjE0IDQ1LjA2NzQgMTEuODIgNDQuOTYzNiAxNS4yMTYxVjE1LjIwMTRaTTIuMTIzNDJlLTA3IDE1LjAxMDNDMi4xMjM0MmUtMDcgMTguMzAzNCAyLjY4NTA2IDIwLjk2NDQgNi4wMDggMjAuOTY0NEM5LjMzMDk1IDIwLjk2NDQgMTIuMDE2IDE4LjMwMzQgMTIuMDE2IDE1LjAxMDNDMTIuMDE2IDExLjcxNzEgOS4zMzA5NSA5LjA1NjE0IDYuMDA4IDkuMDU2MTRDMi42ODUwNiA5LjA1NjE0IDIuMTIzNDJlLTA3IDExLjcxNzEgMi4xMjM0MmUtMDcgMTUuMDEwM1pNMzIuOTQ3NiAzMy4xOTYxQzMyLjk0NzYgMzYuNDg5MyAzNS42MzI2IDM5LjE1MDIgMzguOTU1NiAzOS4xNTAyQzQyLjI3ODUgMzkuMTUwMiA0NC45NjM2IDM2LjQ4OTMgNDQuOTYzNiAzMy4xOTYxQzQ0Ljk2MzYgMjkuOTAzIDQyLjI3ODUgMjcuMjQyIDM4Ljk1NTYgMjcuMjQyQzM1LjYzMjYgMjcuMjQyIDMyLjk0NzYgMjkuOTAzIDMyLjk0NzYgMzMuMTk2MVoiIGZpbGw9InVybCgjcGFpbnQwX2xpbmVhcl8wXzI4OSkiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik04NC4zNDUgNDguMjUwNVY0MS4yMzc5SDg1LjIyMDJWNDcuNDQxOUg4OC41NDMxVjQ4LjI1MDVIODQuMzQ1WiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTg5Ljc4OTIgNDMuODY5NEM5MC4yNDkxIDQzLjM4NDMgOTAuODQyNSA0My4xMzQ0IDkxLjU2OTQgNDMuMTM0NEM5Mi4yOTYzIDQzLjEzNDQgOTIuODc0OCA0My4zNjk2IDkzLjMxOTkgNDMuODY5NEM5My43NjQ5IDQ0LjM1NDYgOTMuOTg3NCA0NC45NzIxIDkzLjk4NzQgNDUuNzUxMkM5My45ODc0IDQ2LjUzMDQgOTMuNzY0OSA0Ny4xNDc5IDkzLjMxOTkgNDcuNjE4M0M5Mi44ODk3IDQ4LjEwMzUgOTIuMjk2MyA0OC4zMzg3IDkxLjU2OTQgNDguMzM4N0M5MC44NDI1IDQ4LjMzODcgOTAuMjQ5MSA0OC4xMDM1IDg5Ljc4OTIgNDcuNjMzQzg5LjM0NDIgNDcuMTQ3OSA4OS4xMjE3IDQ2LjUzMDQgODkuMTIxNyA0NS43NjU5Qzg5LjEyMTcgNDUuMDAxNSA4OS4zNDQyIDQ0LjM2OTMgODkuNzg5MiA0My44Njk0Wk05MS41NTQ2IDQ3LjYxODNDOTIuNTE4OCA0Ny42MTgzIDkzLjExMjIgNDYuOTEyNyA5My4xMTIyIDQ1Ljc1MTJDOTMuMTEyMiA0NC41ODk4IDkyLjU0ODUgNDMuODk4OSA5MS41NTQ2IDQzLjg5ODlDOTAuNTYwNiA0My44OTg5IDg5Ljk4MjEgNDQuNjA0NSA4OS45ODIxIDQ1Ljc2NTlDODkuOTgyMSA0Ni45Mjc0IDkwLjU2MDYgNDcuNjMzIDkxLjU1NDYgNDcuNjMzVjQ3LjYxODNaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNOTUuNTAwNiA0Ny43ODAxVjQ3LjcwNjZDOTUuMjAzOSA0Ny42MTgzIDk0Ljk5NjIgNDcuMzM5IDk0Ljk5NjIgNDcuMDMwM0M5NC45OTYyIDQ2LjYzMzMgOTUuMjYzMiA0Ni4zMjQ2IDk1LjY0ODkgNDYuMjA3VjQ2LjE0ODJDOTUuMTU5NCA0NS44NTQyIDk0LjkyMiA0NS4zOTg0IDk0LjkyMiA0NC43OTU2Qzk0LjkyMiA0NC4yOTU4IDk1LjEgNDMuODk4OSA5NS40NDEyIDQzLjU5MDFDOTUuNzk3MiA0My4yODE0IDk2LjI1NzEgNDMuMTM0NCA5Ni44MjA4IDQzLjEzNDRDOTcuMjIxNCA0My4xMzQ0IDk3LjUzMjkgNDMuMjA3OSA5Ny43ODUxIDQzLjM0MDJDOTcuOTkyOCA0Mi43OTYyIDk4LjU0MTYgNDIuNDU4MSA5OS4yMjQgNDIuNDU4MVY0My4xNDkxQzk4Ljc2NDIgNDMuMTQ5MSA5OC4zOTMzIDQzLjM1NDkgOTguMjg5NCA0My42NDg5Qzk4LjYwMSA0My45NTc3IDk4Ljc0OTMgNDQuMzU0NiA5OC43NDkzIDQ0LjgyNTFDOTguNzQ5MyA0NS43OTU0IDk4LjAwNzYgNDYuNDU2OSA5Ni44ODAyIDQ2LjQ1NjlDOTYuNjQyOCA0Ni40NTY5IDk2LjQyMDMgNDYuNDI3NSA5Ni4xOTc4IDQ2LjM4MzRDOTUuOTAxMSA0Ni40Mjc1IDk1Ljc2NzYgNDYuNTg5MiA5NS43Njc2IDQ2LjgzOTJDOTUuNzY3NiA0Ny4xMzMyIDk1Ljk5MDEgNDcuMjY1NSA5Ni40NSA0Ny4yNjU1SDk3Ljc4NTFDOTguNzQ5MyA0Ny4yNjU1IDk5LjMxMyA0Ny43MzYgOTkuMzEzIDQ4LjUxNTFDOTkuMzEzIDQ5LjQ3MDcgOTguNDA4MSA0OS45NzA2IDk2Ljg4MDIgNDkuOTcwNkM5NS40NDEyIDQ5Ljk3MDYgOTQuNzQ0IDQ5LjUwMDEgOTQuNzQ0IDQ4LjczNTdDOTQuNzQ0IDQ4LjI2NTIgOTUuMDQwNyA0Ny44OTc3IDk1LjUxNTQgNDcuNzUwN0w5NS41MDA2IDQ3Ljc4MDFaTTk2Ljg5NSA0OS4zNjc4Qzk3LjkzMzQgNDkuMzY3OCA5OC40NTI2IDQ5LjEwMzIgOTguNDUyNiA0OC41NTkyQzk4LjQ1MjYgNDguMTYyMyA5OC4yMDA0IDQ3Ljk3MTIgOTcuNjgxMiA0Ny45NzEySDk2LjMxNjRDOTUuNzY3NiA0Ny45NzEyIDk1LjQ4NTcgNDguMTkxNyA5NS40ODU3IDQ4LjYxODFDOTUuNDg1NyA0OS4xMDMyIDk1Ljk0NTYgNDkuMzUzMSA5Ni44OTUgNDkuMzUzMVY0OS4zNjc4Wk05Ni44MzU3IDQ1Ljg2ODlDOTcuNTE4IDQ1Ljg2ODkgOTcuOTE4NiA0NS40NTcyIDk3LjkxODYgNDQuODEwM0M5Ny45MTg2IDQ0LjE2MzUgOTcuNDg4NCA0My43MzcxIDk2LjgzNTcgNDMuNzM3MUM5Ni4xODI5IDQzLjczNzEgOTUuNzUyNyA0NC4xNjM1IDk1Ljc1MjcgNDQuODEwM0M5NS43NTI3IDQ1LjQ1NzIgOTYuMTgyOSA0NS44Njg5IDk2LjgzNTcgNDUuODY4OVoiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik0xMDAuMzY2IDQyLjM5OTNWNDEuMjk2N0gxMDEuMTk3VjQyLjM5OTNIMTAwLjM2NlpNMTAwLjM2NiA0OC4yNTA1VjQzLjIzNzNIMTAxLjE5N1Y0OC4yNTA1SDEwMC4zNjZaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTAzLjIyOSA0Ni43MzYzQzEwMy4yMjkgNDcuMzI0MyAxMDMuNzE5IDQ3LjY5MTkgMTA0LjQ5IDQ3LjY5MTlDMTA1LjIwMiA0Ny42OTE5IDEwNS42MzMgNDcuMzgzMSAxMDUuNjMzIDQ2Ljg1MzlDMTA1LjYzMyA0Ni40ODYzIDEwNS40MSA0Ni4yNTExIDEwNC45NSA0Ni4xNjI5TDEwMy44NjcgNDUuOTU3MUMxMDIuOTYyIDQ1Ljc5NTQgMTAyLjUwMiA0NS4zNTQzIDEwMi41MDIgNDQuNjMzOUMxMDIuNTAyIDQzLjcwNzcgMTAzLjI0NCA0My4xMzQ0IDEwNC40MTYgNDMuMTM0NEMxMDUuNTg4IDQzLjEzNDQgMTA2LjM0NSA0My43MzcxIDEwNi4zNTkgNDQuNjYzM0gxMDUuNTU4QzEwNS41MjkgNDQuMDc1MyAxMDUuMTU4IDQzLjc4MTIgMTA0LjQzMSA0My43ODEyQzEwMy43NDkgNDMuNzgxMiAxMDMuMzQ4IDQ0LjA3NTMgMTAzLjM0OCA0NC41NDU3QzEwMy4zNDggNDQuODEwMyAxMDMuNDY3IDQ1LjAwMTUgMTAzLjY3NCA0NS4xMTkxQzEwMy44ODIgNDUuMjA3MyAxMDMuOTcxIDQ1LjIzNjcgMTA0LjE2NCA0NS4yNjYxTDEwNS4xNTggNDUuNDQyNUMxMDYuMDMzIDQ1LjU4OTUgMTA2LjQ5MyA0Ni4wNiAxMDYuNDkzIDQ2LjgzOTJDMTA2LjQ5MyA0Ny43NTA3IDEwNS42OTIgNDguMzM4NyAxMDQuNDc1IDQ4LjMzODdDMTAzLjIgNDguMzM4NyAxMDIuNDEzIDQ3LjY5MTkgMTAyLjQxMyA0Ni43MjE2SDEwMy4yMTVMMTAzLjIyOSA0Ni43MzYzWiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTExMS44NjMgNDMuMjM3M1Y0OC4yNTA1SDExMS4wMzJWNDMuOTI4MkgxMDguNzE4VjQ2Ljc5NUMxMDguNzE4IDQ3LjAwMDkgMTA4LjczMyA0Ny4xMTg1IDEwOC44MjIgNDcuMzA5NkMxMDguODk2IDQ3LjQ4NiAxMDkuMDg5IDQ3LjYwMzYgMTA5LjQwMSA0Ny42MDM2QzEwOS41NzkgNDcuNjAzNiAxMDkuNzQyIDQ3LjU4ODkgMTA5Ljg2IDQ3LjU0NDhWNDguMjUwNUMxMDkuNjUzIDQ4LjI5NDYgMTA5LjQ2IDQ4LjMyNCAxMDkuMjUyIDQ4LjMyNEMxMDguMzQ3IDQ4LjMyNCAxMDcuODg3IDQ3LjgzODkgMTA3Ljg4NyA0Ni44OThWNDMuOTI4MkgxMDcuMDEyVjQzLjIzNzNIMTA3Ljg4N1Y0MS43MjNMMTA4LjcxOCA0MS4zOTk2VjQzLjIzNzNIMTExLjg2M1pNMTExLjAzMiA0MS4yOTY3SDExMS44NjNWNDIuMzk5M0gxMTEuMDMyVjQxLjI5NjdaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTE3LjcyMyA0Ni41NDUxQzExNy42NzggNDcuMDg5MSAxMTcuNDQxIDQ3LjUzMDEgMTE3LjAyNiA0Ny44NjgzQzExNi42MjUgNDguMTkxNyAxMTYuMTA2IDQ4LjM1MzQgMTE1LjQ5OCA0OC4zNTM0QzExNC43NzEgNDguMzUzNCAxMTQuMTc3IDQ4LjExODIgMTEzLjc0NyA0Ny42NDc4QzExMy4zMTcgNDcuMTc3MyAxMTMuMDk0IDQ2LjU0NTEgMTEzLjA5NCA0NS43NjZDMTEzLjA5NCA0NC45ODY4IDExMy4zMTcgNDQuMzM5OSAxMTMuNzQ3IDQzLjg2OTVDMTE0LjE5MiA0My4zODQzIDExNC44IDQzLjE0OTEgMTE1LjU0MiA0My4xNDkxQzExNi4xMzUgNDMuMTQ5MSAxMTYuNjI1IDQzLjMxMDggMTE3LjAyNiA0My42MzQyQzExNy40MjYgNDMuOTU3NyAxMTcuNjQ5IDQ0LjM2OTMgMTE3LjcwOCA0NC44ODM5SDExNi44NDhDMTE2LjY5OSA0NC4yMzcgMTE2LjE4IDQzLjg5ODkgMTE1LjUxMiA0My44OTg5QzExNC41MDQgNDMuODk4OSAxMTMuOTU1IDQ0LjYzMzkgMTEzLjk1NSA0NS43ODA3QzExMy45NTUgNDYuOTI3NCAxMTQuNTQ4IDQ3LjYzMzEgMTE1LjUxMiA0Ny42MzMxQzExNi4yNTQgNDcuNjMzMSAxMTYuODAzIDQ3LjIwNjcgMTE2Ljg3NyA0Ni41NTk4SDExNy43MzhMMTE3LjcyMyA0Ni41NDUxWiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTExOS4zMjUgNDYuNzM2M0MxMTkuMzI1IDQ3LjMyNDMgMTE5LjgxNCA0Ny42OTE5IDEyMC41ODYgNDcuNjkxOUMxMjEuMjk4IDQ3LjY5MTkgMTIxLjcyOCA0Ny4zODMxIDEyMS43MjggNDYuODUzOUMxMjEuNzI4IDQ2LjQ4NjMgMTIxLjUwNiA0Ni4yNTExIDEyMS4wNDYgNDYuMTYyOUwxMTkuOTYzIDQ1Ljk1NzFDMTE5LjA1OCA0NS43OTU0IDExOC41OTggNDUuMzU0MyAxMTguNTk4IDQ0LjYzMzlDMTE4LjU5OCA0My43MDc3IDExOS4zNCA0My4xMzQ0IDEyMC41MTIgNDMuMTM0NEMxMjEuNjg0IDQzLjEzNDQgMTIyLjQ0IDQzLjczNzEgMTIyLjQ1NSA0NC42NjMzSDEyMS42NTRDMTIxLjYyNCA0NC4wNzUzIDEyMS4yNTMgNDMuNzgxMiAxMjAuNTI2IDQzLjc4MTJDMTE5Ljg0NCA0My43ODEyIDExOS40NDQgNDQuMDc1MyAxMTkuNDQ0IDQ0LjU0NTdDMTE5LjQ0NCA0NC44MTAzIDExOS41NjIgNDUuMDAxNSAxMTkuNzcgNDUuMTE5MUMxMTkuOTc4IDQ1LjIwNzMgMTIwLjA2NyA0NS4yMzY3IDEyMC4yNTkgNDUuMjY2MUwxMjEuMjUzIDQ1LjQ0MjVDMTIyLjEyOSA0NS41ODk1IDEyMi41ODggNDYuMDYgMTIyLjU4OCA0Ni44MzkyQzEyMi41ODggNDcuNzUwNyAxMjEuNzg3IDQ4LjMzODcgMTIwLjU3MSA0OC4zMzg3QzExOS4yOTUgNDguMzM4NyAxMTguNTA5IDQ3LjY5MTkgMTE4LjUwOSA0Ni43MjE2SDExOS4zMUwxMTkuMzI1IDQ2LjczNjNaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTI3LjA1NCA0OC4yNTA1SDEyNi4xNzhWNDEuMjM3OUgxMjcuMDU0VjQ4LjI1MDVaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTI4LjgzNCA0OC4yNTA1VjQzLjIzNzNIMTI5LjU3NkwxMjkuNjc5IDQ0LjE2MzVIMTI5Ljc1NEMxMzAuMDY1IDQzLjUxNjYgMTMwLjY4OCA0My4xMzQ0IDEzMS40NiA0My4xMzQ0QzEzMi41NTcgNDMuMTM0NCAxMzMuMjEgNDMuOTI4MyAxMzMuMjEgNDUuMTYzMlY0OC4yNTA1SDEzMi4zNjRWNDUuMjUxNEMxMzIuMzY0IDQ0LjMzOTkgMTMxLjk2NCA0My44ODQxIDEzMS4xNzggNDMuODg0MUMxMzAuMjg4IDQzLjg4NDEgMTI5LjY3OSA0NC41ODk4IDEyOS42NzkgNDUuNjMzNlY0OC4yNTA1SDEyOC44MzRaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTM1LjE2OCA0Ni43MzYzQzEzNS4xNjggNDcuMzI0MyAxMzUuNjU4IDQ3LjY5MTkgMTM2LjQyOSA0Ny42OTE5QzEzNy4xNDEgNDcuNjkxOSAxMzcuNTcxIDQ3LjM4MzEgMTM3LjU3MSA0Ni44NTM5QzEzNy41NzEgNDYuNDg2MyAxMzcuMzQ5IDQ2LjI1MTEgMTM2Ljg4OSA0Ni4xNjI5TDEzNS44MDYgNDUuOTU3MUMxMzQuOTAxIDQ1Ljc5NTQgMTM0LjQ0MSA0NS4zNTQzIDEzNC40NDEgNDQuNjMzOUMxMzQuNDQxIDQzLjcwNzcgMTM1LjE4MyA0My4xMzQ0IDEzNi4zNTUgNDMuMTM0NEMxMzcuNTI3IDQzLjEzNDQgMTM4LjI4MyA0My43MzcxIDEzOC4yOTggNDQuNjYzM0gxMzcuNDk3QzEzNy40NjggNDQuMDc1MyAxMzcuMDk3IDQzLjc4MTIgMTM2LjM3IDQzLjc4MTJDMTM1LjY4NyA0My43ODEyIDEzNS4yODcgNDQuMDc1MyAxMzUuMjg3IDQ0LjU0NTdDMTM1LjI4NyA0NC44MTAzIDEzNS40MDYgNDUuMDAxNSAxMzUuNjEzIDQ1LjExOTFDMTM1LjgyMSA0NS4yMDczIDEzNS45MSA0NS4yMzY3IDEzNi4xMDMgNDUuMjY2MUwxMzcuMDk3IDQ1LjQ0MjVDMTM3Ljk3MiA0NS41ODk1IDEzOC40MzIgNDYuMDYgMTM4LjQzMiA0Ni44MzkyQzEzOC40MzIgNDcuNzUwNyAxMzcuNjMxIDQ4LjMzODcgMTM2LjQxNCA0OC4zMzg3QzEzNS4xMzkgNDguMzM4NyAxMzQuMzUyIDQ3LjY5MTkgMTM0LjM1MiA0Ni43MjE2SDEzNS4xNTNMMTM1LjE2OCA0Ni43MzYzWiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTE0My45MjEgNDMuMjM3M1Y0OC4yNTA1SDE0My4yMDlMMTQzLjA5IDQ3LjMyNDNIMTQzLjAxNkMxNDIuNzQ5IDQ3Ljk0MTggMTQyLjA4MSA0OC4zNTM0IDE0MS4yOTUgNDguMzUzNEMxNDAuMjQyIDQ4LjM1MzQgMTM5LjYxOSA0Ny42NjI0IDEzOS42MTkgNDYuNDQyMlY0My4yMzczSDE0MC40NDlWNDYuMzI0NkMxNDAuNDQ5IDQ3LjE5MiAxNDAuODIgNDcuNjE4MyAxNDEuNTc3IDQ3LjYxODNDMTQyLjQ5NiA0Ny42MTgzIDE0My4wNzUgNDYuOTEyNyAxNDMuMDc1IDQ1Ljg1NDJWNDMuMjM3M0gxNDMuOTIxWiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTE0NS40NzggNDguMjUwNVY0My4yMzczSDE0Ni4yMkwxNDYuMzI0IDQ0LjI1MTdIMTQ2LjM4M0MxNDYuNjY1IDQzLjUxNjYgMTQ3LjIxNCA0My4xNDkxIDE0OC4wMTUgNDMuMTQ5MVY0My44OTg5QzE0Ni44ODcgNDMuOTEzNiAxNDYuMzI0IDQ0LjU4OTggMTQ2LjMyNCA0NS45Mjc3VjQ4LjI1MDVIMTQ1LjQ3OFoiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik0xNDguMzQxIDQzLjIzNzNIMTQ5LjIxN1Y0MS43MjNMMTUwLjA0NyA0MS4zOTk2VjQzLjIzNzNIMTUxLjE3NVY0My45MjgzSDE1MC4wNDdWNDYuODI0NUMxNTAuMDQ3IDQ3LjIyMTQgMTUwLjEwNyA0Ny41NzQzIDE1MC43NTkgNDcuNjE4NEMxNTAuOTM3IDQ3LjYxODQgMTUxLjA4NiA0Ny42MDM3IDE1MS4xOSA0Ny41NTk1VjQ4LjI2NTJDMTUxLjAxMiA0OC4zMDkzIDE1MC43ODkgNDguMzM4NyAxNTAuNTY2IDQ4LjMzODdDMTQ5LjY3NiA0OC4zMzg3IDE0OS4yMzEgNDcuODUzNiAxNDkuMjMxIDQ2LjkxMjdWNDMuOTQzSDE0OC4zNTZWNDMuMjUyTDE0OC4zNDEgNDMuMjM3M1oiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik0xNTIuNDggNDcuNjQ3N0MxNTIuMDUgNDcuMTc3MyAxNTEuODI3IDQ2LjU0NTEgMTUxLjgyNyA0NS43NTEyQzE1MS44MjcgNDQuOTU3NCAxNTIuMDM1IDQ0LjMyNTIgMTUyLjQ4IDQzLjg1NDdDMTUyLjkxIDQzLjM2OTYgMTUzLjUwNCA0My4xMzQ0IDE1NC4yMTYgNDMuMTM0NEMxNTUuNjI1IDQzLjEzNDQgMTU2LjQ1NiA0NC4wMTY1IDE1Ni40NTYgNDUuMzk4NEMxNTYuNDU2IDQ1LjYwNDIgMTU2LjQ1NiA0NS43ODA2IDE1Ni40MjYgNDUuOTEzSDE1Mi42ODhDMTUyLjY4OCA0Ny4wMTU2IDE1My4yODEgNDcuNjYyNCAxNTQuMjQ1IDQ3LjY2MjRDMTU0Ljk4NyA0Ny42NjI0IDE1NS41MjEgNDcuMjk0OSAxNTUuNjU1IDQ2LjczNjNIMTU2LjVDMTU2LjQxMSA0Ny4yMjE0IDE1Ni4xNTkgNDcuNjAzNiAxNTUuNzQ0IDQ3Ljg5NzdDMTU1LjM0MyA0OC4xOTE3IDE1NC44MzkgNDguMzM4NyAxNTQuMjMxIDQ4LjMzODdDMTUzLjUxOSA0OC4zMzg3IDE1Mi45MjUgNDguMTAzNSAxNTIuNDk1IDQ3LjYzM0wxNTIuNDggNDcuNjQ3N1pNMTU1LjYxIDQ1LjMxMDJDMTU1LjYxIDQ0LjM1NDYgMTU1LjA5MSA0My44MjUzIDE1NC4yMDEgNDMuODI1M0MxNTMuMzExIDQzLjgyNTMgMTUyLjcxNyA0NC40MTM0IDE1Mi42ODggNDUuMzEwMkgxNTUuNjFaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTYyLjAzNCA0Ni41NDUxQzE2MS45ODkgNDcuMDg5MSAxNjEuNzUyIDQ3LjUzMDEgMTYxLjMzNiA0Ny44NjgzQzE2MC45MzYgNDguMTkxNyAxNjAuNDE3IDQ4LjM1MzQgMTU5LjgwOCA0OC4zNTM0QzE1OS4wODIgNDguMzUzNCAxNTguNDg4IDQ4LjExODIgMTU4LjA1OCA0Ny42NDc4QzE1Ny42MjggNDcuMTc3MyAxNTcuNDA1IDQ2LjU0NTEgMTU3LjQwNSA0NS43NjZDMTU3LjQwNSA0NC45ODY4IDE1Ny42MjggNDQuMzM5OSAxNTguMDU4IDQzLjg2OTVDMTU4LjUwMyA0My4zODQzIDE1OS4xMTEgNDMuMTQ5MSAxNTkuODUzIDQzLjE0OTFDMTYwLjQ0NiA0My4xNDkxIDE2MC45MzYgNDMuMzEwOCAxNjEuMzM2IDQzLjYzNDJDMTYxLjczNyA0My45NTc3IDE2MS45NTkgNDQuMzY5MyAxNjIuMDE5IDQ0Ljg4MzlIMTYxLjE1OEMxNjEuMDEgNDQuMjM3IDE2MC40OTEgNDMuODk4OSAxNTkuODIzIDQzLjg5ODlDMTU4LjgxNSA0My44OTg5IDE1OC4yNjYgNDQuNjMzOSAxNTguMjY2IDQ1Ljc4MDdDMTU4LjI2NiA0Ni45Mjc0IDE1OC44NTkgNDcuNjMzMSAxNTkuODIzIDQ3LjYzMzFDMTYwLjU2NSA0Ny42MzMxIDE2MS4xMTQgNDcuMjA2NyAxNjEuMTg4IDQ2LjU1OThIMTYyLjA0OEwxNjIuMDM0IDQ2LjU0NTFaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTYzLjIyIDQ4LjI1MDVWNDEuMjA4NUgxNjQuMDY2VjQ0LjE0ODhIMTY0LjEyNUMxNjQuNDM3IDQzLjUzMTMgMTY1LjA5IDQzLjEzNDQgMTY1LjgzMSA0My4xMzQ0QzE2Ni45MjkgNDMuMTM0NCAxNjcuNTgyIDQzLjkxMzYgMTY3LjU4MiA0NS4xNDg1VjQ4LjIzNThIMTY2Ljc1MVY0NS4yMjJDMTY2Ljc1MSA0NC4zMTA1IDE2Ni4zNSA0My44NTQ3IDE2NS41NDkgNDMuODU0N0MxNjQuNjU5IDQzLjg1NDcgMTY0LjA2NiA0NC41MzEgMTY0LjA2NiA0NS41NzQ4VjQ4LjIyMTFIMTYzLjIyVjQ4LjI1MDVaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTcxLjM1IDE0LjM3ODFDMTcwLjU3OCAxMy42NTc3IDE3MC4yMDcgMTIuNzMxNiAxNzAuMjA3IDExLjU5OTVDMTcwLjIwNyAxMC40Njc1IDE3MC41NzggOS41NTYwMSAxNzEuMzUgOC44MzU2NEMxNzIuMTIxIDguMTE1MjYgMTczLjA0MSA3Ljc0NzcyIDE3NC4xMDkgNy43NDc3MkMxNzYuMTcxIDcuNzAzNjIgMTc4LjA0IDkuMzUwMTkgMTc3Ljk5NiAxMS41NzAxQzE3Ny45OTYgMTIuNzAyMSAxNzcuNjI1IDEzLjYyODMgMTc2Ljg1MyAxNC4zNDg3QzE3Ni4wOTcgMTUuMDY5MSAxNzUuMTc3IDE1LjQzNjYgMTc0LjEwOSAxNS40MzY2QzE3My4wNDEgMTUuNDM2NiAxNzIuMTA2IDE1LjA4MzggMTcxLjM1IDE0LjM2MzRWMTQuMzc4MVpNMTc2LjYzMSA5LjA0MTQ2QzE3NS45NDggOC4zNzk4OSAxNzUuMTAzIDguMDU2NDUgMTc0LjEwOSA4LjA1NjQ1QzE3My4xMTUgOC4wNTY0NSAxNzIuMjY5IDguMzk0NTkgMTcxLjU3MiA5LjA1NjE2QzE3MC44NzUgOS43MTc3MyAxNzAuNTE5IDEwLjU3MDQgMTcwLjUxOSAxMS42MTQyQzE3MC41MTkgMTIuNjU4IDE3MC44NzUgMTMuNTEwNyAxNzEuNTU3IDE0LjE3MjNDMTcyLjI1NSAxNC44MzM5IDE3My4xIDE1LjE3MiAxNzQuMDk0IDE1LjE3MkMxNzUuMDg4IDE1LjE3MiAxNzUuOTM0IDE0LjgzMzkgMTc2LjYxNiAxNC4xNzIzQzE3Ny4yOTggMTMuNTEwNyAxNzcuNjU0IDEyLjY0MzMgMTc3LjY1NCAxMS41ODQ4QzE3Ny42NTQgMTAuNTI2MyAxNzcuMjk4IDkuNzAzMDMgMTc2LjYxNiA5LjA0MTQ2SDE3Ni42MzFaTTE3Mi42NTUgMTMuMDk5MUMxNzIuMjU1IDEyLjcxNjggMTcyLjA2MiAxMi4yMTcgMTcyLjA2MiAxMS41OTk1QzE3Mi4wNjIgMTAuOTgyMSAxNzIuMjU1IDEwLjQ4MjIgMTcyLjY1NSAxMC4xQzE3My4wNTYgOS43MTc3MyAxNzMuNTYgOS41MjY2MSAxNzQuMTY4IDkuNTI2NjFDMTc0LjcwMiA5LjUyNjYxIDE3NS4xNjIgOS42NzM2MyAxNzUuNTMzIDkuOTgyMzZDMTc1LjkwNCAxMC4yNzY0IDE3Ni4xMTIgMTAuNjU4NiAxNzYuMTcxIDExLjE0MzhIMTc1LjQxNEMxNzUuMzI1IDEwLjU3MDQgMTc0LjgzNiAxMC4xODgyIDE3NC4xNjggMTAuMTg4MkMxNzMuMzIzIDEwLjE4ODIgMTcyLjgzMyAxMC43NjE1IDE3Mi44MzMgMTEuNjE0MkMxNzIuODMzIDEyLjQ2NjkgMTczLjMzOCAxMy4wNDAzIDE3NC4xNjggMTMuMDQwM0MxNzQuODM2IDEzLjA0MDMgMTc1LjM0IDEyLjY0MzMgMTc1LjQyOSAxMi4wODQ3SDE3Ni4xODZDMTc2LjE0MSAxMi41NDA0IDE3NS45MTkgMTIuOTIyNyAxNzUuNTQ4IDEzLjIzMTRDMTc1LjE3NyAxMy41MjU0IDE3NC43MzIgMTMuNjg3MiAxNzQuMTgzIDEzLjY4NzJDMTczLjU3NSAxMy42ODcyIDE3My4wNzEgMTMuNDk2IDE3Mi42NyAxMy4xMTM4TDE3Mi42NTUgMTMuMDk5MVoiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik01Ni4yOTI4IDI3LjEwOTdMNzUuNzcwNiAxOC43NDQ1Qzc1Ljg0NDggMTguNzE1MSA3NS45MDQxIDE4LjY0MTYgNzUuOTA0MSAxOC41NTM0Qzc1LjkwNDEgMTguNDIxMSA3NS43ODU0IDE4LjMxODEgNzUuNjUxOSAxOC4zNDc1TDcyLjY3MDIgMTguODMyN0w1Ni40ODU2IDE4LjkwNjJDNTYuMjAzOCAxOC45MDYyIDU1Ljk4MTMgMTguNjg1NyA1NS45ODEzIDE4LjQwNjRWMTMuNjEzNkM1NS45ODEzIDEzLjMzNDMgNTYuMjAzOCAxMy4xMTM4IDU2LjQ4NTYgMTMuMTEzOEw3OS4yMjcgMTMuMDQwM0M3OS41MDg5IDEzLjA0MDMgNzkuNzMxNCAxMy4yNjA4IDc5LjczMTQgMTMuNTQwMVYyMi4zNzU4Qzc5LjczMTQgMjIuNTgxNiA3OS42MTI3IDIyLjc1OCA3OS40MTk5IDIyLjgzMTVMNjEuMzUxNCAzMC41NjQ1QzYxLjI3NzIgMzAuNTkzOSA2MS4yMTc5IDMwLjY2NzUgNjEuMjE3OSAzMC43NTU3QzYxLjIxNzkgMzAuODg4IDYxLjMzNjUgMzAuOTkwOSA2MS40NzAxIDMwLjk2MTVMNjQuODM3NSAzMC40MDI4SDc5LjI0MTlDNzkuNTIzNyAzMC40MDI4IDc5Ljc0NjIgMzAuNjIzNCA3OS43NDYyIDMwLjkwMjdWMzUuNjk1NEM3OS43NDYyIDM1Ljk3NDcgNzkuNTIzNyAzNi4xOTUyIDc5LjI0MTkgMzYuMTk1Mkw1Ni40NzA4IDM2LjIyNDZDNTYuMTg4OSAzNi4yMjQ2IDU1Ljk2NjQgMzYuMDA0MSA1NS45NjY0IDM1LjcyNDhWMjcuNTUwN0M1NS45NjY0IDI3LjM0NDkgNTYuMDg1MSAyNy4xNjg1IDU2LjI3OCAyNy4wOTVMNTYuMjkyOCAyNy4xMDk3WiIgZmlsbD0iIzAwMUM0MyI+PC9wYXRoPgogICAgPHBhdGggZD0iTTExMS43NTkgMzYuMjU0SDEwNS4xNzNDMTA0LjkwNiAzNi4yNTQgMTA0LjY4MyAzNi4wNDgyIDEwNC42NjggMzUuNzgzNkwxMDQuMzI3IDMxLjMxNDNDMTA0LjMyNyAzMS4xODIgMTA0LjIwOCAzMS4wNzkxIDEwNC4wNzUgMzEuMDc5MUMxMDMuOTg2IDMxLjA3OTEgMTAzLjg5NyAzMS4xMzc5IDEwMy44NTIgMzEuMjExNEMxMDEuOTI0IDM0LjcxMDQgOTguNDA4MSAzNi42NjU3IDk0LjA0NjggMzYuNjY1N0M4Ny4xOTMyIDM2LjY2NTcgODMuMTQzNCAzMi45NzU2IDgzLjE0MzQgMjYuNzcxNVYxMy41MTA3QzgzLjE0MzQgMTMuMjMxNCA4My4zNjU5IDEzLjAxMDkgODMuNjQ3NyAxMy4wMTA5SDkwLjkwMThDOTEuMTgzNyAxMy4wMTA5IDkxLjQwNjIgMTMuMjMxNCA5MS40MDYyIDEzLjUxMDdWMjQuNjU0NUM5MS4zNzY1IDI4LjgwMDMgOTMuNDY4MiAzMS4yOTk2IDk3LjE2MiAzMS4yOTk2QzEwMC40NyAzMS4yOTk2IDEwMi45MTggMjkuODg4MyAxMDMuOTg2IDI3LjQ2MjVWMTMuNTEwN0MxMDMuOTg2IDEzLjIzMTQgMTA0LjIwOCAxMy4wMTA5IDEwNC40OSAxMy4wMTA5SDExMS43NDRDMTEyLjAyNiAxMy4wMTA5IDExMi4yNDkgMTMuMjMxNCAxMTIuMjQ5IDEzLjUxMDdWMzUuNzI0OEMxMTIuMjQ5IDM2LjAwNDEgMTEyLjAyNiAzNi4yMjQ2IDExMS43NDQgMzYuMjI0NkwxMTEuNzU5IDM2LjI1NFoiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICAgIDxwYXRoIGQ9Ik0xMTYuMTggMTMuMDI1NkgxMjIuNzY2QzEyMy4wMzQgMTMuMDI1NiAxMjMuMjU2IDEzLjIzMTQgMTIzLjI3MSAxMy40OTZMMTIzLjU1MyAxNy4xNDJMMTIzLjQxOSAxOC41MDkzQzEyMy40MTkgMTguNTA5MyAxMjMuNDM0IDE4LjYxMjIgMTIzLjQ3OSAxOC42NDE2QzEyMy41NTMgMTguNzAwNCAxMjMuNjcxIDE4LjY4NTcgMTIzLjcxNiAxOC41OTc1QzEyNS43NDggMTQuNjI4IDEyOC44MzQgMTIuNTExIDEzMi44MjQgMTIuNTExQzEzMy4yMSAxMi41MTEgMTM0LjA1NiAxMi41NTUxIDEzNC41OSAxMi41OTkyQzEzNC44NTcgMTIuNjEzOSAxMzUuMDUgMTIuODM0NSAxMzUuMDUgMTMuMDk5MVYxOC4zMDM0QzEzNS4wNSAxOC42MjY5IDEzNC43MzggMTguODc2OCAxMzQuNDI2IDE4Ljc4ODZDMTMzLjM3MyAxOC41MjQgMTMyLjcwNiAxOC4zNzY5IDEzMS40NzQgMTguMzc2OUMxMjcuODg0IDE4LjM3NjkgMTI1LjA4MSAyMC4zNzY0IDEyMy45NTMgMjIuODc1NlYzNS43Mzk1QzEyMy45NTMgMzYuMDE4OCAxMjMuNzMxIDM2LjIzOTMgMTIzLjQ0OSAzNi4yMzkzSDExNi4xOTVDMTE1LjkxMyAzNi4yMzkzIDExNS42OSAzNi4wMTg4IDExNS42OSAzNS43Mzk1VjEzLjUyNTRDMTE1LjY5IDEzLjI0NjEgMTE1LjkxMyAxMy4wMjU2IDExNi4xOTUgMTMuMDI1NkgxMTYuMThaIiBmaWxsPSIjMDAxQzQzIj48L3BhdGg+CiAgICA8cGF0aCBkPSJNMTY3LjA3NyAzNi4yNTRIMTYwLjQ5MUMxNjAuMjI0IDM2LjI1NCAxNjAuMDAxIDM2LjA0ODIgMTU5Ljk4NiAzNS43ODM2TDE1OS42NDUgMzEuMzE0M0MxNTkuNjQ1IDMxLjE4MiAxNTkuNTI3IDMxLjA3OTEgMTU5LjM5MyAzMS4wNzkxQzE1OS4zMDQgMzEuMDc5MSAxNTkuMjE1IDMxLjEzNzkgMTU5LjE3MSAzMS4yMTE0QzE1Ny4yNDIgMzQuNzEwNCAxNTMuNzI2IDM2LjY2NTcgMTQ5LjM2NSAzNi42NjU3QzE0Mi41MTEgMzYuNjY1NyAxMzguNDYxIDMyLjk3NTYgMTM4LjQ2MSAyNi43NzE1VjEzLjUxMDdDMTM4LjQ2MSAxMy4yMzE0IDEzOC42ODQgMTMuMDEwOSAxMzguOTY2IDEzLjAxMDlIMTQ2LjIyQzE0Ni41MDIgMTMuMDEwOSAxNDYuNzI0IDEzLjIzMTQgMTQ2LjcyNCAxMy41MTA3VjI0LjY1NDVDMTQ2LjY5NSAyOC44MDAzIDE0OC43ODYgMzEuMjk5NiAxNTIuNDggMzEuMjk5NkMxNTUuNzg4IDMxLjI5OTYgMTU4LjIzNiAyOS44ODgzIDE1OS4zMDQgMjcuNDYyNVYxMy41MTA3QzE1OS4zMDQgMTMuMjMxNCAxNTkuNTI3IDEzLjAxMDkgMTU5LjgwOCAxMy4wMTA5SDE2Ny4wNjNDMTY3LjM0NCAxMy4wMTA5IDE2Ny41NjcgMTMuMjMxNCAxNjcuNTY3IDEzLjUxMDdWMzUuNzI0OEMxNjcuNTY3IDM2LjAwNDEgMTY3LjM0NCAzNi4yMjQ2IDE2Ny4wNjMgMzYuMjI0NkwxNjcuMDc3IDM2LjI1NFoiIGZpbGw9IiMwMDFDNDMiPjwvcGF0aD4KICA8L2c+CiAgPGRlZnM+CiAgICA8bGluZWFyR3JhZGllbnQgaWQ9InBhaW50MF9saW5lYXJfMF8yODkiIHgxPSIxMS40MDc4IiB5MT0iNDMuMTA0OSIgeDI9IjMzLjI4NzMiIHkyPSI0Ljg4NjYiIGdyYWRpZW50VW5pdHM9InVzZXJTcGFjZU9uVXNlIj4KICAgICAgPHN0b3Agc3RvcC1jb2xvcj0iIzAwQ0E5MCI+PC9zdG9wPgogICAgICA8c3RvcCBvZmZzZXQ9IjEiIHN0b3AtY29sb3I9IiMwMDVCRTUiPjwvc3RvcD4KICAgIDwvbGluZWFyR3JhZGllbnQ+CiAgICA8Y2xpcFBhdGggaWQ9ImNsaXAwXzBfMjg5Ij4KICAgICAgPHJlY3Qgd2lkdGg9IjE3OCIgaGVpZ2h0PSI1MCIgZmlsbD0id2hpdGUiPjwvcmVjdD4KICAgIDwvY2xpcFBhdGg+CiAgPC9kZWZzPgo8L3N2Zz4K" alt="Zuru" class="header-logo">
    <div class="header-divider"></div>
    <div class="header-title">
      <h1>Partners Program 2026</h1>
      <p>Dashboard de Produccion por Operador</p>
    </div>
  </div>
  <div class="header-badge">GENERADO: {generation_date}</div>
</div>

<div class="container">

  <!-- Filtros -->
  <div class="filter-bar">
    <label>Operador:</label>
    <select id="operatorFilter" onchange="filterData()">
      <option value="__ALL__">Todos los operadores</option>
    </select>
    <label>Producto:</label>
    <select id="productFilter" onchange="filterData()">
      <option value="__ALL__">Todos los productos</option>
    </select>
    <label>Buscar:</label>
    <input type="text" id="searchInput" placeholder="Buscar operador..." oninput="searchOperator()">
    <button class="btn btn-outline" onclick="resetFilters()">Limpiar filtros</button>
    <button class="btn btn-primary" onclick="exportCSV()">Exportar CSV</button>
  </div>

  <!-- KPIs -->
  <div class="kpi-grid" id="kpiGrid">
    <div class="kpi-card green">
      <div class="kpi-label">Operadores en Programa</div>
      <div class="kpi-value" id="kpiQualified">{len(qualified)}</div>
      <div class="kpi-sub">de {total_operators} operadores totales</div>
    </div>
    <div class="kpi-card blue">
      <div class="kpi-label">Prima Total 2026</div>
      <div class="kpi-value" id="kpiPrima2026">$ {total_prima_2026:,.0f}</div>
      <div class="kpi-sub">USD produccion acumulada</div>
    </div>
    <div class="kpi-card orange">
      <div class="kpi-label">Score Promedio</div>
      <div class="kpi-value" id="kpiAvgScore">{avg_score}</div>
      <div class="kpi-sub">Score final promedio</div>
    </div>
    <div class="kpi-card green">
      <div class="kpi-label">Crecimiento General</div>
      <div class="kpi-value" id="kpiGrowth">{overall_growth}%</div>
      <div class="kpi-sub">vs 2025</div>
    </div>
  </div>

  <!-- Detalle Operador (oculto por defecto) -->
  <div class="operator-detail" id="operatorDetail">
    <div class="detail-header">
      <h2 id="detailName"></h2>
      <p id="detailStatus"></p>
    </div>
    <div class="detail-body">
      <div class="detail-grid" id="detailGrid"></div>
      <div class="gauge-container" id="gaugeContainer"></div>
      <div class="score-formula">
        <strong>Score Final</strong> = (Score Produccion x 60%) + (Score Crecimiento x 40%)
      </div>
      <div id="productBreakdown" style="margin-top:20px"></div>
    </div>
  </div>

  <!-- Comparativo y Scores -->
  <div class="grid-2">
    <div class="card">
      <div class="card-header">
        <h3>Comparativo Prima Mismo Periodo 2025 vs 2026 (Top 15)</h3>
      </div>
      <div class="card-body">
        <div class="legend">
          <div class="legend-item"><div class="legend-dot c2025"></div> Prima 2025</div>
          <div class="legend-item"><div class="legend-dot c2026"></div> Prima 2026</div>
        </div>
        <div class="chart-container" id="compChart"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header">
        <h3>Distribucion de Score Final</h3>
      </div>
      <div class="card-body">
        <div id="scoreDistribution"></div>
      </div>
    </div>
  </div>

  <!-- Tabla Principal -->
  <div class="card">
    <div class="card-header">
      <h3>Ranking de Operadores - Zuru Partners Program 2026</h3>
      <span class="badge badge-blue" id="tableCount">{total_operators} operadores</span>
    </div>
    <div class="card-body scroll-table">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Operador</th>
            <th class="text-right">Prima 2025 Total</th>
            <th class="text-right">Prima 2025 Periodo</th>
            <th class="text-right">Prima 2026</th>
            <th class="text-right">Crecimiento</th>
            <th class="text-center">Score 1</th>
            <th class="text-center">Score 2</th>
            <th class="text-center">Score Final</th>
            <th class="text-center">Estado</th>
          </tr>
        </thead>
        <tbody id="mainTable"></tbody>
      </table>
    </div>
  </div>

  <!-- Tablas de Referencia -->
  <div class="grid-2" style="margin-top:24px;">
    <div class="card">
      <div class="card-header"><h3>Rangos Score 1 - Prima Operador</h3></div>
      <div class="card-body">
        <table>
          <thead><tr><th>Rango Prima</th><th class="text-center">Score</th></tr></thead>
          <tbody>
            <tr><td>Mayor a USD 40,000</td><td class="text-center"><span class="badge badge-success">100</span></td></tr>
            <tr><td>USD 30,000 - USD 40,000</td><td class="text-center"><span class="badge badge-success">90</span></td></tr>
            <tr><td>USD 20,000 - USD 30,000</td><td class="text-center"><span class="badge badge-blue">80</span></td></tr>
            <tr><td>USD 15,000 - USD 20,000</td><td class="text-center"><span class="badge badge-blue">70</span></td></tr>
            <tr><td>USD 10,000 - USD 15,000</td><td class="text-center"><span class="badge badge-warning">60</span></td></tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h3>Rangos Score 2 - % Crecimiento</h3></div>
      <div class="card-body">
        <table>
          <thead><tr><th>% Crecimiento</th><th class="text-center">Score</th></tr></thead>
          <tbody>
            <tr><td>60% o mas</td><td class="text-center"><span class="badge badge-success">100</span></td></tr>
            <tr><td>50% - 59%</td><td class="text-center"><span class="badge badge-success">95</span></td></tr>
            <tr><td>40% - 49%</td><td class="text-center"><span class="badge badge-success">90</span></td></tr>
            <tr><td>30% - 39%</td><td class="text-center"><span class="badge badge-blue">80</span></td></tr>
            <tr><td>25% - 29%</td><td class="text-center"><span class="badge badge-blue">70</span></td></tr>
            <tr><td>20% - 24%</td><td class="text-center"><span class="badge badge-warning">60</span></td></tr>
            <tr><td>15% - 19%</td><td class="text-center"><span class="badge badge-warning">50</span></td></tr>
            <tr><td>10% - 14%</td><td class="text-center"><span class="badge badge-danger">40</span></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<div class="footer">
  Zuru Partners Program 2026 &bull; Dashboard generado automaticamente &bull; Datos actualizados al {generation_date}
</div>

<script>
const ALL_DATA = {data_json};
const ALL_PRODUCTS = {products_json};
let filteredData = [...ALL_DATA];
let activeProductFilter = '__ALL__';

const PRIMA_RANGES = [[40000, 100],[30000, 90],[20000, 80],[15000, 70],[10000, 60]];
const GROWTH_RANGES = [[0.60, 100],[0.50, 95],[0.40, 90],[0.30, 80],[0.25, 70],[0.20, 60],[0.15, 50],[0.10, 40]];
const THRESHOLDS = {{'Chubb - Int.': 10000, 'Lampe - Carga': 20000}};
const DEFAULT_THRESHOLD = 10000;

function getThreshold(prodName) {{
  return THRESHOLDS[prodName] || DEFAULT_THRESHOLD;
}}

function calcScore1(prima) {{
  for (const [low, score] of PRIMA_RANGES) {{ if (prima >= low) return score; }}
  return 0;
}}
function calcScore2(growth) {{
  if (growth == null || growth < 0.10) return 0;
  for (const [low, score] of GROWTH_RANGES) {{ if (growth >= low) return score; }}
  return 0;
}}

function checkEligibility(d, prodVal) {{
  if (prodVal !== '__ALL__') {{
    const prod = d.products ? d.products.find(p => p.producto === prodVal) : null;
    if (!prod) return false;
    return prod.prima_2026 >= getThreshold(prodVal);
  }}
  if (!d.products) return false;
  return d.products.some(p => p.prima_2026 >= getThreshold(p.producto));
}}

function recalcForProduct(data, prodVal) {{
  if (prodVal === '__ALL__') {{
    return data.map(d => ({{
      ...d,
      eligible_program: checkEligibility(d, '__ALL__'),
      qualified: checkEligibility(d, '__ALL__') && d.meets_growth,
    }}));
  }}
  return data.filter(d => d.products && d.products.some(p => p.producto === prodVal)).map(d => {{
    const prod = d.products.find(p => p.producto === prodVal);
    const p25 = prod ? prod.prima_2025 : 0;
    const p25t = prod ? prod.prima_2025_total : 0;
    const p26 = prod ? prod.prima_2026 : 0;
    const growth = p25 > 0 ? Math.round((p26 - p25) / p25 * 10000) / 10000 : null;
    const s1 = calcScore1(p26);
    const s2 = calcScore2(growth);
    const sf = Math.round((s1 * 0.6 + s2 * 0.4) * 10) / 10;
    const threshold = getThreshold(prodVal);
    const eligible = p26 >= threshold;
    const meetsGrowth = growth != null && growth >= 0.10;
    return {{
      ...d,
      prima_2025: p25,
      prima_2025_total: p25t,
      prima_2026: p26,
      growth: growth,
      growth_pct: growth != null ? Math.round(growth * 1000) / 10 : null,
      score1: s1,
      score2: s2,
      score_final: sf,
      eligible_program: eligible,
      meets_growth: meetsGrowth,
      qualified: eligible && meetsGrowth,
    }};
  }});
}}

function rerank(data) {{
  data.sort((a, b) => b.score_final - a.score_final);
  data.forEach((d, i) => {{ d.rank = i + 1; }});
  return data;
}}

function fmt(n) {{ return n == null ? '-' : '$ ' + n.toLocaleString('en-US', {{minimumFractionDigits: 0, maximumFractionDigits: 0}}); }}
function fmtPct(n) {{ return n == null ? 'N/A' : n.toFixed(1) + '%'; }}

function getScoreColor(score) {{
  if (score >= 80) return '#00CA90';
  if (score >= 60) return '#005BE5';
  if (score >= 40) return '#FF9800';
  return '#E53935';
}}

function getUrlParam(name) {{
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}}

function init() {{
  const sel = document.getElementById('operatorFilter');
  ALL_DATA.forEach(d => {{
    const opt = document.createElement('option');
    opt.value = d.name;
    opt.textContent = d.name;
    sel.appendChild(opt);
  }});
  const psel = document.getElementById('productFilter');
  ALL_PRODUCTS.forEach(p => {{
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    psel.appendChild(opt);
  }});

  // Auto-filter by URL param: ?operador=NombreOperador
  const paramOp = getUrlParam('operador');
  if (paramOp) {{
    const match = ALL_DATA.find(d => d.name === paramOp);
    if (match) {{
      sel.value = paramOp;
      // Hide filter bar in embedded/operator mode
      document.querySelector('.filter-bar').style.display = 'none';
      filteredData = [match];
      renderAll();
      showOperatorDetail(match);
      return;
    }}
  }}

  renderAll();
}}

function filterData() {{
  const opVal = document.getElementById('operatorFilter').value;
  const prodVal = document.getElementById('productFilter').value;
  activeProductFilter = prodVal;

  let data = recalcForProduct([...ALL_DATA], prodVal);
  data = rerank(data);

  if (opVal !== '__ALL__') {{
    data = data.filter(d => d.name === opVal);
    if (data.length === 1) showOperatorDetail(data[0]);
    else document.getElementById('operatorDetail').classList.remove('active');
  }} else {{
    document.getElementById('operatorDetail').classList.remove('active');
  }}

  filteredData = data;
  renderAll();
}}

function searchOperator() {{
  const q = document.getElementById('searchInput').value.toLowerCase();
  activeProductFilter = document.getElementById('productFilter').value;
  let data = recalcForProduct([...ALL_DATA], activeProductFilter);
  data = rerank(data);
  if (q) {{ data = data.filter(d => d.name.toLowerCase().includes(q)); }}
  filteredData = data;
  document.getElementById('operatorDetail').classList.remove('active');
  renderAll();
}}

function resetFilters() {{
  document.getElementById('operatorFilter').value = '__ALL__';
  document.getElementById('productFilter').value = '__ALL__';
  document.getElementById('searchInput').value = '';
  activeProductFilter = '__ALL__';
  filteredData = rerank([...ALL_DATA]);
  document.getElementById('operatorDetail').classList.remove('active');
  renderAll();
}}

function updateKPIs() {{
  const d = filteredData;
  const qualified = d.filter(x => x.qualified).length;
  const total = d.length;
  const prima26 = d.reduce((s,x) => s + x.prima_2026, 0);
  const prima25 = d.reduce((s,x) => s + x.prima_2025, 0);
  const avgScore = total > 0 ? (d.reduce((s,x) => s + x.score_final, 0) / total).toFixed(1) : 0;
  const growth = prima25 > 0 ? ((prima26 - prima25) / prima25 * 100).toFixed(1) : '0.0';

  document.getElementById('kpiQualified').textContent = qualified;
  document.querySelector('#kpiQualified').closest('.kpi-card').querySelector('.kpi-sub').textContent = 'de ' + total + ' operadores totales';
  document.getElementById('kpiPrima2026').textContent = '$ ' + prima26.toLocaleString('en-US', {{maximumFractionDigits: 0}});
  document.getElementById('kpiAvgScore').textContent = avgScore;
  document.getElementById('kpiGrowth').textContent = growth + '%';
}}

function renderTable() {{
  const tbody = document.getElementById('mainTable');
  tbody.innerHTML = '';
  document.getElementById('tableCount').textContent = filteredData.length + ' operadores';

  filteredData.forEach((d, i) => {{
    const growthStr = d.growth_pct != null ? d.growth_pct.toFixed(1) + '%' : 'N/A';
    const growthClass = d.growth_pct != null && d.growth_pct >= 10 ? 'color:var(--accent-dark)' : d.growth_pct != null ? 'color:var(--danger)' : '';
    const statusBadge = d.qualified
      ? '<span class="badge badge-success">Calificado</span>'
      : d.eligible_program && !d.meets_growth
        ? '<span class="badge badge-warning">Sin crecim.</span>'
        : '<span class="badge badge-danger">No califica</span>';
    const scoreColor = getScoreColor(d.score_final);

    tbody.innerHTML += '<tr style="cursor:pointer" onclick="selectOperator(\\'' + d.name.replace(/'/g, "\\\\'") + '\\')">' +
      '<td class="mono text-center">' + d.rank + '</td>' +
      '<td><strong>' + d.name + '</strong></td>' +
      '<td class="text-right mono" style="color:var(--text-secondary)">' + fmt(d.prima_2025_total) + '</td>' +
      '<td class="text-right mono">' + fmt(d.prima_2025) + '</td>' +
      '<td class="text-right mono" style="font-weight:600">' + fmt(d.prima_2026) + '</td>' +
      '<td class="text-right mono" style="' + growthClass + '">' + growthStr + '</td>' +
      '<td class="text-center"><span class="badge badge-blue">' + d.score1 + '</span></td>' +
      '<td class="text-center"><span class="badge badge-blue">' + d.score2 + '</span></td>' +
      '<td class="text-center"><div style="display:flex;align-items:center;gap:6px;justify-content:center"><div class="score-bar" style="width:60px"><div class="score-bar-fill" style="width:' + d.score_final + '%;background:' + scoreColor + '"></div></div><strong>' + d.score_final + '</strong></div></td>' +
      '<td class="text-center">' + statusBadge + '</td></tr>';
  }});
}}

function renderCompChart() {{
  const container = document.getElementById('compChart');
  const top = [...filteredData].sort((a,b) => b.prima_2026 - a.prima_2026).slice(0, 15);
  const maxVal = Math.max(...top.map(d => Math.max(d.prima_2025, d.prima_2026)), 1);

  container.innerHTML = '';
  top.forEach(d => {{
    const w25 = Math.max((d.prima_2025 / maxVal) * 100, 0.5);
    const w26 = Math.max((d.prima_2026 / maxVal) * 100, 0.5);
    container.innerHTML += '<div class="bar-row">' +
      '<div class="bar-label" title="' + d.name + '">' + d.name + '</div>' +
      '<div class="bar-group">' +
        '<div class="bar-track"><div class="bar bar-2025" style="width:' + w25 + '%">' + (w25 > 15 ? fmt(d.prima_2025) : '') + '</div></div>' +
        '<div class="bar-track"><div class="bar bar-2026" style="width:' + w26 + '%">' + (w26 > 15 ? fmt(d.prima_2026) : '') + '</div></div>' +
      '</div>' +
      '<div class="bar-values">' + fmt(d.prima_2026) + '</div></div>';
  }});
}}

function renderScoreDist() {{
  const container = document.getElementById('scoreDistribution');
  const ranges = [
    {{ label: '90 - 100', min: 90, max: 101, color: '#00CA90' }},
    {{ label: '70 - 89', min: 70, max: 90, color: '#005BE5' }},
    {{ label: '50 - 69', min: 50, max: 70, color: '#FF9800' }},
    {{ label: '30 - 49', min: 30, max: 50, color: '#E53935' }},
    {{ label: '0 - 29', min: 0, max: 30, color: '#9CA3AF' }},
  ];

  const total = filteredData.length || 1;
  let html = '';

  ranges.forEach(r => {{
    const count = filteredData.filter(d => d.score_final >= r.min && d.score_final < r.max).length;
    const pct = (count / total * 100).toFixed(0);
    html += '<div style="margin-bottom:14px">' +
      '<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
        '<span style="font-size:13px;font-weight:600">' + r.label + '</span>' +
        '<span style="font-size:12px;color:var(--text-secondary)">' + count + ' (' + pct + '%)</span>' +
      '</div>' +
      '<div class="score-bar" style="height:12px">' +
        '<div class="score-bar-fill" style="width:' + pct + '%;background:' + r.color + '"></div>' +
      '</div></div>';
  }});

  container.innerHTML = html;
}}

function createGauge(value, label, color) {{
  const pct = value / 100;
  const r = 50;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - pct);
  return '<div class="gauge">' +
    '<svg width="120" height="120" viewBox="0 0 120 120">' +
      '<circle cx="60" cy="60" r="' + r + '" fill="none" stroke="#F3F4F6" stroke-width="10"/>' +
      '<circle cx="60" cy="60" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="10" stroke-dasharray="' + circ + '" stroke-dashoffset="' + offset + '" stroke-linecap="round"/>' +
    '</svg>' +
    '<div class="gauge-label"><div class="val">' + value + '</div><div class="lbl">' + label + '</div></div></div>';
}}

function showOperatorDetail(d) {{
  const detail = document.getElementById('operatorDetail');
  detail.classList.add('active');
  document.getElementById('detailName').textContent = d.name;
  document.getElementById('detailStatus').textContent = d.qualified
    ? 'Calificado para Zuru Partners Program 2026'
    : 'Aun no califica para el programa';

  document.getElementById('detailGrid').innerHTML =
    '<div class="detail-metric"><div class="label">Prima 2025</div><div class="value" style="color:var(--text-secondary)">' + fmt(d.prima_2025) + '</div></div>' +
    '<div class="detail-metric"><div class="label">Prima 2026</div><div class="value" style="color:var(--accent-dark)">' + fmt(d.prima_2026) + '</div></div>' +
    '<div class="detail-metric"><div class="label">Crecimiento</div><div class="value" style="color:' + (d.growth_pct >= 10 ? 'var(--accent-dark)' : 'var(--danger)') + '">' + fmtPct(d.growth_pct) + '</div></div>' +
    '<div class="detail-metric"><div class="label">Ranking</div><div class="value" style="color:var(--blue)">#' + d.rank + '</div><div class="sub">de ' + ALL_DATA.length + '</div></div>';

  document.getElementById('gaugeContainer').innerHTML =
    createGauge(d.score1, 'Score 1 (60%)', '#005BE5') +
    createGauge(d.score2, 'Score 2 (40%)', '#FF9800') +
    createGauge(d.score_final, 'Score Final', getScoreColor(d.score_final));

  // Product breakdown table
  const pb = document.getElementById('productBreakdown');
  if (d.products && d.products.length > 0) {{
    let html = '<h3 style="font-size:14px;font-weight:700;color:var(--primary);margin-bottom:12px">Desglose por Producto</h3>';
    html += '<table><thead><tr><th>Producto</th><th class="text-right">Prima 2025</th><th class="text-right">Prima 2026</th><th class="text-right">Variacion</th></tr></thead><tbody>';
    d.products.forEach(p => {{
      const diff = p.prima_2026 - p.prima_2025;
      const diffColor = diff >= 0 ? 'var(--accent-dark)' : 'var(--danger)';
      const diffSign = diff >= 0 ? '+' : '';
      html += '<tr><td><strong>' + p.producto + '</strong></td>' +
        '<td class="text-right mono">' + fmt(p.prima_2025) + '</td>' +
        '<td class="text-right mono" style="font-weight:600">' + fmt(p.prima_2026) + '</td>' +
        '<td class="text-right mono" style="color:' + diffColor + '">' + diffSign + fmt(diff).replace('$ ', '$ ') + '</td></tr>';
    }});
    html += '</tbody></table>';
    pb.innerHTML = html;
  }} else {{
    pb.innerHTML = '';
  }}

  detail.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}

function selectOperator(name) {{
  document.getElementById('operatorFilter').value = name;
  const d = ALL_DATA.find(x => x.name === name);
  if (d) showOperatorDetail(d);
}}

function exportCSV() {{
  let csv = 'Rank,Operador,Prima 2025 Total,Prima 2025 Periodo,Prima 2026,Crecimiento %,Score 1,Score 2,Score Final,Calificado\\n';
  filteredData.forEach(d => {{
    csv += d.rank + ',"' + d.name + '",' + d.prima_2025_total + ',' + d.prima_2025 + ',' + d.prima_2026 + ',' +
      (d.growth_pct != null ? d.growth_pct : '') + ',' + d.score1 + ',' + d.score2 + ',' +
      d.score_final + ',' + (d.qualified ? 'Si' : 'No') + '\\n';
  }});
  const blob = new Blob([csv], {{ type: 'text/csv' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'zuru_partners_2026.csv'; a.click();
  URL.revokeObjectURL(url);
}}

function renderAll() {{
  updateKPIs();
  renderTable();
  renderCompChart();
  renderScoreDist();
}}

init();
</script>
</body>
</html>"""
    return html


def main():
    print("=" * 60)
    print("  ZURU Partners Program 2026 - Dashboard Generator")
    print("=" * 60)
    print()

    rows = fetch_data()
    data, products = process_data(rows)

    print(f"Se procesaron {len(data)} operadores.")
    print(f"Productos encontrados: {len(products)}")
    qualified = [d for d in data if d["qualified"]]
    print(f"Operadores calificados: {len(qualified)}")
    print()

    html = generate_html(data, products)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zuru_dashboard.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generado exitosamente!")
    print(f"Archivo: {output_path}")
    print()
    print("Abre el archivo HTML en tu navegador para ver el dashboard.")


if __name__ == "__main__":
    main()
