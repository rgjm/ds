#!/usr/bin/env python3
"""Add geo.gccsa / geo.gccsa_share to census_2021.db: the Greater Capital City Statistical Area
(e.g. 1GSYD = Greater Sydney) each region falls in.

SA1-SA4 nest exactly. SAL (suburb), POA (postcode) and LGA (council) don't, so they're assigned to
the GCCSA holding most of their population. Population is estimated per mesh block by splitting each
SA1's 2021 count evenly across its residential mesh blocks. gccsa_share is the fraction of residents
in that GCCSA.

Needs raw/{MB,SAL,POA,LGA}_2021_AUST.xlsx from the ABS ASGS Edition 3 allocation files.
"""
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
DB = HERE / "census_2021.db"


def rows(name):
    ws = openpyxl.load_workbook(HERE / "raw" / f"{name}_2021_AUST.xlsx", read_only=True).worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = next(it)
    for r in it:
        if r[0] is not None:
            yield dict(zip(header, r))


def main():
    con = sqlite3.connect(DB)
    sa1_pop = dict(con.execute("SELECT code, Tot_P_P FROM G01 WHERE geo_type = 'SA1'"))

    mb_sa1, mb_gccsa, mb_cat = {}, {}, {}
    for r in rows("MB"):
        mb = r["MB_CODE_2021"]
        mb_sa1[mb], mb_gccsa[mb], mb_cat[mb] = r["SA1_CODE_2021"], r["GCCSA_CODE_2021"], r["MB_CATEGORY_2021"]
    res_mbs = Counter(mb_sa1[mb] for mb, cat in mb_cat.items() if cat == "Residential")
    all_mbs = Counter(mb_sa1.values())

    def mb_pop(mb):
        sa1 = mb_sa1[mb]
        pop = sa1_pop.get(sa1) or 0
        if res_mbs[sa1]:
            return pop / res_mbs[sa1] if mb_cat[mb] == "Residential" else 0
        return pop / all_mbs[sa1]

    for col, typ in (("gccsa", "TEXT"), ("gccsa_share", "REAL")):
        try:
            con.execute(f"ALTER TABLE geo ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # already added on a previous run

    for geo_type in ("SAL", "POA", "LGA"):
        weights = defaultdict(Counter)
        for r in rows(geo_type):
            code = str(r[f"{geo_type}_CODE_2021"])
            if not code.startswith(geo_type):
                code = geo_type + code
            mb = r["MB_CODE_2021"]
            # tiny epsilon keeps unpopulated regions assignable by mesh-block count
            weights[code][mb_gccsa[mb]] += mb_pop(mb) + 1e-6
        con.executemany(
            "UPDATE geo SET gccsa = ?, gccsa_share = ? WHERE geo_type = ? AND code = ?",
            ((w.most_common(1)[0][0], round(w.most_common(1)[0][1] / sum(w.values()), 3), geo_type, code)
             for code, w in weights.items()))
        print(geo_type, len(weights))

    sa1_gccsa = {mb_sa1[mb]: g for mb, g in mb_gccsa.items()}
    for geo_type, n in (("SA1", 11), ("SA2", 9), ("SA3", 5), ("SA4", 3)):
        lookup = {sa1[:n]: g for sa1, g in sa1_gccsa.items()}
        con.executemany("UPDATE geo SET gccsa = ?, gccsa_share = 1 WHERE geo_type = ? AND code = ?",
                        ((g, geo_type, code) for code, g in lookup.items()))
    con.execute("UPDATE geo SET gccsa = code, gccsa_share = 1 WHERE geo_type = 'GCCSA'")
    con.execute("CREATE INDEX IF NOT EXISTS geo_gccsa ON geo(gccsa, geo_type)")
    con.commit()
    print(con.execute("SELECT geo_type, count(*), count(gccsa) FROM geo GROUP BY 1").fetchall())


if __name__ == "__main__":
    main()
