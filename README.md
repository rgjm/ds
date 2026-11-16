# ds

Small data-science projects, one per directory. Only scripts and docs are committed. Datasets,
virtualenvs, databases, fitted models and outputs stay local (see `.gitignore`), so each project's
README has to say how to rebuild them.

| project | what it is |
|---|---|
| [`abs_census/`](abs_census/) | ABS 2021 Census DataPack loaded into SQLite, plus a lookup CLI |
| [`pima_glm/`](pima_glm/) | Logistic regression / GLMs / XGBoost on the Pima Indians diabetes data |

## Conventions for every project directory

Each new directory must be reproducible from a fresh clone. It needs:

1. **Its own virtualenv** at `<project>/.venv` (Python 3.10), not shared between projects.
2. **A `requirements.txt`** that pins the packages the scripts import, with exact versions
   (`pkg==x.y.z`). Pin direct dependencies only, not the full `pip freeze`. Update it whenever
   you install something new.
3. **A `README.md`** with a **Setup** section covering:
   - creating the venv:
     ```sh
     cd <project>
     python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
     ```
   - **where to get the data**: direct download URLs (or the landing page if there's no stable
     link), the exact filenames and paths the scripts expect, and the licence;
   - the commands to run, in order, to rebuild any generated files (databases, models, results).
4. **No data in git.** The root `.gitignore` ignores everything except `*.py`, `*.R`, `*.sh`,
   `README.md`, `CLAUDE.md` and `requirements.txt`. If a project needs another small file type
   committed (e.g. a config), add a `!` exception there deliberately.

Before committing a new project, check `git status` shows only scripts and docs.
