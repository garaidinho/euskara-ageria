# ───────────────────────────────────────────────────────────────────────────────
#  app.py  – Euskara Ageria  (versión completa, lista para sustituir tu archivo)
# ───────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, url_for
import os
import psycopg2
from dotenv import load_dotenv

# ─────────────── Config básica ────────────────────────────────────────────────
app = Flask(__name__)
load_dotenv()                               # En Render se ignora si ya hay vars

# ─────────────── Conexión a PostgreSQL ────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# Render (y Heroku) dan el DSN como postgres:// → psycopg2 quiere postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# sslmode=require ya viene en la URL interna de Render, lo repetimos por si acaso
conn = psycopg2.connect(DATABASE_URL, sslmode="require")

# Crear tabla si no existe
with conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS puntos (
            id      SERIAL PRIMARY KEY,
            clase   TEXT NOT NULL,
            nombre  TEXT NOT NULL,
            puntos  INTEGER NOT NULL DEFAULT 0,
            UNIQUE (clase, nombre)
        );
    """)

# Colores por clase (en minúsculas)
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
    """Página de bienvenida sencilla. Pásate a /LM1/amaia, por ejemplo."""
    clases = " | ".join(cls.upper() for cls in sorted(color_map))
    return f"<h1>Euskara Ageria</h1><p>Ir a /LM1/amaia (u otro alumno).<br>Clases: {clases}</p>"

@app.route("/<clase>/<nombre>", methods=["GET", "POST"])
def mostrar_alumno(clase: str, nombre: str):
    clase_lower  = clase.lower()     # Normalizamos a minúsculas
    nombre_lower = nombre.lower()

    # ─── POST: +1 / -1 ────────────────────────────────────────────────────────
    if request.method == "POST":
        accion = request.form.get("accion")          # "1" o "-1"
        delta  = 1 if accion == "1" else -1

        with conn, conn.cursor() as cur:
            cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                        (clase_lower, nombre_lower))
            row     = cur.fetchone()
            puntos  = max((row[0] if row else 0) + delta, 0)   # nunca < 0

            if row:
                cur.execute("UPDATE puntos SET puntos=%s WHERE clase=%s AND nombre=%s",
                            (puntos, clase_lower, nombre_lower))
            else:
                cur.execute("INSERT INTO puntos (clase, nombre, puntos) VALUES (%s,%s,%s)",
                            (clase_lower, nombre_lower, puntos))

        # Evitar reenvío de formulario (PRG pattern)
        return redirect(url_for("mostrar_alumno",
                                clase=clase_lower, nombre=nombre_lower))

    # ─── GET: mostrar ficha ───────────────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s",
                    (clase_lower, nombre_lower))
        row     = cur.fetchone()
        puntos  = row[0] if row else 0

    # Foto (cualquier extensión) en static/photos/<clase_lower>/
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

# Endpoint mínimo para UptimeRobot / BetterUptime
@app.route("/ping")
def ping():
    return "pong", 200

# ─────────────── Arranque local ───────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True)
