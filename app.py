from flask import Flask, render_template, request, redirect, url_for
import os
import psycopg2
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

# 🔗 Conexión con PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL, sslmode='require')

# ✅ Colores por clase
color_map = {
    "LM1": ("bg-blue-200", "text-blue-600"),
    "LM2": ("bg-yellow-200", "text-yellow-600"),
    "LM3": ("bg-red-200", "text-red-600"),
    "LM4": ("bg-green-200", "text-green-600"),
    "LM5": ("bg-purple-200", "text-purple-600"),
}

# 🔧 Crear tabla si no existe
with conn:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS puntos (
                id SERIAL PRIMARY KEY,
                clase TEXT NOT NULL,
                nombre TEXT NOT NULL,
                puntos INTEGER NOT NULL
            )
        """)

@app.route('/')
def home():
    return "✅ Web activa. Accede a una URL como /alumno/LM1/Nahia para ver un alumno."

@app.route('/alumno/<clase>/<nombre>', methods=['GET', 'POST'])
def mostrar_alumno(clase, nombre):
    # 🔡 Normaliza nombres
    clase = clase.upper()
    nombre_lower = nombre.lower()

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT puntos FROM puntos WHERE clase=%s AND nombre=%s", (clase, nombre_lower))
            row = cur.fetchone()
            puntos = row[0] if row else 0

            if request.method == 'POST':
                accion = request.form.get('accion')
                puntos += 1 if accion == '1' else -1

                if row:
                    cur.execute("UPDATE puntos SET puntos=%s WHERE clase=%s AND nombre=%s", (puntos, clase, nombre_lower))
                else:
                    cur.execute("INSERT INTO puntos (clase, nombre, puntos) VALUES (%s, %s, %s)", (clase, nombre_lower, puntos))

                return redirect(url_for('mostrar_alumno', clase=clase, nombre=nombre))

    # 📸 Buscar imagen sin importar extensión
    carpeta_foto = os.path.join("static", "photos", clase)
    nombre_archivo = None
    if os.path.isdir(carpeta_foto):
        for archivo in os.listdir(carpeta_foto):
            if os.path.splitext(archivo)[0].lower() == nombre_lower:
                nombre_archivo = archivo
                break

    if not nombre_archivo:
        nombre_archivo = "default.jpg"

    # 🎨 Colores por clase
    bg_cls, txt_cls = color_map.get(clase.upper(), ("bg-gray-100", "text-black"))

    return render_template("alumno.html",
                           alumno=(nombre.capitalize(), nombre_archivo, clase, puntos),
                           bg_cls=bg_cls,
                           txt_cls=txt_cls)

if __name__ == '__main__':
    app.run(debug=True)
