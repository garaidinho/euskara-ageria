# ───────────────────────────────────────────────────────────────────────────────
#  app.py – Euskara Ageria (nombre mostrado = URL, foto por clave normalizada)
# ───────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, url_for
import os, time, re, unicodedata
import psycopg2
from contextlib import closing
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()  # En Render se ignora si ya hay vars


# ─────────────── Utilidades de normalización ──────────────────────────────────
def strip_accents(s: str) -> str:
    """Quita acentos/diacríticos."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def normalize_key(s: str) -> str:
    """
    Clave robusta para foto/DB: minúsculas, sin acentos, sin espacios, sin puntos
    y solo alfanumérico.  'Antton e.' -> 'anttone'
    """
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)  # elimina todo lo no alfanumérico
    return s

def format_display_name(nombre_raw: str) -> str:
    """
    Para mostrar bonito: respeta espacios e iniciales de la URL, capitaliza palabras.
    'antton e.' -> 'Antton e.'
    """
    parts = re.split(r"\s+", nombre_raw.strip())
    return " ".join(p.capitalize() for p in parts if p)


# ─────────────── Config DB (lazy + reintentos) ────────────────────────────────
def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL no está definido en Render > Environment.")
    return url

def get_conn(max_tries: int = 10):
    url = _db_url()
    delay = 0.5
    last = None
    for _ in range(max_tries):
        try:
            conn = psycopg2.connect(
                url,
                sslmode="require",
                keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
            )
            conn.autocommit = False
            return conn
        except Exception as e:
            last = e
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
    raise last or RuntimeError("No se pudo conectar a la base de datos.")

_schema_ready = False
def ensure_schema():
    """Crea tabla si falta (una sola vez por proceso)."""
    global _schema_ready
    if _schema_ready:
        return
    try:
        with closing(get_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS puntos (
                    id      SERIAL PRIMARY KEY,
                    clase   TEXT NOT NULL,
                    nombre  TEXT NOT NULL,
                    puntos  INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (clase, nombre)
                );
            """)
        _schema_ready = True
    except Exception as e:
        print("[WARN] init schema diferido:", repr(e))


# ─────────────── Colores por clase ────────────────────────────────────────────
color_map = {
    "lm1": ("bg-blue-200",   "text-blue-600"),
    "lm2": ("bg-yellow-200", "text-yellow-600"),
    "lm3": ("bg-red-200",    "text-red-600"),
    "lm4": ("bg-green-200",  "text-green-600"),
    "lm5": ("bg-purple-200", "text-purple-600"),
}


# ─────────────── Rutas ────────────────────────────────────────────────────────
@app.route("/")
def index():
    clases = " | ".join(cls.upper() for cls in sorted(color_map))
    return f"<h1>Euskara Ageria</h1><p>Ir a /LM1/amaia (u otro alumno).<br>Clases: {clases}</p>"


@app.route("/<clase>/<nombre>", methods=["GET", "POST"])
def mostrar_alumno(clase: str, nombre: str):
    """
    - 'nombre' se usa tal cual para el TÍTULO (respeta espacios e iniciales).
    - Para cargar la foto y para la clave de DB usamos normalize_key(nombre).
    """
    ensure_schema()

    clase_lower   = clase.lower()
    nombre_raw    = nombre              # tal como llega en la URL (con espacios/inicial)
    key_nombre    = normalize_key(nombre_raw)   # clave robusta para DB/foto

    # ─── POST: +1 / -1 ────────────────────────────────────────────────────────
    if request.method == "POST":
        accion = request.form.get("accion")   # "1" o "-1"
        delta  = 1 if accion == "1" else -1

        with closing(get_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                        (clase_lower, key_nombre))
            row = cur.fetchone()
            puntos = max((row[0] if row else 0) + delta, 0)  # nunca < 0

            if row:
                cur.execute("UPDATE puntos SET puntos=%s WHERE clase=%s AND nombre=%s",
                            (puntos, clase_lower, key_nombre))
            else:
                cur.execute("INSERT INTO puntos (clase, nombre, puntos) VALUES (%s,%s,%s)",
                            (clase_lower, key_nombre, puntos))

        # PRG pattern
        return redirect(url_for("mostrar_alumno", clase=clase_lower, nombre=nombre_raw))

    # ─── GET: mostrar ficha ───────────────────────────────────────────────────
    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                    (clase_lower, key_nombre))
        row = cur.fetchone()
        puntos = row[0] if row else 0

    # Foto en static/photos/<clase>/  (coincidencia por clave normalizada)
    carpeta_foto   = os.path.join("static", "photos", clase_lower)
    nombre_archivo = "default.jpg"
    if os.path.isdir(carpeta_foto):
        for archivo in os.listdir(carpeta_foto):
            stem, ext = os.path.splitext(archivo)
            if not ext:
                continue
            if normalize_key(stem) == key_nombre:
                nombre_archivo = archivo
                break

    # IMPORTANTE: para MOSTRAR usamos SIEMPRE lo que vino en la URL
    display_name = format_display_name(nombre_raw)

    bg_cls, txt_cls = color_map.get(clase_lower, ("bg-gray-100", "text-black"))
    return render_template(
        "alumno.html",
        alumno=(display_name, nombre_archivo, clase_lower, puntos),
        bg_cls=bg_cls,
        txt_cls=txt_cls,
    )


# Healthcheck real (comprueba DB)
@app.route("/ping")
def ping():
    try:
        with closing(get_conn()) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
        return "ok", 200
    except Exception as e:
        return f"db_error: {e}", 500


# ─────────────── Arranque local ───────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
