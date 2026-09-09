# ───────────────────────────────────────────────────────────────────────────────
# Euskara Ageria 2026-2027
# - Ikaslearen profila: irakurketa bakarrik (puntuak + medailak)
# - Irakasleen plataforma: gelaka, puntuak aldatu, absentzia markatu, historikoa
# ───────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, url_for
import os, time, re, unicodedata
from datetime import date, timedelta
from contextlib import closing

import psycopg2
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

CURRENT_TERM = int(os.getenv("CURRENT_TERM", "1"))
START_POINTS = 10
MEDAL_THRESHOLDS = {1: 15, 2: 15, 3: 15, 4: 15, 5: 17}
SPECIAL_THRESHOLDS = {1: 18, 2: 18, 3: 17, 4: 17, 5: 21}

# Gelak: izenak URL/foto-fitxategiekin bat etortzeko moduan gordeta.
GELAK = {
    "garai": {
        "izena": "Garaien gela",
        "taldeak": [
            ("LM2", ["Yzïa", "Paloma", "Oihan", "Lucas", "Odei", "Elize", "Léa", "Augustin", "Luken"]),
            ("LM3", ["Tehani", "Lola", "Deba", "Léon", "Maika", "Garance", "Aritz", "Nahia", "Jules", "Antton M.", "Jean", "Gaspar"]),
        ],
    },
    "benat": {
        "izena": "Beñaten gela",
        "taldeak": [
            ("LM1", ["Luma", "Mathys", "Amaia", "Nahima", "Naël", "Robinson", "Agustina", "Elerina", "Noé", "Gaël", "Ayumi"]),
            ("LM5", ["Noha", "Arthur", "Leo B", "Gaspard", "Leo F", "Milo", "Sasha"]),
        ],
    },
    "florianne": {
        "izena": "Floriannen gela",
        "taldeak": [
            ("LM2", ["Nina", "Zoi", "Paco", "Andoni", "Jeanne", "Eneko", "Emile", "Lola", "Nino"]),
            ("LM5", ["Gabi", "Ilho", "Andoni C", "Izei", "Andoni L", "Andoni M", "Alaia", "Gilen"]),
        ],
    },
    "oihana": {
        "izena": "Oihanaren gela",
        "taldeak": [
            ("LM3", ["Amaia", "Maia", "Antton E.", "Aguxtin", "Mila", "Amets", "Haize"]),
            ("LM4", ["Nolan", "Louis", "Kaori", "Zulai", "Ilyam", "Elaia", "Lou", "Kemen", "Jon", "Telma", "Eba", "Cerise", "Jone", "Amane", "Elea", "Oihan", "Gaspard", "Unai", "Mattin"]),
        ],
    },
}

color_map = {
    "lm1": ("bg-blue-200", "text-blue-600"),
    "lm2": ("bg-yellow-200", "text-yellow-600"),
    "lm3": ("bg-red-200", "text-red-600"),
    "lm4": ("bg-green-200", "text-green-600"),
    "lm5": ("bg-purple-200", "text-purple-600"),
}


def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def normalize_key(s: str) -> str:
    s = strip_accents(s).lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def format_display_name(nombre_raw: str) -> str:
    parts = re.split(r"\s+", nombre_raw.strip())
    return " ".join(p.capitalize() for p in parts if p)


def current_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def all_students():
    seen = set()
    out = []
    for gela in GELAK.values():
        for clase, nombres in gela["taldeak"]:
            for nombre in nombres:
                key = (clase.lower(), normalize_key(nombre))
                if key in seen:
                    continue
                seen.add(key)
                out.append((clase.lower(), nombre))
    return out


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
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
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
    global _schema_ready
    if _schema_ready:
        return
    try:
        with closing(get_conn()) as conn, conn, conn.cursor() as cur:
            # Taula berria erabiltzen dugu 2026-27ko sistema aurreko datuekin ez nahasteko.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ikasle_egoera (
                    clase       TEXT NOT NULL,
                    nombre      TEXT NOT NULL,
                    puntuak     INTEGER NOT NULL DEFAULT 10,
                    epea        INTEGER NOT NULL DEFAULT 1,
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (clase, nombre)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS puntu_historia (
                    id          SERIAL PRIMARY KEY,
                    clase       TEXT NOT NULL,
                    nombre      TEXT NOT NULL,
                    epea        INTEGER NOT NULL,
                    delta       INTEGER NOT NULL,
                    mota        TEXT NOT NULL DEFAULT 'eskuz',
                    sortua      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_historia_ikaslea
                ON puntu_historia (clase, nombre, sortua DESC);
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS medailak (
                    clase       TEXT NOT NULL,
                    nombre      TEXT NOT NULL,
                    epea        INTEGER NOT NULL,
                    lortua      BOOLEAN NOT NULL DEFAULT TRUE,
                    lortua_noiz TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (clase, nombre, epea)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS asteko_absentzia (
                    clase       TEXT NOT NULL,
                    nombre      TEXT NOT NULL,
                    astea       DATE NOT NULL,
                    markatua    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (clase, nombre, astea)
                );
            """)
        _schema_ready = True
    except Exception as e:
        print("[WARN] init schema diferido:", repr(e))


def ensure_student(cur, clase: str, nombre_raw: str):
    clase = clase.lower()
    key = normalize_key(nombre_raw)
    cur.execute(
        """
        INSERT INTO ikasle_egoera (clase, nombre, puntuak, epea)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (clase, nombre) DO NOTHING;
        """,
        (clase, key, START_POINTS, CURRENT_TERM),
    )
    return key


def initialize_all_students():
    ensure_schema()
    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        for clase, nombre in all_students():
            ensure_student(cur, clase, nombre)


def photo_for(clase: str, nombre_raw: str) -> str:
    clase_lower = clase.lower()
    key = normalize_key(nombre_raw)
    carpeta = os.path.join("static", "photos", clase_lower)
    if os.path.isdir(carpeta):
        for archivo in os.listdir(carpeta):
            stem, ext = os.path.splitext(archivo)
            if ext and normalize_key(stem) == key:
                return archivo
    return "default.jpg"


def student_state(clase: str, nombre_raw: str):
    ensure_schema()
    clase_lower = clase.lower()
    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        key = ensure_student(cur, clase_lower, nombre_raw)
        cur.execute(
            "SELECT puntuak, epea FROM ikasle_egoera WHERE clase=%s AND nombre=%s",
            (clase_lower, key),
        )
        puntuak, epea = cur.fetchone()
        cur.execute(
            "SELECT epea FROM medailak WHERE clase=%s AND nombre=%s AND lortua=TRUE ORDER BY epea",
            (clase_lower, key),
        )
        medailak = {row[0] for row in cur.fetchall()}
    return key, puntuak, epea, medailak


@app.route("/")
def index():
    return "<h1>Euskara Ageria</h1><p>Ikaslearen txartela hurbildu bere profila irekitzeko.</p>"


# ───────────────────────────── IKASLEAREN PROFILA ─────────────────────────────
@app.route("/<clase>/<nombre>", methods=["GET"])
def mostrar_alumno(clase: str, nombre: str):
    clase_lower = clase.lower()
    _, puntuak, epea, medailak = student_state(clase_lower, nombre)
    display_name = format_display_name(nombre)
    nombre_archivo = photo_for(clase_lower, nombre)
    bg_cls, txt_cls = color_map.get(clase_lower, ("bg-gray-100", "text-black"))

    return render_template(
        "alumno.html",
        alumno=(display_name, nombre_archivo, clase_lower, puntuak),
        epea=epea,
        medailak=medailak,
        medal_thresholds=MEDAL_THRESHOLDS,
        bg_cls=bg_cls,
        txt_cls=txt_cls,
    )


# ───────────────────────────── IRAKASLE PLATAFORMA ────────────────────────────
@app.route("/irakasle")
def irakasle_index():
    initialize_all_students()
    gelak_view = []
    for key, g in GELAK.items():
        kop = sum(len(nombres) for _, nombres in g["taldeak"])
        gelak_view.append({"key": key, "izena": g["izena"], "kop": kop})
    return render_template("irakasle.html", gelak=gelak_view)


@app.route("/irakasle/gela/<gela_key>")
def irakasle_gela(gela_key: str):
    ensure_schema()
    gela = GELAK.get(gela_key)
    if not gela:
        return "Gela ez da existitzen", 404

    initialize_all_students()
    astea = current_week_start()
    taldeak_view = []

    with closing(get_conn()) as conn, conn.cursor() as cur:
        for clase, nombres in gela["taldeak"]:
            ikasleak = []
            for nombre in nombres:
                key = normalize_key(nombre)
                cur.execute(
                    "SELECT puntuak FROM ikasle_egoera WHERE clase=%s AND nombre=%s",
                    (clase.lower(), key),
                )
                row = cur.fetchone()
                puntuak = row[0] if row else START_POINTS
                cur.execute(
                    "SELECT 1 FROM asteko_absentzia WHERE clase=%s AND nombre=%s AND astea=%s",
                    (clase.lower(), key, astea),
                )
                absentzia = cur.fetchone() is not None
                ikasleak.append({
                    "clase": clase.lower(),
                    "clase_label": clase.upper(),
                    "nombre": nombre,
                    "display": format_display_name(nombre),
                    "foto": photo_for(clase, nombre),
                    "puntuak": puntuak,
                    "absentzia": absentzia,
                })
            taldeak_view.append((clase.upper(), ikasleak))

    return render_template(
        "gela.html",
        gela_key=gela_key,
        gela_izena=gela["izena"],
        taldeak=taldeak_view,
    )


@app.post("/irakasle/puntuak/<clase>/<nombre>")
def irakasle_aldatu_puntuak(clase: str, nombre: str):
    ensure_schema()
    try:
        delta = int(request.form.get("delta", "0"))
    except ValueError:
        delta = 0
    delta = max(min(delta, 20), -20)  # akats handiak saihesteko segurtasun-muga teknikoa

    if delta != 0:
        clase_lower = clase.lower()
        with closing(get_conn()) as conn, conn, conn.cursor() as cur:
            key = ensure_student(cur, clase_lower, nombre)
            cur.execute(
                "SELECT puntuak, epea FROM ikasle_egoera WHERE clase=%s AND nombre=%s FOR UPDATE",
                (clase_lower, key),
            )
            puntuak, epea = cur.fetchone()
            berria = max(puntuak + delta, 0)
            benetako_delta = berria - puntuak
            if benetako_delta:
                cur.execute(
                    "UPDATE ikasle_egoera SET puntuak=%s, updated_at=NOW() WHERE clase=%s AND nombre=%s",
                    (berria, clase_lower, key),
                )
                cur.execute(
                    "INSERT INTO puntu_historia (clase, nombre, epea, delta, mota) VALUES (%s,%s,%s,%s,'eskuz')",
                    (clase_lower, key, epea, benetako_delta),
                )

    next_url = request.form.get("next")
    return redirect(next_url or url_for("irakasle_index"))


@app.post("/irakasle/absentzia/<clase>/<nombre>")
def irakasle_absentzia(clase: str, nombre: str):
    ensure_schema()
    clase_lower = clase.lower()
    astea = current_week_start()
    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        key = ensure_student(cur, clase_lower, nombre)
        cur.execute(
            "SELECT 1 FROM asteko_absentzia WHERE clase=%s AND nombre=%s AND astea=%s",
            (clase_lower, key, astea),
        )
        if cur.fetchone():
            cur.execute(
                "DELETE FROM asteko_absentzia WHERE clase=%s AND nombre=%s AND astea=%s",
                (clase_lower, key, astea),
            )
        else:
            cur.execute(
                "INSERT INTO asteko_absentzia (clase, nombre, astea) VALUES (%s,%s,%s)",
                (clase_lower, key, astea),
            )

    next_url = request.form.get("next")
    return redirect(next_url or url_for("irakasle_index"))


@app.route("/irakasle/ikaslea/<clase>/<nombre>")
def irakasle_ikaslea(clase: str, nombre: str):
    ensure_schema()
    clase_lower = clase.lower()
    key, puntuak, epea, medailak = student_state(clase_lower, nombre)
    astea = current_week_start()

    with closing(get_conn()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT delta, mota, sortua
            FROM puntu_historia
            WHERE clase=%s AND nombre=%s
            ORDER BY sortua DESC
            LIMIT 50
            """,
            (clase_lower, key),
        )
        historia = cur.fetchall()
        cur.execute(
            "SELECT 1 FROM asteko_absentzia WHERE clase=%s AND nombre=%s AND astea=%s",
            (clase_lower, key, astea),
        )
        absentzia = cur.fetchone() is not None

    return render_template(
        "irakasle_ikaslea.html",
        nombre=nombre,
        display_name=format_display_name(nombre),
        clase=clase_lower,
        foto=photo_for(clase_lower, nombre),
        puntuak=puntuak,
        epea=epea,
        medailak=medailak,
        historia=historia,
        absentzia=absentzia,
    )


@app.route("/ping")
def ping():
    try:
        ensure_schema()
        with closing(get_conn()) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
        return "ok", 200
    except Exception as e:
        return f"db_error: {e}", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
