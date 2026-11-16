#!/usr/bin/env python3
"""Logistic GLM with a smooth non-linear BMI term, compared to the linear-BMI model in glm.py.

BMI enters as a natural cubic regression spline (patsy `cr`, centred so it's identifiable alongside
the intercept) with 3-6 degrees of freedom. A natural spline's basis includes the straight line,
so the linear model is nested in each spline model and likelihood-ratio tests apply. A penalised-spline GAM, with the
smoothing weight chosen by cross-validation, is fitted as a check on how much wiggle the data support.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from statsmodels.gam.api import BSplines, GLMGam

from glm import MAIN, SEED, load

OTHERS = "pregnancies + glucose + blood_pressure + pedigree + age"
MODELS = {"linear": MAIN} | {f"spline df={k}": f"diabetes ~ {OTHERS} + cr(bmi, df={k}, constraints='center')"
                              for k in (3, 4, 5, 6)}
COLORS = {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
          "grid": "#e8e7e3", "spline": "#2a78d6", "linear": "#eb6834"}


def fit(formula, data):
    return smf.glm(formula, data=data, family=sm.families.Binomial()).fit()


def cv(formula, data, folds=10):
    out = []
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=SEED).split(data, data.diabetes):
        p = fit(formula, data.iloc[tr]).predict(data.iloc[te])
        y = data.diabetes.iloc[te]
        out.append((roc_auc_score(y, p), log_loss(y, p)))
    return np.array(out).mean(axis=0)


def gam(data):
    x = data[["bmi"]]
    spline = BSplines(x, df=[10], degree=[3])
    exog = sm.add_constant(data[OTHERS.split(" + ")])
    model = GLMGam(data.diabetes, exog=exog, smoother=spline, family=sm.families.Binomial())
    alpha, _ = model.select_penweight_kfold(k_folds=10)
    res = GLMGam(data.diabetes, exog=exog, smoother=spline, alpha=alpha,
                 family=sm.families.Binomial()).fit()
    return res, alpha


def plot(data, models, path):
    grid = pd.DataFrame({"bmi": np.linspace(data.bmi.quantile(0.005), data.bmi.quantile(0.995), 200)})
    for c in OTHERS.split(" + "):
        grid[c] = data[c].median()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=150)
    fig.patch.set_facecolor(COLORS["surface"]); ax.set_facecolor(COLORS["surface"])
    for name, color in (("linear", COLORS["linear"]), (models["chosen"], COLORS["spline"])):
        sf = models[name].get_prediction(grid).summary_frame()
        if name != "linear":
            ax.fill_between(grid.bmi, sf.mean_ci_lower, sf.mean_ci_upper, color=color, alpha=0.15, lw=0)
        ax.plot(grid.bmi, sf["mean"], color=color, lw=2)
    shown = data.bmi[data.bmi.between(grid.bmi.min(), grid.bmi.max())]
    ax.plot(shown, np.full(len(shown), -0.02), "|", color=COLORS["muted"], ms=6, alpha=0.4)
    ax.set_xlim(grid.bmi.min() - 1, grid.bmi.max() + 1)
    ax.set_ylim(-0.04, 1)
    ax.set_xlabel("BMI", color=COLORS["ink2"]); ax.set_ylabel("Predicted probability of diabetes", color=COLORS["ink2"])
    fig.text(0.02, 0.965, "Diabetes risk by BMI, other predictors at their medians",
             color=COLORS["ink"], fontsize=11.5, va="top")
    fig.text(0.02, 0.915, "Shaded: 95% CI for the spline. Ticks along the bottom: observed BMIs "
             "(middle 99% shown).", color=COLORS["ink2"], fontsize=8.5, va="top")
    ax.grid(axis="y", color=COLORS["grid"], lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(COLORS["muted"])
    ax.tick_params(colors=COLORS["muted"], length=0)
    ax.legend(handles=[plt.Line2D([], [], color=COLORS["spline"], lw=2, label="Natural spline, BMI 3 df"),
                       plt.Line2D([], [], color=COLORS["linear"], lw=2, label="Linear BMI")],
              loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, facecolor=COLORS["surface"])
    grid["p_linear"] = models["linear"].predict(grid)
    grid["p_spline"] = models[models["chosen"]].predict(grid)
    return grid


def main():
    pd.set_option("display.width", 140)
    data = load().dropna(subset=["glucose", "blood_pressure", "bmi"])
    fits = {name: fit(f, data) for name, f in MODELS.items()}
    lin = fits["linear"]
    rows = []
    for name, m in fits.items():
        auc, ll = cv(MODELS[name], data)
        lr = 2 * (m.llf - lin.llf)
        extra = m.df_model - lin.df_model
        rows.append({"model": name, "bmi df": 1 + extra, "AIC": m.aic, "BIC": m.bic_llf,
                     "LR vs linear": lr if extra else np.nan,
                     "p": stats.chi2.sf(lr, extra) if extra else np.nan,
                     "CV AUC": auc, "CV log loss": ll})
    table = pd.DataFrame(rows).set_index("model")
    print(f"Logistic GLM, {len(data)} rows; BMI linear vs natural cubic spline\n")
    print(table.round(4).to_string(), "\n")

    res, alpha = gam(data)
    print(f"Penalised spline GAM (10 B-spline basis functions, smoothing weight {alpha[0]:.3g} by 10-fold CV):")
    print(f"  effective df for BMI ≈ {res.edf[-10:].sum():.2f}   AIC {res.aic:.1f}\n")

    chosen = table["AIC"].drop("linear").idxmin()
    fits["chosen"] = chosen
    grid = plot(data, fits, "bmi_spline.png")
    print(f"Lowest-AIC spline: {chosen}. Predicted probability at median other predictors:")
    at = pd.DataFrame({"bmi": [20, 25, 30, 35, 40, 45, 50]})
    for c in OTHERS.split(" + "):
        at[c] = data[c].median()
    for name, col in (("linear", "p_linear"), (chosen, "p_spline")):
        sf = fits[name].get_prediction(at).summary_frame()
        at[col] = sf["mean"]
        at[col + " 95% CI"] = [f"{lo:.3f}-{hi:.3f}" for lo, hi in zip(sf.mean_ci_lower, sf.mean_ci_upper)]
    at["n with BMI ±2.5"] = [((data.bmi - b).abs() <= 2.5).sum() for b in at.bmi]
    print(at.drop(columns=OTHERS.split(" + ")).set_index("bmi").round(3).to_string())
    print("\nPlot saved to bmi_spline.png")


if __name__ == "__main__":
    main()
