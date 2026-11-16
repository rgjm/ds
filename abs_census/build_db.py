#!/usr/bin/env python3
"""Build census_2021.db (SQLite) from the ABS 2021 Census GCP DataPack (all geographies, short header).

Tables created:
  geo          one row per region: geo_type, code, name, state, area_sqkm
  table_info   one row per census table (G01, G02, ...): name and population counted
  cells        column dictionary: short column name -> long name / description, per DataPack file
  G01 ... G62  one table per DataPack file (G04A, G04B, ... kept separate), all geography levels
               stacked together, keyed by (geo_type, code)
"""
import csv
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
ZIP = HERE / "raw" / "2021_GCP_all_for_AUS_short-header.zip"
DB = HERE / "census_2021.db"

STATES = {"1": "NSW", "2": "VIC", "3": "QLD", "4": "SA", "5": "WA",
          "6": "TAS", "7": "NT", "8": "ACT", "9": "OT"}
POA_STATE = {"NSW": "NSW", "Vic.": "VIC", "Qld": "QLD", "SA": "SA", "WA": "WA",
             "Tas.": "TAS", "NT": "NT", "ACT": "ACT", "OT": "OT"}


def num(v):
    if v == "" or v is None:
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def state_of(geo_type, code, name):
    if geo_type == "AUS":
        return None
    if geo_type == "POA":
        suffix = str(name).rsplit(",", 1)[-1].strip()
        return POA_STATE.get(suffix, suffix)
    m = re.match(r"[A-Za-z]*(\d)", code)
    return STATES.get(m.group(1)) if m else None


def sheet_rows(ws, header_first_cell):
    """Yield rows after the header row whose first cell equals header_first_cell."""
    rows = ws.iter_rows(values_only=True)
    for row in rows:
        if row and row[0] == header_first_cell:
            break
    for row in rows:
        if row and row[0] is not None:
            yield row


def load_metadata(con, z):
    with z.open("Metadata/Metadata_2021_GCP_DataPack_R1_R2.xlsx") as f:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True)
    con.execute("CREATE TABLE table_info (table_id TEXT PRIMARY KEY, name TEXT, population TEXT)")
    con.executemany("INSERT INTO table_info VALUES (?,?,?)",
                    ((r[0], r[1], (r[2] or "").strip() or None)
                     for r in sheet_rows(wb["Table Number, Name, Population"], "Table Number")))
    con.execute("""CREATE TABLE cells (sequential TEXT, short TEXT, long TEXT,
                   datapack_file TEXT, profile_table TEXT, description TEXT)""")
    con.executemany("INSERT INTO cells VALUES (?,?,?,?,?,?)",
                    (r[:6] for r in sheet_rows(wb["Cell Descriptors Information"], "Sequential")))
    con.execute("CREATE INDEX cells_file ON cells(datapack_file, short)")

    with z.open("Metadata/2021Census_geog_desc_1st_2nd_3rd_release.xlsx") as f:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True)
    con.execute("""CREATE TABLE geo (geo_type TEXT, code TEXT, name TEXT, state TEXT, area_sqkm REAL,
                   PRIMARY KEY (geo_type, code))""")
    for ws in wb.worksheets:
        for geo_type, code, _asgs, name, area in sheet_rows(ws, "ASGS_Structure"):
            code = str(code)
            con.execute("INSERT OR IGNORE INTO geo VALUES (?,?,?,?,?)",
                        (geo_type, code, str(name), state_of(geo_type, code, name), area))
    con.execute("CREATE INDEX geo_name ON geo(name COLLATE NOCASE)")


def load_data(con, z):
    files = {}
    for n in z.namelist():
        m = re.search(r"/2021Census_(G\w+?)_AUST?_(\w+)\.csv$", n)
        if m:
            files.setdefault(m.group(1), []).append((m.group(2), n))
    for i, (table, members) in enumerate(sorted(files.items()), 1):
        cols = None
        for geo_type, member in sorted(members):
            with z.open(member) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
                header = [h.strip() for h in next(reader)]
                if cols is None:
                    cols = header[1:]
                    coldefs = ", ".join(f'"{c}" NUMERIC' for c in cols)
                    con.execute(f'CREATE TABLE "{table}" (geo_type TEXT, code TEXT, {coldefs}, '
                                f'PRIMARY KEY (geo_type, code))')
                    insert = (f'INSERT INTO "{table}" VALUES '
                              f'({",".join("?" * (len(cols) + 2))})')
                elif header[1:] != cols:
                    sys.exit(f"Column mismatch in {member}")
                con.executemany(insert, ([geo_type, row[0].strip()] + [num(v.strip()) for v in row[1:]]
                                         for row in reader if row))
        con.commit()
        print(f"[{i}/{len(files)}] {table}: {len(cols)} columns", flush=True)


def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    with zipfile.ZipFile(ZIP) as z:
        load_metadata(con, z)
        con.commit()
        load_data(con, z)
    con.execute("ANALYZE")
    con.commit()
    con.close()
    print(f"Done: {DB} ({DB.stat().st_size / 1e9:.2f} GB)")


if __name__ == "__main__":
    main()
