from flask import Flask, render_template, request, redirect, url_for
import os
import psycopg2
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Carga variables locales (.env) -en Render ya vienen en el panel Environment-
load_dotenv()

# ─────────────── Conexión a PostgreSQL ───────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# Render (y Heroku) dan el DSN como postgres:// → psycopg2 quiere postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Abre conexión global (sslmode=require ya viene incluido en el DSN de Render)
conn = psycopg2.connect(DATABASE_URL, sslmode="require")

# ─────────────── Tabla y colores por clase ───────────────────────────────────
with conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS puntos (
            id SERIAL PRIMARY KEY,
            clase  TEXT NOT NULL,
            nombre TEXT NOT NULL,
            puntos INTEGER NOT NULL DEFAULT 0,
            UNIQUE (clase, nombre)
        );
    """)

color_map = {
    "lm1": ("bg-blue-200",   "text-blue-600"),
    "lm2": ("bg-yellow-200", "text-yellow-600"),
    "lm3": ("bg-red-200",    "text-red-600"),
    "lm4": ("bg-green-200",  "text-green-600"),
    "lm5": ("bg-purple-200", "text-purple-600"),
}

# ─────────────── Rutas web ────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", clases=sorted(color_map.keys()))

@app.route("/<clase>/<nombre>", methods=["GET", "POST"])
def mostrar_alumno(clase: str, nombre: str):
    clase_lower  = clase.lower()
    nombre_lower = nombre.lower()

    if request.method == "POST":
        delta = int(request.form.get("delta", 0))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                        (clase_lower, nombre_lower))
            row = cur.fetchone()
            puntos = row[0] + delta if row else delta

            if row:
                cur.execute("UPDATE puntos SET puntos=%s WHERE clase=%s AND nombre=%s",
                            (puntos, clase_lower, nombre_lower))
            else:
                cur.execute("INSERT INTO puntos (clase, nombre, puntos) VALUES (%s,%s,%s)",
                            (clase_lower, nombre_lower, puntos))
        # evitar doble envío de formulario
        return redirect(url_for("mostrar_alumno",
                                clase=clase_lower, nombre=nombre_lower))

    # --- GET ----------------------------------------------------------------
    with conn.cursor() as cur:
        cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                    (clase_lower, nombre_lower))
        row = cur.fetchone()
        puntos = row[0] if row else 0

    # Foto → busca cualquier extensión dentro de static/photos/<clase>/
    carpeta_foto   = os.path.join("static", "photos", clase_lower)
    nombre_archivo = "default.jpg"
    if os.path.isdir(carpeta_foto):
        for archivo in os.listdir(carpeta_foto):
            if os.path.splitext(archivo)[0].lower() == nombre_lower:
                nombre_archivo = archivo
                break

    bg_cls, txt_cls = color_map.get(clase_lower, ("bg-gray-100", "text-black"))
    return render_template(
        "alumno.html",
        alumno=(nombre.capitalize(), nombre_archivo, clase_lower, puntos),
        bg_cls=bg_cls,
        txt_cls=txt_cls,
    )

# ─────────────── Ruta ping para mantener vivo el servicio ─────────────────────
@app.route("/ping")
def ping():
    return "pong", 200

# ─────────────── Ejecución local (opcional) ──────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
