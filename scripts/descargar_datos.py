#!/usr/bin/env python3
"""
FireCal — descarga y ARMONIZA focos de calor de NASA FIRMS (MODIS + VIIRS).

Crea/actualiza data/focos.js (lo lee la página) y data/series/<CLAVE>.csv.
Solo usa la biblioteca estándar de Python (no hace falta instalar nada).

FORMAS DE USO
-------------
1) Por país, con la API de FIRMS (necesita MAP_KEY). Descarga el rectángulo
   del país y se queda solo con los focos dentro de su contorno:
       python scripts/descargar_datos.py --pais PER

2) Por rectángulo (oeste,sur,este,norte), con la API:
       python scripts/descargar_datos.py --bbox -75.9,-11.5,-70.5,-7.3 --clave UCAYALI --nombre "Ucayali"

3) RÁPIDO: con los CSV anuales por país que se descargan a mano de
   https://firms.modaps.eosdis.nasa.gov/country/  (MODIS y VIIRS S-NPP)
       python scripts/descargar_datos.py --csv "descargas/*.csv" --pais PER

   La opción 3 es la más rápida para 25 años de historia: la API entrega
   como máximo 5 días por consulta y tiene límite de transacciones.

MAP_KEY
-------
Pídela gratis en https://firms.modaps.eosdis.nasa.gov/api/map_key/ y guárdala
en un archivo .env en la raíz del proyecto (NUNCA lo subas a GitHub):
       FIRMS_MAP_KEY=tu_clave_de_32_caracteres

ARMONIZACIÓN (resumen)
----------------------
- Filtro: confianza nominal/alta y tipo 0 (vegetación) cuando existe la columna.
- Días-celda: cuántas celdas de 0,01° (~1 km) tuvieron >= 1 foco cada día.
- VIIRS S-NPP (desde 2012-01-20) es la referencia. Antes de VIIRS se usa
  MODIS multiplicado por un factor VIIRS/MODIS calculado para cada mes del
  año en el periodo en que ambos sensores se superponen.
"""
import argparse
import csv
import glob
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"
CACHE = RAIZ / "cache"
API = "https://firms.modaps.eosdis.nasa.gov/api"
INICIO_SERIE = date(2001, 1, 1)
VIIRS_INICIO = date(2012, 1, 20)
CELDA = 100  # 1/0,01°


# ----------------------------------------------------------------- utilidades
def leer_map_key():
    clave = os.environ.get("FIRMS_MAP_KEY")
    env = RAIZ / ".env"
    if not clave and env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("FIRMS_MAP_KEY"):
                clave = linea.split("=", 1)[1].strip().strip('"').strip("'")
    if not clave:
        sys.exit("Falta la MAP_KEY. Crea un archivo .env con FIRMS_MAP_KEY=tu_clave (ver README).")
    return clave


def pedir(url, intentos=4):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            espera = 5 * (i + 1)
            print(f"   ! error de red ({e}); reintento en {espera}s", file=sys.stderr)
            time.sleep(espera)
    raise RuntimeError(f"No se pudo descargar: {url.split('/csv/')[0]}/…")


def rango_fechas(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


# ------------------------------------------------------- descarga con la API
def disponibilidad(map_key):
    texto = pedir(f"{API}/data_availability/csv/{map_key}/ALL")
    disp = {}
    for fila in csv.DictReader(io.StringIO(texto)):
        try:
            disp[fila["data_id"]] = (date.fromisoformat(fila["min_date"]), date.fromisoformat(fila["max_date"]))
        except (KeyError, ValueError):
            continue
    if not disp:
        sys.exit("La API no devolvió disponibilidad. ¿La MAP_KEY es correcta?\n" + texto[:300])
    return disp


def tramos_por_fuente(disp, sp, nrt, desde, hasta):
    """Usa la versión científica (SP) donde existe y la casi-tiempo-real (NRT) después."""
    tramos = []
    fin_sp = None
    if sp in disp:
        a, b = max(desde, disp[sp][0]), min(hasta, disp[sp][1])
        if a <= b:
            tramos.append((sp, a, b))
            fin_sp = b
    if nrt in disp:
        a = max(desde, disp[nrt][0], (fin_sp + timedelta(days=1)) if fin_sp else desde)
        b = min(hasta, disp[nrt][1])
        if a <= b:
            tramos.append((nrt, a, b))
    return tramos


def descargar_api(map_key, args, desde, hasta):
    disp = disponibilidad(map_key)
    clave = args.clave
    carpeta = CACHE / clave
    carpeta.mkdir(parents=True, exist_ok=True)
    textos = []
    for sp, nrt in (("MODIS_SP", "MODIS_NRT"), ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT")):
        for fuente, a, b in tramos_por_fuente(disp, sp, nrt, desde, hasta):
            if fuente.startswith("VIIRS"):
                args.viirs_fin = b if args.viirs_fin is None else max(args.viirs_fin, b)
            total = (b - a).days // args.dias + 1
            print(f"→ {fuente}: {a} a {b} ({total} consultas)")
            d, n = a, 0
            while d <= b:
                dias = min(args.dias, (b - d).days + 1)
                archivo = carpeta / f"{fuente}_{d.isoformat()}_{dias}.csv"
                if archivo.exists():
                    texto = archivo.read_text(encoding="utf-8")
                else:
                    # La API por país (/api/country) ya no responde: siempre usamos /api/area
                    url = f"{API}/area/csv/{map_key}/{fuente}/{args.bbox}/{dias}/{d.isoformat()}"
                    texto = pedir(url)
                    if "exceed" in texto.lower()[:200]:
                        print("   Límite de transacciones: esperando 2 minutos…", file=sys.stderr)
                        time.sleep(120)
                        continue
                    if texto.lower().startswith(("invalid", "error")):
                        print(f"   ! respuesta de la API: {texto[:200]}", file=sys.stderr)
                        texto = ""
                    else:
                        archivo.write_text(texto, encoding="utf-8")
                    time.sleep(args.pausa)
                textos.append((fuente, texto))
                d += timedelta(days=dias)
                n += 1
                if n % 50 == 0:
                    print(f"   {n}/{total}")
    return textos


# ------------------------------------------------------- límites del país
URL_PAISES = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/ne_50m_admin_0_countries.geojson"


def cargar_pais(iso):
    """Descarga el contorno del país (Natural Earth 1:50m). Devuelve (bbox, filtro(lat, lon))."""
    archivo = CACHE / "ne_50m_admin_0_countries.geojson"
    if not archivo.exists():
        print("Descargando límites de países (Natural Earth)…")
        CACHE.mkdir(exist_ok=True)
        archivo.write_text(pedir(URL_PAISES), encoding="utf-8")
    geo = json.loads(archivo.read_text(encoding="utf-8"))
    f = next((x for x in geo["features"]
              if iso in (x["properties"].get("ISO_A3"), x["properties"].get("ADM0_A3"))), None)
    if not f:
        sys.exit(f"No encontré el país {iso}. Usa el código ISO de 3 letras (PER, BRA, BOL…).")
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    bbox = [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)]

    def en_anillo(x, y, anillo):
        dentro = False
        j = len(anillo) - 1
        for i in range(len(anillo)):
            xi, yi = anillo[i][0], anillo[i][1]
            xj, yj = anillo[j][0], anillo[j][1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                dentro = not dentro
            j = i
        return dentro

    def filtro(lat, lon):
        return any(en_anillo(lon, lat, poly[0]) and not any(en_anillo(lon, lat, h) for h in poly[1:])
                   for poly in polys)

    return bbox, filtro, f["properties"].get("NAME_ES") or f["properties"].get("NAME")


# ------------------------------------------------------------- procesamiento
def es_viirs(cabecera, fuente=""):
    return "VIIRS" in fuente.upper() or "bright_ti4" in cabecera


def procesar(textos, solo_snpp=True, filtro=None):
    """Devuelve (modis, viirs, extension) donde modis/viirs = {fecha: set(celdas)}."""
    modis, viirs = defaultdict(set), defaultdict(set)
    viirs_otros = defaultdict(set)
    lat_min = lon_min = 999.0
    lat_max = lon_max = -999.0
    leidos = aceptados = 0
    for fuente, texto in textos:
        if not texto.strip():
            continue
        lector = csv.DictReader(io.StringIO(texto))
        if not lector.fieldnames:
            continue
        cab = [c.strip().lower() for c in lector.fieldnames]
        lector.fieldnames = cab
        viirs_archivo = es_viirs(cab, fuente)
        for fila in lector:
            leidos += 1
            try:
                lat, lon = float(fila["latitude"]), float(fila["longitude"])
                fecha = date.fromisoformat(fila["acq_date"][:10])
            except (KeyError, ValueError):
                continue
            tipo = (fila.get("type") or "0").strip()
            if tipo not in ("0", ""):
                continue  # volcanes, fuentes industriales fijas, mar
            conf = (fila.get("confidence") or "").strip().lower()
            if viirs_archivo:
                if conf and conf[0] == "l":
                    continue
            else:
                try:
                    if float(conf) < 30:
                        continue
                except ValueError:
                    pass
            if filtro and not filtro(lat, lon):
                continue  # fuera del país (el rectángulo incluye países vecinos)
            celda = (round(lat * CELDA), round(lon * CELDA))
            aceptados += 1
            lat_min, lat_max = min(lat_min, lat), max(lat_max, lat)
            lon_min, lon_max = min(lon_min, lon), max(lon_max, lon)
            if viirs_archivo:
                sat = (fila.get("satellite") or "N").strip().upper()
                if not solo_snpp or sat in ("N", "NPP", "SUOMI NPP", "SNPP"):
                    viirs[fecha].add(celda)
                else:
                    viirs_otros[fecha].add(celda)
            else:
                modis[fecha].add(celda)
    if solo_snpp and not viirs and viirs_otros:
        print("   (no hay VIIRS S-NPP; se usan los otros satélites VIIRS del archivo)")
        viirs = viirs_otros
    print(f"Filas leídas: {leidos:,} · aceptadas tras el filtro: {aceptados:,}")
    ext = [round(lon_min, 2), round(lat_min, 2), round(lon_max, 2), round(lat_max, 2)] if aceptados else None
    return modis, viirs, ext


def armonizar(modis, viirs, desde, hasta, viirs_fin=None):
    """viirs_fin: último día con datos VIIRS disponibles (después se usa MODIS×k)."""
    m = {d: len(c) for d, c in modis.items()}
    v = {d: len(c) for d, c in viirs.items()}
    modis_fin = max(m) if m else None
    if viirs_fin is None:
        viirs_fin = hasta  # con CSV asumimos que VIIRS cubre hasta el final
    # VIIRS empieza el 20-01-2012 (o el 1 de enero del primer año con datos VIIRS cargados)
    viirs_ini = max(VIIRS_INICIO, date(min(v).year, 1, 1), desde) if v else None

    # Factor VIIRS/MODIS por mes del año en el periodo de superposición
    suma_v, suma_m = defaultdict(int), defaultdict(int)
    if viirs_ini and modis_fin:
        for d in rango_fechas(viirs_ini, min(modis_fin, hasta)):
            suma_v[d.month] += v.get(d, 0)
            suma_m[d.month] += m.get(d, 0)
    total_v, total_m = sum(suma_v.values()), sum(suma_m.values())
    k_global = (total_v / total_m) if total_m else 1.0
    factores = {mes: (suma_v[mes] / suma_m[mes]) if suma_m[mes] >= 30 else k_global for mes in range(1, 13)}
    if not total_m:
        print("   ! No hay superposición MODIS-VIIRS: factor = 1 (sin intercalibrar)")

    serie, filas = [], []
    for d in rango_fechas(INICIO_SERIE, hasta):
        if d < desde:
            serie.append(None)
            continue
        mv, vv = m.get(d, 0), v.get(d, 0)
        if viirs_ini and viirs_ini <= d <= viirs_fin:
            h, src = vv, "VIIRS"
        else:
            h, src = round(mv * factores[d.month]), "MODIS×k"
        serie.append(h)
        filas.append((d.isoformat(), mv, vv, h, src))
    return serie, filas, factores, viirs_ini


# ------------------------------------------------------------------- salida
def leer_focos():
    archivo = DATA / "focos.js"
    if archivo.exists():
        texto = archivo.read_text(encoding="utf-8")
        i = texto.find("{")
        if i >= 0:
            try:
                return json.loads(texto[i:].rstrip().rstrip(";"))
            except json.JSONDecodeError:
                pass
    return {"inicio": INICIO_SERIE.isoformat(), "areas": {}}


def guardar(clave, nombre, bbox, serie, filas, factores, viirs_ini, fuente):
    datos = leer_focos()
    datos["inicio"] = INICIO_SERIE.isoformat()
    datos.setdefault("areas", {})[clave] = {
        "nombre": nombre,
        "bbox": bbox,
        "viirs_desde": viirs_ini.isoformat() if viirs_ini else None,
        "factores_viirs_modis": {str(k): round(x, 3) for k, x in factores.items()},
        "fuente": fuente,
        "actualizado": date.today().isoformat(),
        "diario": serie,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "focos.js").write_text(
        "// Generado por scripts/descargar_datos.py con datos de NASA FIRMS (MODIS + VIIRS S-NPP)\n"
        "window.FIRECAL_DATOS_REALES = " + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    (DATA / "series").mkdir(exist_ok=True)
    with open(DATA / "series" / f"{clave}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "modis_dias_celda", "viirs_dias_celda", "armonizado", "fuente_usada"])
        w.writerows(filas)
    print(f"✔ Guardado data/focos.js (área {clave}) y data/series/{clave}.csv")


# --------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Descarga y armoniza focos de calor de NASA FIRMS.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pais", help="Código ISO de 3 letras (ej. PER, BRA, AUS); filtra por el contorno del país")
    g.add_argument("--bbox", help="oeste,sur,este,norte en grados")
    p.add_argument("--csv", nargs="+", help="Archivos CSV de FIRMS ya descargados (acepta comodines)")
    p.add_argument("--clave", help="Identificador del área (por defecto, el código del país)")
    p.add_argument("--nombre", help="Nombre que se mostrará en la página")
    p.add_argument("--desde", default=INICIO_SERIE.isoformat(), help="AAAA-MM-DD (por defecto 2001-01-01)")
    p.add_argument("--hasta", default=(date.today() - timedelta(days=1)).isoformat(), help="AAAA-MM-DD (por defecto ayer)")
    p.add_argument("--dias", type=int, default=5, help="Días por consulta a la API (máximo 5)")
    p.add_argument("--pausa", type=float, default=0.5, help="Segundos entre consultas")
    p.add_argument("--todos-viirs", action="store_true", help="Incluir NOAA-20/21 además de S-NPP")
    args = p.parse_args()

    desde, hasta = date.fromisoformat(args.desde), date.fromisoformat(args.hasta)
    if desde < INICIO_SERIE:
        sys.exit("--desde no puede ser anterior a 2001-01-01")
    if not (args.pais or args.bbox or args.csv):
        p.error("indica --pais, --bbox o --csv")
    args.dias = max(1, min(5, args.dias))  # la API acepta de 1 a 5 días
    filtro, nombre_pais = None, None
    if args.pais:
        args.pais = args.pais.upper()
        args.clave = (args.clave or args.pais).upper()
        bbox_pais, filtro, nombre_pais = cargar_pais(args.pais)
        args.bbox = ",".join(str(x) for x in bbox_pais)
        print(f"País {args.pais} ({nombre_pais}) · rectángulo {args.bbox}")
    elif not args.clave:
        sys.exit("Con --bbox o --csv indica también --clave (ej. --clave PER)")
    nombre = args.nombre or nombre_pais or args.clave
    args.viirs_fin = None

    if args.csv:
        archivos = sorted({a for patron in args.csv for a in glob.glob(patron)})
        if not archivos:
            sys.exit("No se encontraron archivos CSV.")
        print(f"Leyendo {len(archivos)} archivos CSV…")
        textos = [(Path(a).name, Path(a).read_text(encoding="utf-8", errors="replace")) for a in archivos]
        fuente = "NASA FIRMS (CSV descargados)"
    else:
        textos = descargar_api(leer_map_key(), args, desde, hasta)
        fuente = "NASA FIRMS API"

    modis, viirs, ext = procesar(textos, solo_snpp=not args.todos_viirs, filtro=filtro)
    if not modis and not viirs:
        sys.exit("No se encontraron focos con esos parámetros.")
    serie, filas, factores, viirs_ini = armonizar(modis, viirs, desde, hasta, args.viirs_fin)
    bbox = [float(x) for x in args.bbox.split(",")] if args.bbox else ext
    print("Factores VIIRS/MODIS por mes:", ", ".join(f"{m}:{x:.2f}" for m, x in factores.items()))
    guardar(args.clave, nombre, bbox, serie, filas, factores, viirs_ini, fuente)


if __name__ == "__main__":
    main()
