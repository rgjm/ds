# ABS 2021 Census, local copy

Source: ABS 2021 Census General Community Profile (GCP) DataPack, all geographies, short headers
(`raw/2021_GCP_all_for_AUS_short-header.zip`, CC BY 4.0). 2021 is the latest released census.
Results from the 2026 census are not due until mid-2027.

`census_2021.db` is a SQLite database:

| table | contents |
|---|---|
| `geo` | every region: `geo_type`, `code`, `name`, `state`, `area_sqkm`, `gccsa` (capital-city area it falls in, e.g. `1GSYD` = Greater Sydney, `2GMEL` = Greater Melbourne; set for SA1–4, SAL, POA, LGA) and `gccsa_share` (fraction of residents inside it) |
| `table_info` | census table names, e.g. G02 = Selected Medians and Averages |
| `cells` | column dictionary: `short` column name → `long` name, by `datapack_file` |
| `G01` … `G62` | data, one table per DataPack file (G04A, G04B… are separate); all geography levels stacked, keyed by `(geo_type, code)` |

Geography types: AUS, STE (state), GCCSA, SA4, SA3, SA2, SA1, LGA (council), SAL (suburb/locality),
POA (postcode), CED/SED (federal/state electorate), SUA, UCL, RA, SOS, SOSR.

## Lookups

```sh
./census.py place Newtown                      # find regions
./census.py search median rent                 # find columns
./census.py show Newtown G02 --state NSW       # a whole table for one place
./census.py show Parramatta G04B --type LGA --filter Tot
./census.py get 2000 Tot_P_P Median_rent_weekly --type POA
./census.py tables
./census.py sql "SELECT g.name, d.Median_rent_weekly FROM G02 d JOIN geo g USING (geo_type, code)
                 WHERE geo_type='SA2' AND g.state='VIC' ORDER BY 2 DESC LIMIT 10"
```

The database also opens in any SQLite tool (DB Browser for SQLite, DBeaver, DuckDB, or pandas).

## Setup / rebuilding

The database and raw files are not in git. To rebuild from scratch:

```sh
cd abs_census
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Data (CC BY 4.0, Australian Bureau of Statistics), ~700 MB total, into raw/
mkdir -p raw && cd raw
curl -LO https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_all_for_AUS_short-header.zip
ASGS=https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/allocation-files
for f in MB SAL POA LGA; do curl -LO $ASGS/${f}_2021_AUST.xlsx; done
cd ..

.venv/bin/python build_db.py        # builds census_2021.db, ~30 min
.venv/bin/python add_hierarchy.py   # adds gccsa / gccsa_share to geo
```

Landing pages if the direct links move: [Census DataPacks](https://www.abs.gov.au/census/find-census-data/datapacks)
(2021, General Community Profile, all geographies, short header) and
[ASGS Edition 3 allocation files](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/allocation-files).
