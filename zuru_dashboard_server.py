#!/usr/bin/env python3
"""
ZURU Partners Program 2026 - Dashboard Server (Tiempo Real)
============================================================
Servidor web que muestra el dashboard con datos en tiempo real
desde la base de datos MySQL. Los datos se actualizan cada vez
que se carga o refresca la página.

Requisitos:
    pip install mysql-connector-python flask

Uso:
    python zuru_dashboard_server.py

Luego abre en tu navegador: http://localhost:5000
El dashboard se actualizará automáticamente cada 5 minutos,
o puedes refrescar la página manualmente en cualquier momento.
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

try:
    from flask import Flask, Response
except ImportError:
    print("=" * 60)
    print("ERROR: Necesitas instalar Flask")
    print("Ejecuta: pip install flask")
    print("=" * 60)
    sys.exit(1)

# ─── Configuración ───
DB_CONFIG = {
    "host": "34.125.225.64",
    "database": "EMI",
    "user": "ddi",
    "password": "DDI4ever%",
}

# Puerto del servidor (puedes cambiarlo si ya está en uso)
SERVER_PORT = 5000

# Auto-refresh en segundos (300 = 5 minutos)
AUTO_REFRESH_SECONDS = 300

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
    return rows


def process_data(rows):
    operators = {}
    products_set = set()

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
            operators[name]["prima_2025_total"] += prima
            operators[name]["products"][producto]["prima_2025_total"] += prima
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

        eligible = False
        for pname, pdata in data["products"].items():
            threshold = MIN_PRIMA_BY_PRODUCT.get(pname, MIN_PRIMA_DEFAULT)
            if pdata["prima_2026"] >= threshold:
                eligible = True
                break

        meets_growth = growth is not None and growth >= MIN_GROWTH

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


# ─── Import the HTML generator from the original script ───
# We read the generate_html function from zuru_dashboard.py
# But since it's very large, we import it directly

# First, check if the original file exists in the same directory
_script_dir = os.path.dirname(os.path.abspath(__file__))
_original_script = os.path.join(_script_dir, "zuru_dashboard.py")

if os.path.exists(_original_script):
    import importlib.util
    spec = importlib.util.spec_from_file_location("zuru_dashboard", _original_script)
    _orig_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_orig_module)
    generate_html = _orig_module.generate_html
else:
    print("=" * 60)
    print("ERROR: No se encontró zuru_dashboard.py en la misma carpeta.")
    print(f"Ruta esperada: {_original_script}")
    print("El servidor necesita este archivo para generar el HTML.")
    print("=" * 60)
    sys.exit(1)


# ─── Flask App ───
app = Flask(__name__)


@app.route("/")
def dashboard():
    """Genera el dashboard con datos frescos de la base de datos."""
    try:
        rows = fetch_data()
        data, products = process_data(rows)
        html = generate_html(data, products)

        # Inject auto-refresh meta tag into the HTML <head>
        refresh_meta = f'<meta http-equiv="refresh" content="{AUTO_REFRESH_SECONDS}">'
        # Also inject a small JS snippet showing last update time and countdown
        update_indicator = f'''
        <script>
        (function() {{
            const REFRESH_SECS = {AUTO_REFRESH_SECONDS};
            const loadTime = new Date();

            function createIndicator() {{
                const bar = document.createElement('div');
                bar.id = 'live-update-bar';
                bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:linear-gradient(135deg,#001C43,#005BE5);color:white;padding:8px 20px;font-family:Inter,sans-serif;font-size:13px;display:flex;justify-content:space-between;align-items:center;z-index:99999;box-shadow:0 -2px 10px rgba(0,0,0,0.15);';

                const left = document.createElement('span');
                left.innerHTML = '<span style="display:inline-block;width:8px;height:8px;background:#00CA90;border-radius:50%;margin-right:8px;animation:pulse 2s infinite;"></span><strong>EN VIVO</strong> — Datos actualizados desde MySQL';

                const right = document.createElement('span');
                right.id = 'update-countdown';

                bar.appendChild(left);
                bar.appendChild(right);
                document.body.appendChild(bar);

                // Add padding to body so content isn't hidden behind the bar
                document.body.style.paddingBottom = '50px';

                // Add pulse animation
                const style = document.createElement('style');
                style.textContent = '@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}';
                document.head.appendChild(style);
            }}

            function updateCountdown() {{
                const now = new Date();
                const elapsed = Math.floor((now - loadTime) / 1000);
                const remaining = Math.max(0, REFRESH_SECS - elapsed);
                const mins = Math.floor(remaining / 60);
                const secs = remaining % 60;
                const timeStr = loadTime.toLocaleTimeString('es-PE');
                const el = document.getElementById('update-countdown');
                if (el) {{
                    el.innerHTML = 'Ultima actualizacion: ' + timeStr + ' · Proxima en: <strong>' + mins + 'm ' + secs.toString().padStart(2,'0') + 's</strong>';
                }}
            }}

            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', function() {{ createIndicator(); updateCountdown(); setInterval(updateCountdown, 1000); }});
            }} else {{
                createIndicator(); updateCountdown(); setInterval(updateCountdown, 1000);
            }}
        }})();
        </script>
        '''

        # Insert the meta tag and indicator into the HTML
        html = html.replace('<head>', f'<head>\n    {refresh_meta}', 1)
        html = html.replace('</body>', f'{update_indicator}\n</body>', 1)

        return Response(html, mimetype='text/html')

    except mysql.connector.Error as e:
        return Response(
            f"""<html><body style="font-family:Inter,sans-serif;padding:40px;text-align:center;">
            <h1 style="color:#e74c3c;">Error de Conexion a Base de Datos</h1>
            <p style="color:#666;">No se pudo conectar a MySQL: {e}</p>
            <p>Verifica la conexion a internet y la configuracion de la base de datos.</p>
            <button onclick="location.reload()" style="padding:10px 30px;background:#005BE5;color:white;border:none;border-radius:8px;cursor:pointer;font-size:16px;">Reintentar</button>
            </body></html>""",
            mimetype='text/html',
            status=500
        )
    except Exception as e:
        return Response(
            f"""<html><body style="font-family:Inter,sans-serif;padding:40px;text-align:center;">
            <h1 style="color:#e74c3c;">Error</h1>
            <p style="color:#666;">{type(e).__name__}: {e}</p>
            <button onclick="location.reload()" style="padding:10px 30px;background:#005BE5;color:white;border:none;border-radius:8px;cursor:pointer;font-size:16px;">Reintentar</button>
            </body></html>""",
            mimetype='text/html',
            status=500
        )


if __name__ == "__main__":
    print("=" * 60)
    print("  ZURU Partners Program 2026 - Dashboard EN VIVO")
    print("=" * 60)
    print()
    print(f"  Servidor iniciado en: http://localhost:{SERVER_PORT}")
    print(f"  Auto-refresh cada: {AUTO_REFRESH_SECONDS // 60} minutos")
    print()
    print("  Abre la URL en tu navegador para ver el dashboard.")
    print("  Los datos se actualizan desde MySQL en cada carga.")
    print()
    print("  Presiona Ctrl+C para detener el servidor.")
    print("=" * 60)
    print()
    app.run(host="0.0.0.0", port=SERVER_PORT, debug=False)
