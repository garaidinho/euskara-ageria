import os
import sqlite3

DB_PATH = "alumnos.db"
FOTOS_DIR = "static/photos"

# Eliminar la base de datos si ya existía (opcional, solo si reinicias todo)
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

# Conectar y crear tabla con campo de clase
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS alumnos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        foto TEXT NOT NULL,
        clase TEXT NOT NULL,
        puntos INTEGER DEFAULT 0
    )
''')

# Leer subcarpetas (lm1, lm2, ...)
for carpeta in os.listdir(FOTOS_DIR):
    carpeta_path = os.path.join(FOTOS_DIR, carpeta)
    if os.path.isdir(carpeta_path):
        for filename in os.listdir(carpeta_path):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                nombre = os.path.splitext(filename)[0]
                ruta_foto = f"{carpeta}/{filename}"
                cursor.execute("INSERT INTO alumnos (nombre, foto, clase, puntos) VALUES (?, ?, ?, ?)",
                               (nombre, ruta_foto, carpeta, 0))
                print(f"Añadido: {nombre} ({carpeta})")

conn.commit()
conn.close()
print("✅ Importación finalizada correctamente.")
