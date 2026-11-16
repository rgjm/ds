#!/usr/bin/env python3
"""Fit the same predictors as glm.py under three GLM forms and compare them:

  binomial / logit     log-odds linear in predictors     -> odds ratios
  gaussian / identity  probability linear in predictors  -> risk differences ("linear probability model")
  poisson  / log       log-probability linear            -> risk ratios ("modified Poisson")

The gaussian and poisson variance functions are wrong for a 0/1 outcome, so their coefficients are
reported with robust (HC0 sandwich) standard errors as well as the model-based ones.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from glm import MAIN, SEED, UNITS, load

FAMILIES = {
    "binomial-logit": sm.families.Binomial(),
    "gaussian-identity": sm.families.Gaussian(),
    "poisson-log": sm.families.Poisson(),
}
EFFECT = {"binomial-logit": "odds ratio", "gaussian-identity": "risk diff", "poisson-log": "risk ratio"}


def fit(family, data, robust=False):
    return smf.glm(MAIN, data=data, family=FAMILIES[family]).fit(cov_type="HC0" if robust else "nonrobust")


def effects(family, model, robust):
    rows = {}
    for v in model.params.index.drop("Intercept"):
        u = UNITS[v]
        b, lo, hi = model.params[v] * u, model.conf_int().loc[v, 0] * u, model.conf_int().loc[v, 1] * u
        if family != "gaussian-identity":
            b, lo, hi = np.exp(b), np.exp(lo), np.exp(hi)
        rows[(v, u)] = {"effect": b, "ci_low": lo, "ci_high": hi, "p": model.pvalues[v],
                        "p_robust": robust.pvalues[v]}
    return pd.DataFrame(rows).T


def cv(family, data, folds=10):
    out = []
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=SEED).split(data, data.diabetes):
        p = fit(family, data.iloc[tr]).predict(data.iloc[te])
        y = data.diabetes.iloc[te]
        out.append((roc_auc_score(y, p), brier_score_loss(y, p.clip(0, 1))))
    return np.array(out).mean(axis=0)


def main():
    pd.set_option("display.width", 140)
    data = load().dropna(subset=["glucose", "blood_pressure", "bmi"])
    summary, preds = [], {}
    for fam in FAMILIES:
        m, mr = fit(fam, data), fit(fam, data, robust=True)
        p = m.predict(data)
        preds[fam] = p
        auc, brier = cv(fam, data)
        summary.append({"model": fam, "AIC": m.aic, "deviance": m.deviance, "CV AUC": auc,
                        "CV Brier": brier, "min pred": p.min(), "max pred": p.max(),
                        "preds <0": (p < 0).sum(), "preds >1": (p > 1).sum()})
        print(f"== {fam}: {EFFECT[fam]} per unit shown (model-based 95% CI; p and robust p)")
        print(effects(fam, m, mr).round(3).to_string(), "\n")

    print("== Comparison (all fitted on the same 724 rows)")
    print(pd.DataFrame(summary).set_index("model").round(3).to_string(), "\n")
    print("AIC: binomial and poisson are both likelihoods for the 0/1 counts, so comparable; the gaussian")
    print("AIC is from a normal density and isn't on the same scale.\n")
    print("== Correlation of fitted probabilities")
    print(pd.DataFrame(preds).corr().round(3).to_string())

    p = pd.DataFrame(preds)
    top = p["binomial-logit"].idxmax()
    print(f"\nRow {top} (highest logit prediction): " +
          ", ".join(f"{k} {v:.3f}" for k, v in p.loc[top].items()))


if __name__ == "__main__":
    main()
