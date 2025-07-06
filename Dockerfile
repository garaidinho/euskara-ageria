# Usa una imagen oficial de Python 3.11
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . .

# Instala las dependencias
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expón el puerto (opcional si usas 10000 u otro)
EXPOSE 10000

# Comando de inicio
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
