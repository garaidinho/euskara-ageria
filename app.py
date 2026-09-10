# ───────────────────────────────────────────────────────────────────────────────
# Euskara Ageria 2026-2027
# - Ikaslearen profila: irakurketa bakarrik (puntuak + medailak)
# - Irakasleen plataforma: gelaka, puntuak aldatu, absentzia markatu, historikoa
# ───────────────────────────────────────────────────────────────────────────────
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort
import os, time, re, unicodedata
from functools import lru_cache
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


def alphabetical_sort_key(nombre_raw: str):
    # Izenak azentuak kontuan hartu gabe alfabetikoki ordenatzeko.
    return strip_accents(nombre_raw).casefold()



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


def is_official_student(clase: str, nombre_raw: str) -> bool:
    # GELAK zerrenda ofizialean dagoen ikaslea bakarrik onartu.
    wanted = (clase.lower(), normalize_key(nombre_raw))
    return any(
        (c.lower(), normalize_key(n)) == wanted
        for c, n in all_students()
    )


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
                ALTER TABLE medailak
                ADD COLUMN IF NOT EXISTS animazioa_ikusia BOOLEAN NOT NULL DEFAULT FALSE;
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


PHOTO_OVERRIDES = {
    ("lm2", "zoi"): "Paco.jpg",
    ("lm2", "paco"): "Zoi.jpg",
}


@lru_cache(maxsize=256)
def photo_for(clase: str, nombre_raw: str) -> str:
    clase_lower = clase.lower()
    key = normalize_key(nombre_raw)

    override = PHOTO_OVERRIDES.get((clase_lower, key))
    if override:
        override_path = os.path.join("static", "photos", clase_lower, override)
        if os.path.isfile(override_path):
            return override

    carpeta = os.path.join("static", "photos", clase_lower)
    if os.path.isdir(carpeta):
        for archivo in os.listdir(carpeta):
            stem, ext = os.path.splitext(archivo)
            if ext and normalize_key(stem) == key:
                return archivo
    return "default.jpg"



@lru_cache(maxsize=256)
def teacher_photo_path(clase: str, nombre_raw: str) -> str:
    # Irakasleen interfazearentzat thumbnail arina; faltan bada jatorrizkoa.
    clase_lower = clase.lower()
    original = photo_for(clase_lower, nombre_raw)
    stem = os.path.splitext(original)[0]
    thumb_name = normalize_key(stem) + ".jpg"
    thumb_rel = os.path.join("photos_thumb", clase_lower, thumb_name)
    thumb_abs = os.path.join("static", thumb_rel)
    if os.path.isfile(thumb_abs):
        return thumb_rel
    return os.path.join("photos", clase_lower, original)


def maybe_award_medal(cur, clase: str, key: str, epea: int, puntuak: int):
    """Medaila lortzen den unean gordetzen du; behin lortuta ez da galtzen."""
    threshold = MEDAL_THRESHOLDS.get(epea)
    if threshold is None or puntuak < threshold:
        return False
    cur.execute(
        """
        INSERT INTO medailak (clase, nombre, epea, lortua, animazioa_ikusia)
        VALUES (%s, %s, %s, TRUE, FALSE)
        ON CONFLICT (clase, nombre, epea) DO NOTHING
        RETURNING epea;
        """,
        (clase, key, epea),
    )
    return cur.fetchone() is not None


def consume_pending_medal_animation(clase: str, key: str, epea: int):
    """Ikaslearen profil publikoak medaila berria behin bakarrik ospatzeko."""
    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT epea
            FROM medailak
            WHERE clase=%s AND nombre=%s AND epea=%s
              AND lortua=TRUE AND animazioa_ikusia=FALSE
            FOR UPDATE
            """,
            (clase, key, epea),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            """
            UPDATE medailak
            SET animazioa_ikusia=TRUE
            WHERE clase=%s AND nombre=%s AND epea=%s
            """,
            (clase, key, epea),
        )
        return row[0]


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
        maybe_award_medal(cur, clase_lower, key, epea, puntuak)
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

    # Ez utzi kanpoko URL/probe batek DBn "ikasle" faltsurik sortzen.
    # Adib.: /.well-known/assetlinks.json
    if not is_official_student(clase_lower, nombre):
        abort(404)

    key, puntuak, epea, medailak = student_state(clase_lower, nombre)
    new_medal = consume_pending_medal_animation(clase_lower, key, epea)
    display_name = format_display_name(nombre)
    nombre_archivo = photo_for(clase_lower, nombre)
    bg_cls, txt_cls = color_map.get(clase_lower, ("bg-gray-100", "text-black"))
    threshold = MEDAL_THRESHOLDS[epea]
    progress_pct = max(0, min(round((puntuak / threshold) * 100), 100))
    remaining = max(threshold - puntuak, 0)

    return render_template(
        "alumno.html",
        alumno=(display_name, nombre_archivo, clase_lower, puntuak),
        epea=epea,
        medailak=medailak,
        new_medal=new_medal,
        medal_thresholds=MEDAL_THRESHOLDS,
        progress_pct=progress_pct,
        remaining=remaining,
        bg_cls=bg_cls,
        txt_cls=txt_cls,
    )


# ───────────────────────────── IRAKASLE PLATAFORMA ────────────────────────────
def _ajax_request() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def ensure_students_batch(cur, rows):
    """Gela bateko ikasleak SQL bakarrean sortzen ditu falta badira."""
    if not rows:
        return
    placeholders = []
    params = []
    for clase, key in rows:
        placeholders.append("(%s,%s,%s,%s)")
        params.extend([clase, key, START_POINTS, CURRENT_TERM])
    cur.execute(
        """
        INSERT INTO ikasle_egoera (clase, nombre, puntuak, epea)
        VALUES """ + ",".join(placeholders) + """
        ON CONFLICT (clase, nombre) DO NOTHING
        """,
        params,
    )


def weekly_stats_for_student(cur, clase: str, key: str, astea: date):
    amaiera = astea + timedelta(days=7)
    cur.execute(
        """
        SELECT
            COALESCE(SUM(delta), 0)::int,
            COALESCE(SUM(CASE WHEN delta > 0 THEN delta ELSE 0 END), 0)::int,
            COALESCE(SUM(CASE WHEN delta < 0 THEN -delta ELSE 0 END), 0)::int
        FROM puntu_historia
        WHERE clase=%s AND nombre=%s
          AND sortua >= %s AND sortua < %s
        """,
        (clase, key, astea, amaiera),
    )
    row = cur.fetchone() or (0, 0, 0)
    return int(row[0]), int(row[1]), int(row[2])


@app.route("/irakasle")
def irakasle_index():
    # Hasierako orriak ez du DB kontsultarik egiten: berehala irekitzen da.
    gelak_view = []
    for key, g in GELAK.items():
        kop = sum(len(nombres) for _, nombres in g["taldeak"])
        gelak_view.append({"key": key, "izena": g["izena"], "kop": kop})

    mailak_view = []
    for zenbakia in range(1, 6):
        maila = f"LM{zenbakia}"
        kop = sum(
            len(nombres)
            for g in GELAK.values()
            for clase, nombres in g["taldeak"]
            if clase.upper() == maila
        )
        mailak_view.append({"key": maila, "izena": maila, "kop": kop})

    return render_template(
        "irakasle.html",
        gelak=gelak_view,
        mailak=mailak_view,
    )

def _render_irakasle_taldeak(izenburua: str, taldeak):
    # Gela edo maila baten ikasleak modu berean eta kontsulta gutxirekin kargatu.
    ensure_schema()
    astea = current_week_start()
    astea_amaiera = astea + timedelta(days=6)

    taldeak_ordenatuta = [
        (clase.upper(), sorted(nombres, key=alphabetical_sort_key))
        for clase, nombres in taldeak
    ]

    wanted = []
    klaseak = []
    for clase, nombres in taldeak_ordenatuta:
        c = clase.lower()
        if c not in klaseak:
            klaseak.append(c)
        for nombre in nombres:
            wanted.append((c, normalize_key(nombre)))

    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        ensure_students_batch(cur, wanted)

        # V24: dashboard datuak SQL bakarrean irakurri.
        # Lehen 3 SELECT bereizi ziren; orain egoera + astea + absentzia batera datoz.
        pair_placeholders = ",".join(["(%s,%s)"] * len(wanted))
        pair_params = []
        for c, key in wanted:
            pair_params.extend([c, key])

        cur.execute(
            f"""
            SELECT
                e.clase,
                e.nombre,
                e.puntuak,
                COALESCE(w.net, 0)::int AS net,
                COALESCE(w.plus, 0)::int AS plus,
                COALESCE(w.minus, 0)::int AS minus,
                (a.nombre IS NOT NULL) AS absentzia
            FROM ikasle_egoera e
            LEFT JOIN (
                SELECT
                    clase,
                    nombre,
                    COALESCE(SUM(delta), 0)::int AS net,
                    COALESCE(SUM(CASE WHEN delta > 0 THEN delta ELSE 0 END), 0)::int AS plus,
                    COALESCE(SUM(CASE WHEN delta < 0 THEN -delta ELSE 0 END), 0)::int AS minus
                FROM puntu_historia
                WHERE sortua >= %s AND sortua < %s
                GROUP BY clase, nombre
            ) w ON w.clase=e.clase AND w.nombre=e.nombre
            LEFT JOIN asteko_absentzia a
              ON a.clase=e.clase AND a.nombre=e.nombre AND a.astea=%s
            WHERE (e.clase, e.nombre) IN ({pair_placeholders})
            """,
            [astea, astea + timedelta(days=7), astea, *pair_params],
        )
        row_map = {
            (c, n): (int(p), int(net), int(plus), int(minus), bool(absentzia))
            for c, n, p, net, plus, minus, absentzia in cur.fetchall()
        }

    taldeak_view = []
    aste_plus_total = 0
    aste_minus_total = 0
    absentzia_kop = 0
    ikasle_kop = 0

    for clase, nombres in taldeak_ordenatuta:
        c = clase.lower()
        ikasleak = []
        for nombre in nombres:
            key = normalize_key(nombre)
            puntuak, net, plus, minus, absentzia = row_map.get(
                (c, key), (START_POINTS, 0, 0, 0, False)
            )

            aste_plus_total += plus
            aste_minus_total += minus
            absentzia_kop += 1 if absentzia else 0
            ikasle_kop += 1

            ikasleak.append({
                "clase": c,
                "clase_label": clase.upper(),
                "nombre": nombre,
                "display": format_display_name(nombre),
                "foto": photo_for(clase, nombre),
                "foto_path": teacher_photo_path(clase, nombre),
                "puntuak": puntuak,
                "absentzia": absentzia,
                "asteko_net": net,
                "asteko_plus": plus,
                "asteko_minus": minus,
            })

        taldeak_view.append((clase.upper(), ikasleak))

    return render_template(
        "gela.html",
        gela_izena=izenburua,
        taldeak=taldeak_view,
        astea=astea,
        astea_amaiera=astea_amaiera,
        ikasle_kop=ikasle_kop,
        aste_plus_total=aste_plus_total,
        aste_minus_total=aste_minus_total,
        absentzia_kop=absentzia_kop,
    )


@app.route("/irakasle/gela/<gela_key>")
def irakasle_gela(gela_key: str):
    gela = GELAK.get(gela_key)
    if not gela:
        return "Gela ez da existitzen", 404
    return _render_irakasle_taldeak(gela["izena"], gela["taldeak"])


@app.route("/irakasle/maila/<maila>")
def irakasle_maila(maila: str):
    maila = maila.upper()
    if maila not in {"LM1", "LM2", "LM3", "LM4", "LM5"}:
        return "Maila ez da existitzen", 404

    nombres = []
    seen = set()
    for gela in GELAK.values():
        for clase, taldeko_izenak in gela["taldeak"]:
            if clase.upper() != maila:
                continue
            for nombre in taldeko_izenak:
                key = normalize_key(nombre)
                if key not in seen:
                    seen.add(key)
                    nombres.append(nombre)

    return _render_irakasle_taldeak(
        f"{maila} · maila osoa",
        [(maila, nombres)],
    )

@app.post("/irakasle/puntuak/<clase>/<nombre>")
def irakasle_aldatu_puntuak(clase: str, nombre: str):
    ensure_schema()
    try:
        delta = int(request.form.get("delta", "0"))
    except ValueError:
        delta = 0
    delta = max(min(delta, 20), -20)

    clase_lower = clase.lower()
    astea = current_week_start()
    berria = START_POINTS
    medaila_berria = False
    historia_id = None
    aste_net = aste_plus = aste_minus = 0

    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        key = ensure_student(cur, clase_lower, nombre)
        cur.execute(
            "SELECT puntuak, epea FROM ikasle_egoera WHERE clase=%s AND nombre=%s FOR UPDATE",
            (clase_lower, key),
        )
        puntuak, epea = cur.fetchone()
        berria = puntuak

        if delta != 0:
            berria = max(puntuak + delta, 0)
            benetako_delta = berria - puntuak
            if benetako_delta:
                cur.execute(
                    "UPDATE ikasle_egoera SET puntuak=%s, updated_at=NOW() WHERE clase=%s AND nombre=%s",
                    (berria, clase_lower, key),
                )
                cur.execute(
                    """
                    INSERT INTO puntu_historia (clase, nombre, epea, delta, mota)
                    VALUES (%s,%s,%s,%s,'eskuz')
                    RETURNING id
                    """,
                    (clase_lower, key, epea, benetako_delta),
                )
                historia_id = int(cur.fetchone()[0])
                medaila_berria = maybe_award_medal(cur, clase_lower, key, epea, berria)

        aste_net, aste_plus, aste_minus = weekly_stats_for_student(cur, clase_lower, key, astea)

    if _ajax_request():
        return {
            "ok": True,
            "puntuak": int(berria),
            "asteko_net": aste_net,
            "asteko_plus": aste_plus,
            "asteko_minus": aste_minus,
            "medaila_berria": bool(medaila_berria),
            "historia_id": historia_id,
        }

    next_url = request.form.get("next")
    return redirect(next_url or url_for("irakasle_index"))


@app.post("/irakasle/desegin/<int:historia_id>")
def irakasle_desegin(historia_id: int):
    """Azken puntu-aldaketa eskuzkoa benetan desegin, historikoa eta asteko estatistikak zikindu gabe."""
    ensure_schema()
    astea = current_week_start()

    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT clase, nombre, epea, delta, sortua
            FROM puntu_historia
            WHERE id=%s
              AND mota='eskuz'
              AND sortua >= NOW() - INTERVAL '15 minutes'
            FOR UPDATE
            """,
            (historia_id,),
        )
        row = cur.fetchone()
        if not row:
            if _ajax_request():
                return {"ok": False, "error": "ez_da_aurkitu"}, 404
            return redirect(url_for("irakasle_index"))

        clase_lower, key, epea, delta, sortua = row

        # Segurtasuna: desegin daitekeen aldaketa ikasle horren azken puntu-mugimendua izan behar da.
        cur.execute(
            """
            SELECT id
            FROM puntu_historia
            WHERE clase=%s AND nombre=%s
            ORDER BY sortua DESC, id DESC
            LIMIT 1
            """,
            (clase_lower, key),
        )
        latest = cur.fetchone()
        if not latest or int(latest[0]) != int(historia_id):
            if _ajax_request():
                return {"ok": False, "error": "ez_da_azkena"}, 409
            return redirect(url_for("irakasle_index"))

        cur.execute(
            "SELECT puntuak FROM ikasle_egoera WHERE clase=%s AND nombre=%s FOR UPDATE",
            (clase_lower, key),
        )
        state = cur.fetchone()
        if not state:
            if _ajax_request():
                return {"ok": False, "error": "ikaslea_ez_da_aurkitu"}, 404
            return redirect(url_for("irakasle_index"))

        berria = max(int(state[0]) - int(delta), 0)
        cur.execute(
            "UPDATE ikasle_egoera SET puntuak=%s, updated_at=NOW() WHERE clase=%s AND nombre=%s",
            (berria, clase_lower, key),
        )
        cur.execute("DELETE FROM puntu_historia WHERE id=%s", (historia_id,))

        # Klik oker honek medaila sortu bazuen, desegiteak medaila ere leheneratzen du.
        threshold = MEDAL_THRESHOLDS.get(int(epea))
        if int(delta) > 0 and threshold is not None and berria < threshold:
            cur.execute(
                """
                DELETE FROM medailak
                WHERE clase=%s AND nombre=%s AND epea=%s
                  AND lortua_noiz >= %s
                """,
                (clase_lower, key, epea, sortua - timedelta(seconds=2)),
            )

        aste_net, aste_plus, aste_minus = weekly_stats_for_student(cur, clase_lower, key, astea)

    if _ajax_request():
        return {
            "ok": True,
            "puntuak": int(berria),
            "asteko_net": aste_net,
            "asteko_plus": aste_plus,
            "asteko_minus": aste_minus,
        }
    return redirect(url_for("irakasle_index"))


@app.post("/irakasle/absentzia/<clase>/<nombre>")
def irakasle_absentzia(clase: str, nombre: str):
    ensure_schema()
    clase_lower = clase.lower()
    astea = current_week_start()
    active = False

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
            active = False
        else:
            cur.execute(
                "INSERT INTO asteko_absentzia (clase, nombre, astea) VALUES (%s,%s,%s)",
                (clase_lower, key, astea),
            )
            active = True

    if _ajax_request():
        return {"ok": True, "absentzia": active}

    next_url = request.form.get("next")
    return redirect(next_url or url_for("irakasle_index"))


@app.route("/irakasle/ikaslea/<clase>/<nombre>")
def irakasle_ikaslea(clase: str, nombre: str):
    # V24: xehetasun orri osoa DB konexio bakarrean.
    ensure_schema()
    clase_lower = clase.lower()
    astea = current_week_start()
    astea_amaiera = astea + timedelta(days=6)

    with closing(get_conn()) as conn, conn, conn.cursor() as cur:
        key = ensure_student(cur, clase_lower, nombre)
        cur.execute(
            "SELECT puntuak, epea FROM ikasle_egoera WHERE clase=%s AND nombre=%s",
            (clase_lower, key),
        )
        puntuak, epea = cur.fetchone()
        maybe_award_medal(cur, clase_lower, key, epea, puntuak)

        cur.execute(
            "SELECT epea FROM medailak WHERE clase=%s AND nombre=%s AND lortua=TRUE ORDER BY epea",
            (clase_lower, key),
        )
        medailak = {row[0] for row in cur.fetchall()}

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
        aste_net, aste_plus, aste_minus = weekly_stats_for_student(cur, clase_lower, key, astea)

    return render_template(
        "irakasle_ikaslea.html",
        nombre=nombre,
        display_name=format_display_name(nombre),
        clase=clase_lower,
        foto=photo_for(clase_lower, nombre),
        foto_path=teacher_photo_path(clase_lower, nombre),
        puntuak=puntuak,
        epea=epea,
        medailak=medailak,
        historia=historia,
        absentzia=absentzia,
        asteko_net=aste_net,
        asteko_plus=aste_plus,
        asteko_minus=aste_minus,
        astea=astea,
        astea_amaiera=astea_amaiera,
    )



@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(
        os.path.join(app.root_path, "static"),
        "service-worker.js",
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


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
