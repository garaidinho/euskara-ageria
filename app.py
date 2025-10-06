# ───────────────────────────────────────────────────────────────────────────────
#  app.py – Euskara Ageria (versión robusta para Render)  [display name fiel al fichero]
# ───────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, url_for
import os, time
import psycopg2
from contextlib import closing
from dotenv import load_dotenv

# ─────────────── Config básica ────────────────────────────────────────────────
app = Flask(__name__)
load_dotenv()  # En Render se ignora si ya hay vars

# ─────────────── Utilidades DB (lazy + reintentos) ────────────────────────────
def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    # Render/Heroku dan postgres:// y psycopg2 quiere postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL no está definido en Render > Environment.")
    return url

def get_conn(max_tries: int = 10):
    """Abre conexión con reintentos exponenciales. Se cierra en quien la usa."""
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
            conn.autocommit = False  # usaremos 'with conn:' para commit/rollback
            return conn
        except Exception as e:
            last = e
            time.sleep(delay)
            delay = min(delay * 2, 5.0)
    # último intento: si falla, que explote y lo veamos en logs
    raise last or RuntimeError("No se pudo conectar a la base de datos.")

_schema_ready = False
def ensure_schema():
    """Crea tabla si falta. Se ejecuta una vez por proceso."""
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
        # No tumbar la app por esto: volveremos a intentar en la próxima petición
        print("[WARN] init schema diferido:", repr(e))

# Colores por clase (en minúsculas)
color_map = {
    "lm1": ("bg-blue-200",   "text-blue-600"),
    "lm2": ("bg-yellow-200", "text-yellow-600"),
    "lm3": ("bg-red-200",    "text-red-600"),
    "lm4": ("bg-green-200",  "text-green-600"),
    "lm5": ("bg-purple-200", "text-purple-600"),
}

# ─────────────── Helpers de fotos/nombres ─────────────────────────────────────
def buscar_foto_y_display(clase_lower: str, nombre_param: str):
    """
    Devuelve (nombre_archivo, display_name, db_key)
    - nombre_archivo: fichero encontrado (con extensión), p. ej. "Antton e..jpg"
    - display_name: base exacta del fichero (tal cual), p. ej. "Antton e."
    - db_key: clave normalizada para BD (minúsculas), p. ej. "antton e."
    Si no hay foto, usa "default.jpg" y display del parámetro sin forzar.
    """
    carpeta = os.path.join("static", "photos", clase_lower)
    if not os.path.isdir(carpeta):
        return "default.jpg", nombre_param, nombre_param.lower()

    # normalizamos la búsqueda por base en minúsculas
    objetivo = os.path.splitext(nombre_param)[0].lower()

    elegido = None
    display = None
    db_key  = objetivo

    for archivo in os.listdir(carpeta):
        base, ext = os.path.splitext(archivo)
        if not ext.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        if base.lower() == objetivo:
            elegido = archivo           # nombre de archivo exacto (con ext)
            display = base              # base exacta para mostrar (respeta espacios/puntos/mayus)
            db_key  = base.lower()      # clave estable para BD
            break

    if elegido is None:
        # No encontrada: devolvemos default y mostramos el nombre del parámetro tal cual
        return "default.jpg", nombre_param, objetivo

    return elegido, display, db_key

# ─────────────── Rutas ────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Página de bienvenida sencilla. Pásate a /LM1/amaia, por ejemplo."""
    clases = " | ".join(cls.upper() for cls in sorted(color_map))
    return f"<h1>Euskara Ageria</h1><p>Ir a /LM1/amaia (u otro alumno).<br>Clases: {clases}</p>"

@app.route("/<clase>/<nombre>", methods=["GET", "POST"])
def mostrar_alumno(clase: str, nombre: str):
    ensure_schema()

    clase_lower = clase.lower()

    # Resolvemos foto y nombres basados en el fichero REAL
    nombre_archivo, display_name, nombre_db = buscar_foto_y_display(clase_lower, nombre)

    # ─── POST: +1 / -1 ────────────────────────────────────────────────────────
    if request.method == "POST":
        accion = request.form.get("accion")   # "1" o "-1"
        delta  = 1 if accion == "1" else -1

        with closing(get_conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                        (clase_lower, nombre_db))
            row = cur.fetchone()
            puntos = max((row[0] if row else 0) + delta, 0)  # nunca < 0

            if row:
                cur.execute("UPDATE puntos SET puntos=%s WHERE clase=%s AND nombre=%s",
                            (puntos, clase_lower, nombre_db))
            else:
                cur.execute("INSERT INTO puntos (clase, nombre, puntos) VALUES (%s,%s,%s)",
                            (clase_lower, nombre_db, puntos))

        # Evitar reenvío de formulario (PRG pattern) y redirigir con el DISPLAY exacto
        return redirect(url_for("mostrar_alumno",
                                clase=clase_lower, nombre=display_name))

    # ─── GET: mostrar ficha ───────────────────────────────────────────────────
    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                    (clase_lower, nombre_db))
        row = cur.fetchone()
        puntos = row[0] if row else 0

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
    # En local: flask dev server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
