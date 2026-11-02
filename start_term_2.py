"""2026-27: epe berrira igarotzeko segurtasunezko tresna.

Irakurri soilik:
    python start_term_2.py

Aplikatu (behin bakarrik, DB kopia egin ondoren):
    python start_term_2.py --apply

Ez du medailak, puntu_historia edo asteko_absentzia ezabatzen.
Ikasle bakoitzaren aurreko puntuak epe_itxierak taulan gordetzen ditu.
"""
import argparse
from contextlib import closing
import psycopg2

from app import GELAK, START_POINTS, _db_url, normalize_key

TARGET_TERM = 2
PREVIOUS_TERM = 1


def official_keys():
    seen = set()
    for group in GELAK.values():
        for maila, izenak in group["taldeak"]:
            for izena in izenak:
                seen.add((maila.lower(), normalize_key(izena)))
    return sorted(seen)


def main():
    parser = argparse.ArgumentParser(description="Euskara Ageria: 2. epea")
    parser.add_argument("--apply", action="store_true", help="Egiazko aldaketa transakzionala")
    args = parser.parse_args()

    people = official_keys()
    with closing(psycopg2.connect(_db_url(), sslmode="require")) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.ikasle_egoera')")
            if cur.fetchone()[0] is None:
                raise SystemExit("ERROREA: ikasle_egoera taula ez da existitzen.")

            # Single transaction; never operate while teacher points are being edited.
            if args.apply:
                cur.execute("SELECT pg_advisory_xact_lock(2026, 2)")
                cur.execute("LOCK TABLE ikasle_egoera IN SHARE ROW EXCLUSIVE MODE")

            cur.execute("SELECT clase, nombre, puntuak, epea FROM ikasle_egoera")
            all_records = {
                (c, k): (int(p), int(t))
                for c, k, p, t in cur.fetchall()
            }
            missing = [k for k in people if k not in all_records]
            to_reset = [k for k in people if k in all_records and all_records[k][1] == PREVIOUS_TERM]
            already_new = [k for k in people if k in all_records and all_records[k][1] == TARGET_TERM]
            unexpected = [(k, all_records[k][1]) for k in people if k in all_records and all_records[k][1] not in (PREVIOUS_TERM, TARGET_TERM)]
            if unexpected:
                raise SystemExit(f"ERROREA: espero gabeko epeak: {unexpected[:5]}")

            print(
                f"Ikasleak: {len(people)} | 1. epean: {len(to_reset)} | "
                f"2. epean: {len(already_new)} | falta: {len(missing)}"
            )
            if not args.apply:
                print("PROBA SOILIK. Ez da daturik aldatu. Erabili --apply gauzatzeko.")
                conn.rollback()
                return

            cur.execute("""
                CREATE TABLE IF NOT EXISTS epe_itxierak (
                    clase TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    epea INTEGER NOT NULL,
                    azken_puntuak INTEGER NOT NULL,
                    itxita_noiz TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (clase, nombre, epea)
                )
            """)

            # Snapshot all existing official students in term 1 before the reset.
            for c, k in to_reset:
                old_points, _ = all_records[(c, k)]
                cur.execute("""
                    INSERT INTO epe_itxierak(clase,nombre,epea,azken_puntuak)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (clase,nombre,epea) DO NOTHING
                """, (c, k, PREVIOUS_TERM, old_points))
                cur.execute("""
                    UPDATE ikasle_egoera
                    SET puntuak=%s,epea=%s,updated_at=NOW()
                    WHERE clase=%s AND nombre=%s AND epea=%s
                """, (START_POINTS, TARGET_TERM, c, k, PREVIOUS_TERM))
                if cur.rowcount != 1:
                    raise RuntimeError(f"Ikaslea ez da eguneratu: {c}/{k}")

            for c, k in missing:
                cur.execute("""
                    INSERT INTO ikasle_egoera(clase,nombre,puntuak,epea)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (clase,nombre) DO NOTHING
                """, (c, k, START_POINTS, TARGET_TERM))

        conn.commit()
    print(f"EGINDA: {len(to_reset)} reset; {len(missing)} ikasle berri. Historikoa eta medailak mantenduta.")
    print("GARRANTZITSUA: Render > Environment atalean CURRENT_TERM=2 jarri, berriak ere 2. epean has daitezen.")


if __name__ == "__main__":
    main()
