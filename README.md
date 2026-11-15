# 🔥 FireCal: calendario mundial de actividad de fuego

**NASA Space Apps Challenge 2026** · Equipo *Espace Apps Ideas Innovadoras*

FireCal es una aplicación web que **armoniza los focos de calor satelitales de la NASA (MODIS + VIIRS)** y los convierte en un **calendario de actividad de fuego** para cualquier país o área del mundo. Ayuda a servicios de alerta temprana, científicos y gestores de tierras a ver:

- 📅 **Cuándo** se quema: calendario año × mes y vista día a día.
- 🔺 **Qué es inusual**: anomalías respecto a lo normal (puntaje z).
- ⏳ **Cuál es la temporada crítica**: la ventana que concentra el 80 % del fuego, con su pico.
- 📈 **Hacia dónde va**: tendencia anual (Mann-Kendall + pendiente de Sen).
- 🚨 **Cómo vamos ahora**: últimos 30 días comparados con los mismos días de años anteriores.
- 🌧️ **Por qué**: lluvia y humedad del año (NASA POWER).
- 🛰️ **Cómo se veía**: haz clic en un día y el mapa muestra la imagen satelital de ese día (NASA GIBS).

## Enfoque: Huánuco y Amazonía peruana

La página abre en **Huánuco** y tiene botones para la **Amazonía peruana** (Loreto, Ucayali, Madre de Dios, San Martín y Amazonas, juntos) y para cada departamento amazónico. Su historial real 2001–2026 está en `data/focos.js`; los límites salen de geoBoundaries (gbOpen PER ADM1, dominio público) y están en `data/regiones.js`.

El **cuadro estadístico mensual** muestra, para cada mes: promedio, desviación estándar, mínimo y máximo (con su año), valor del año elegido, cuántas veces lo normal, puntaje z, estado, % del fuego anual y tendencia del mes (pendiente de Sen + Mann-Kendall).

## Qué hace FireCal que no hacen FIRMS ni Earthdata Search

| | FIRMS Fire Map | Earthdata Search | **FireCal** |
|---|---|---|---|
| Focos de calor en un mapa | ✅ | ❌ (archivos) | ✅ |
| Une satélites antiguos (MODIS) y modernos (VIIRS) en una serie comparable | ❌ | ❌ | ✅ con factor por mes y **marca de era** (azul = MODIS, naranja = VIIRS) |
| Calendario de actividad año × mes y día a día | ❌ | ❌ | ✅ |
| ¿Es un mes normal o inusual? (anomalías, puntaje z) | ❌ | ❌ | ✅ |
| Temporada crítica, tendencia con significancia (Mann-Kendall) | ❌ | ❌ | ✅ |
| Agrupa focos en **incendios** con lugar (provincia), duración, área e historial día a día | ❌ | ❌ | ✅ |
| Animación de cómo avanzaron los incendios | parcial (barra de tiempo) | ❌ | ✅ |
| Clima del mismo periodo (NASA POWER) | ❌ | ❌ | ✅ |
| En español, enfocado en Huánuco y la Amazonía | ❌ | ❌ | ✅ |

## Arquitectura híbrida

| Parte | De dónde salen los datos | Cuándo |
|---|---|---|
| **Historial 2001 → hoy** (calendario, anomalías, temporada, tendencia) | Pre-calculado con `scripts/descargar_datos.py` → `data/focos.js` | Una vez por país (Perú, Bolivia, Colombia, Ecuador y Chile ya incluidos) |
| **🔥 Incendios en el mapa** (último mes por defecto; también 3 meses, una temporada, un año o fechas exactas) | La página consulta **directamente la API de NASA FIRMS** con tu MAP_KEY. Agrupa los focos en incendios, ubica la provincia y calcula la zona afectada. Se guarda en **caché** (6 h si es reciente, 30 días si es histórico) | Al elegir un área (último mes) o cuando el usuario lo pide; para periodos largos avisa cuánto tardará y muestra el avance |
| **En vivo C · historial del área** (3 años, 5 años o desde 2012) | API de FIRMS (VIIRS) → se guarda en el navegador | Una vez por país y navegador |
| **Imágenes del mapa** | NASA GIBS en vivo | Siempre |
| **Clima** | NASA POWER en vivo | Siempre |

La MAP_KEY se escribe en la página (panel "3 · En vivo") y se guarda **solo en tu navegador**: nunca se sube a GitHub.
¿Por qué no todo en vivo? La API acepta como máximo 5 días por consulta y 5.000 transacciones cada 10 minutos: 25 años de un país son ~3.000 consultas (~30 min). Los archivos anuales por país de FIRMS son rápidos, pero no se pueden pedir desde otra página web (CORS) y pesan mucho (Brasil: ~150 MB por año), así que se procesan con el script.

## Cómo abrir la página

Haz doble clic en `index.html`. Funciona sin instalar nada, pero necesita internet para el mapa y las librerías.

> Si el navegador bloquea algo al abrirla como archivo, usa un servidor local:
> `python -m http.server 8000` y entra a http://localhost:8000

La página **solo muestra datos reales**. Para un país sin historial guardado, el usuario puede descargarlo en vivo desde la API (panel 3, opción C); queda guardado en su navegador.

## Cómo cargar los datos reales de la NASA

1. Pide tu **MAP_KEY** gratis en https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. Copia `.env.example` como `.env` y pega tu clave:
   ```
   FIRMS_MAP_KEY=tu_clave_de_32_caracteres
   ```
   ⚠️ El archivo `.env` está en `.gitignore`: **nunca lo subas a GitHub**.
3. Ejecuta el script (solo usa Python 3, no hay que instalar nada):

   ```bash
   # Opción A: por país, con la API (automático; ~3.000 consultas para 25 años, 30-60 min)
   # Descarga el rectángulo del país y se queda solo con los focos dentro de su contorno.
   python scripts/descargar_datos.py --pais PER

   # Prueba rápida con un solo año:
   python scripts/descargar_datos.py --pais PER --desde 2025-01-01

   # Opción B (recomendada, más rápida): con los CSV anuales por país.
   # Descárgalos de https://firms.modaps.eosdis.nasa.gov/country/
   # (MODIS y VIIRS S-NPP) y guárdalos en una carpeta "descargas":
   python scripts/descargar_datos.py --csv "descargas/*.csv" --pais PER

   # Opción C: un rectángulo (oeste,sur,este,norte)
   python scripts/descargar_datos.py --bbox -75.9,-11.5,-70.5,-7.3 --clave UCAYALI --nombre "Ucayali"
   ```
4. Recarga la página. Las áreas con datos reales ya no muestran el aviso amarillo.

El script crea `data/focos.js` (lo lee la página) y `data/series/<CLAVE>.csv`, con las columnas MODIS, VIIRS y la serie armonizada de cada día.

> **Nota sobre la API de FIRMS (probado en nov. 2026):** la consulta por país (`/api/country`) ya no responde y la consulta por área acepta como máximo 5 días por llamada. Por eso el script usa `/api/area` en tramos de 5 días.

> **Clave del país:** usa el código ISO de 3 letras (PER, BRA, BOL, COL, AUS…). Es el mismo que usa el mapa, así que la página reconoce el país automáticamente.

## Cómo armonizamos MODIS y VIIRS

| Paso | Qué hacemos | Por qué |
|---|---|---|
| 1. Filtro | Confianza nominal/alta y tipo 0 (vegetación) | Quita falsos positivos, volcanes e industrias |
| 2. Días-celda | Celdas de 0,01° (~1 km) con ≥ 1 foco por día | VIIRS (375 m) ve más puntos que MODIS (1 km) por el mismo fuego |
| 3. Intercalibración | Factor VIIRS/MODIS por mes del año (periodo 2012 → fin de MODIS) | Une 2001-2011 (solo MODIS) con 2012-hoy (VIIRS) en una serie continua |
| 4. Referencia | La serie final está en "equivalente VIIRS S-NPP" | VIIRS seguirá operando cuando MODIS (Terra/Aqua) se apague |
| 5. Anomalías | Puntaje z mensual respecto al periodo de referencia | Señala meses inusuales |
| 6. Temporada | Ventana del 10 % al 90 % del fuego acumulado de un año promedio | Define el periodo crítico |
| 7. Tendencia | Mann-Kendall + pendiente de Sen | Prueba no paramétrica, robusta a años extremos |

## APIs y datos de la NASA usados

- **NASA FIRMS**: focos de calor MODIS (desde 2000) y VIIRS S-NPP (desde 2012). API `area`, `country` y `data_availability`.
- **NASA GIBS**: imágenes del mapa (Blue Marble, color real diario de VIIRS/MODIS y luces nocturnas Black Marble).
- **NASA POWER**: lluvia (PRECTOTCORR) y humedad relativa (RH2M) diarias. No necesita clave.
- **Natural Earth**: límites de países (solo como referencia visual).

## Estructura

```
FireCal/
├── index.html              Página principal
├── css/estilos.css         Estilos (tema oscuro)
├── js/app.js               Mapa, gráficos y lógica de la página
├── js/estadistica.js       Climatología, anomalías, temporada, Mann-Kendall
├── data/focos.js           Series diarias armonizadas (países y regiones)
├── data/densidad.js        Dónde hubo fuego: cuadros de 0,2° por año
├── data/regiones.js        Límites de Huánuco y la Amazonía peruana
├── data/series/*.csv       Serie diaria MODIS / VIIRS / armonizada por área
├── scripts/descargar_datos.py  Descarga + armonización de FIRMS
└── .env.example            Plantilla para tu MAP_KEY
```

## Publicar en GitHub Pages

En el repositorio de GitHub ve a **Settings → Pages → Branch: main / root → Save**. En un minuto la página estará en
`https://<usuario>.github.io/<repositorio>/`.

---
*La NASA no respalda este proyecto. Datos: NASA FIRMS, GIBS y POWER.*
