#!/usr/bin/env python3
"""Look things up in the local ABS 2021 Census database (census_2021.db).

  census.py place  NAME [--type SA2]          find regions by name (or code)
  census.py search WORDS...                   find census columns by description, e.g. "median rent"
  census.py show   PLACE TABLE [--type SAL]   all values for a region from one table (G01, G02, G04A...)
  census.py get    PLACE COLUMN... [--type]   specific columns for a region (short names, any table)
  census.py tables                            list census tables
  census.py sql    "SELECT ..."               run raw SQL

PLACE is a region name or code. Exact name matches win, then suburbs (SAL) over LGAs, postcodes,
SA2s etc. Narrow with --type SA2 and/or --state NSW. Geography types: AUS STE GCCSA SA4 SA3 SA2 SA1 LGA SAL POA CED SED SUA UCL RA SOS SOSR.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent / "census_2021.db"
PREFERENCE = ["SAL", "LGA", "POA", "SA2", "SA3", "SA4", "GCCSA", "STE", "AUS", "UCL", "SUA",
              "CED", "SED", "RA", "SOS", "SOSR", "SA1"]


def con():
    if not DB.exists():
        sys.exit(f"{DB} not found - run build_db.py first")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def print_rows(rows, headers=None):
    rows = [tuple("" if v is None else str(v) for v in r) for r in rows]
    if headers:
        rows.insert(0, tuple(headers))
    if not rows:
        print("(no results)")
        return
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for j, r in enumerate(rows):
        print("  ".join(v.ljust(w) for v, w in zip(r, widths)).rstrip())
        if headers and j == 0:
            print("  ".join("-" * w for w in widths))


def find_places(c, name, geo_type=None, state=None):
    q = "SELECT geo_type, code, name, state, area_sqkm FROM geo WHERE {}"
    extra = []
    if geo_type:
        q += " AND geo_type = ?"; extra.append(geo_type.upper())
    if state:
        q += " AND state = ?"; extra.append(state.upper())
    rows = c.execute(q.format("code = ? COLLATE NOCASE"), [name] + extra).fetchall()
    if rows:
        return rows

    def rank(r):
        n = r["name"].lower()
        base = n.split(" (")[0]  # SAL/LGA names carry a "(NSW)"-style suffix
        match = 0 if name.lower() in (n, base) else 1 if n.startswith(name.lower()) else 2
        pref = PREFERENCE.index(r["geo_type"]) if r["geo_type"] in PREFERENCE else 99
        return match, pref, n
    return sorted(c.execute(q.format("name LIKE ?"), [f"%{name}%"] + extra).fetchall(), key=rank)


def resolve(c, place, geo_type, state=None):
    rows = find_places(c, place, geo_type, state)
    if not rows:
        sys.exit(f"No region matching {place!r}")
    r = rows[0]
    if len(rows) > 1:
        others = ", ".join(f"{x['name']} [{x['geo_type']} {x['code']}]" for x in rows[1:6])
        print(f"# using {r['name']} [{r['geo_type']} {r['code']}]; also matched: {others}"
              f"{' ...' if len(rows) > 6 else ''}\n# (narrow with --type/--state or use the code)\n")
    else:
        print(f"# {r['name']} [{r['geo_type']} {r['code']}]\n")
    return r


def cmd_place(c, a):
    print_rows(find_places(c, " ".join(a.name), a.type, a.state), ["type", "code", "name", "state", "sqkm"])


def cmd_search(c, a):
    text = "(c.long || ' ' || c.short || ' ' || c.description || ' ' || ifnull(t.name, ''))"
    cond = " AND ".join(f"{text} LIKE ?" for _ in a.words)
    rows = c.execute("SELECT c.datapack_file, c.short, c.long, t.name FROM cells c "
                     "LEFT JOIN table_info t ON t.table_id = rtrim(c.datapack_file, 'ABCDEFGH') "
                     f"WHERE {cond} ORDER BY c.rowid LIMIT ?",
                     [f"%{w}%" for w in a.words] + [a.limit]).fetchall()
    print_rows(rows, ["table", "column", "description", "table name"])


def cmd_show(c, a):
    r = resolve(c, a.place, a.type, a.state)
    table = a.table.upper()
    info = c.execute("SELECT name, population FROM table_info WHERE table_id = ?",
                     (table.rstrip("ABCDEFGH"),)).fetchone()
    if info:
        print(f"# {table}: {info['name']}" + (f" ({info['population']})" if info["population"] else ""))
    row = c.execute(f'SELECT * FROM "{table}" WHERE geo_type = ? AND code = ?',
                    (r["geo_type"], r["code"])).fetchone()
    if not row:
        sys.exit(f"No {table} data for that region")
    desc = dict(c.execute("SELECT short, long FROM cells WHERE datapack_file = ?", (table,)).fetchall())
    keys = [k for k in row.keys()[2:] if not a.filter or a.filter.lower() in (k + desc.get(k, "")).lower()]
    print_rows([(k, row[k], desc.get(k, "")) for k in keys], ["column", "value", "description"])


def cmd_get(c, a):
    r = resolve(c, a.place, a.type, a.state)
    out = []
    for col in a.columns:
        tables = [t[0] for t in c.execute(
            "SELECT DISTINCT datapack_file FROM cells WHERE short = ? COLLATE NOCASE", (col,))]
        if not tables:
            out.append((col, "?", "(unknown column - try `search`)"))
            continue
        t = tables[0]
        row = c.execute(f'SELECT "{col}" AS v FROM "{t}" WHERE geo_type = ? AND code = ?',
                        (r["geo_type"], r["code"])).fetchone()
        long = c.execute("SELECT long FROM cells WHERE short = ? COLLATE NOCASE AND datapack_file = ?",
                         (col, t)).fetchone()[0]
        out.append((col, row["v"] if row else "", f"{t}: {long}"))
    print_rows(out, ["column", "value", "table: description"])


def cmd_tables(c, a):
    print_rows(c.execute("SELECT table_id, name, population FROM table_info ORDER BY table_id"),
               ["table", "name", "population"])


def cmd_sql(c, a):
    cur = c.execute(" ".join(a.query))
    print_rows(cur.fetchall(), [d[0] for d in cur.description] if cur.description else None)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("place"); s.add_argument("name", nargs="+"); s.add_argument("--type"); s.add_argument("--state")
    s.set_defaults(f=cmd_place)
    s = sub.add_parser("search"); s.add_argument("words", nargs="+"); s.add_argument("--limit", type=int, default=60)
    s.set_defaults(f=cmd_search)
    s = sub.add_parser("show"); s.add_argument("place"); s.add_argument("table"); s.add_argument("--type"); s.add_argument("--state")
    s.add_argument("--filter", help="only columns whose name/description contains this"); s.set_defaults(f=cmd_show)
    s = sub.add_parser("get"); s.add_argument("place"); s.add_argument("columns", nargs="+"); s.add_argument("--type"); s.add_argument("--state")
    s.set_defaults(f=cmd_get)
    sub.add_parser("tables").set_defaults(f=cmd_tables)
    s = sub.add_parser("sql"); s.add_argument("query", nargs="+"); s.set_defaults(f=cmd_sql)
    a = p.parse_args()
    a.f(con(), a)


if __name__ == "__main__":
    main()
