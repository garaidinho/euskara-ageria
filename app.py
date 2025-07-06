from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# ✅ Colores por clase (usamos claves en mayúsculas para consistencia visual)
color_map = {
    "LM1": ("bg-blue-200", "text-blue-600"),
    "LM2": ("bg-yellow-200", "text-yellow-600"),
    "LM3": ("bg-red-200", "text-red-600"),
    "LM4": ("bg-green-200", "text-green-600"),
    "LM5": ("bg-purple-200", "text-purple-600"),
}

# 💾 Memoria temporal de puntos
puntos_dict = {}

@app.route('/')
def home():
    return "✅ Web activa. Accede a una URL como /alumno/LM1/Nahia para ver un alumno."

@app.route('/alumno/<clase>/<nombre>', methods=['GET', 'POST'])
def mostrar_alumno(clase, nombre):
    clase = clase.lower()
    nombre = nombre.lower()
    key = f"{clase}_{nombre}"
    puntos = puntos_dict.get(key, 0)

    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == '1':
            puntos += 1
        elif accion == '-1':
            puntos -= 1
        puntos_dict[key] = puntos
        return redirect(url_for('mostrar_alumno', clase=clase, nombre=nombre))

    # 📸 Buscar imagen correspondiente sin importar extensión
    carpeta_foto = os.path.join("static", "photos", clase)
    nombre_archivo = None

    if os.path.isdir(carpeta_foto):
        archivos = os.listdir(carpeta_foto)
        for archivo in archivos:
            if os.path.splitext(archivo)[0].lower() == nombre:
                nombre_archivo = archivo
                break

    if not nombre_archivo:
        nombre_archivo = "default.jpg"  # Imagen por defecto si no se encuentra

    # 🎨 Colores según clase
    bg_cls, txt_cls = color_map.get(clase.upper(), ("bg-gray-100", "text-black"))

    return render_template("alumno.html",
                           alumno=(nombre.capitalize(), nombre_archivo, clase, puntos),
                           bg_cls=bg_cls,
                           txt_cls=txt_cls)

if __name__ == '__main__':
    app.run(debug=True)
