#!/usr/bin/env python3
"""XGBoost classifier on the Pima data, compared with the logistic GLMs on identical CV folds.

Main comparison: same 724 rows and six predictors as glm.py. Hyperparameters are tuned by an inner
5-fold grid search inside each outer fold (nested CV), so the outer scores are honest. A variant
uses all 768 rows and all eight predictors, leaving missing values as NaN for XGBoost to route.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import xgboost as xgb
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold

from bmi_splines import MODELS, OTHERS
from glm import MAIN, SEED, load

FEATURES = ["pregnancies", "glucose", "blood_pressure", "bmi", "pedigree", "age"]
ALL_FEATURES = FEATURES + ["skin_thickness", "insulin"]
GRID = {"max_depth": [2, 3, 4], "learning_rate": [0.03, 0.1], "n_estimators": [100, 300, 600],
        "min_child_weight": [1, 5]}
SPLINE = MODELS["spline df=3"]


def tuned_xgb(X, y):
    base = xgb.XGBClassifier(subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
                             random_state=SEED, n_jobs=1)
    search = GridSearchCV(base, GRID, scoring="neg_log_loss", n_jobs=-1,
                          cv=StratifiedKFold(5, shuffle=True, random_state=SEED))
    return search.fit(X, y)


def glm_predict(formula, train, test):
    return smf.glm(formula, data=train, family=sm.families.Binomial()).fit().predict(test)


def scores(y, p):
    return {"CV AUC": roc_auc_score(y, p), "CV log loss": log_loss(y, p), "CV Brier": brier_score_loss(y, p)}


def main():
    pd.set_option("display.width", 160)
    df = load()
    data = df.dropna(subset=["glucose", "blood_pressure", "bmi"])
    y = data.diabetes
    folds = list(StratifiedKFold(10, shuffle=True, random_state=SEED).split(data, y))

    oof = pd.DataFrame(index=data.index, columns=["logit", "logit_spline", "xgb"], dtype=float)
    chosen = []
    for i, (tr, te) in enumerate(folds, 1):
        train, test = data.iloc[tr], data.iloc[te]
        oof.iloc[te, 0] = glm_predict(MAIN, train, test).values
        oof.iloc[te, 1] = glm_predict(SPLINE, train, test).values
        search = tuned_xgb(train[FEATURES], train.diabetes)
        oof.iloc[te, 2] = search.predict_proba(test[FEATURES])[:, 1]
        chosen.append(search.best_params_)
        print(f"  outer fold {i}/10 done: {search.best_params_}", flush=True)

    # per-fold means, matching how the earlier GLM scripts report CV metrics
    rows = {}
    for m in oof:
        per_fold = pd.DataFrame([scores(y.iloc[te], oof[m].iloc[te]) for _, te in folds])
        rows[m] = per_fold.mean().to_dict() | {"AUC sd": per_fold["CV AUC"].std(ddof=0)}

    full_y = df.diabetes
    full_folds = StratifiedKFold(10, shuffle=True, random_state=SEED).split(df, full_y)
    per_fold = []
    for tr, te in full_folds:
        s = tuned_xgb(df.iloc[tr][ALL_FEATURES], full_y.iloc[tr])
        per_fold.append(scores(full_y.iloc[te], s.predict_proba(df.iloc[te][ALL_FEATURES])[:, 1]))
    pf = pd.DataFrame(per_fold)
    rows["xgb, 768 rows, 8 vars*"] = pf.mean().to_dict() | {"AUC sd": pf["CV AUC"].std(ddof=0)}

    print("\n10-fold CV (same folds for the first three; XGBoost tuned by nested 5-fold CV):")
    print(pd.DataFrame(rows).T.round(4).to_string())
    print("* different rows/folds, so only roughly comparable\n")

    final = tuned_xgb(data[FEATURES], y)
    print(f"Final XGBoost hyperparameters (tuned on all {len(data)} rows): {final.best_params_}")
    model = final.best_estimator_
    model.save_model("pima_xgb.json")

    contribs = model.get_booster().predict(xgb.DMatrix(data[FEATURES]), pred_contribs=True)
    shap = pd.Series(np.abs(contribs[:, :-1]).mean(axis=0), index=FEATURES).sort_values(ascending=False)
    print("\nMean |SHAP| (log-odds contribution) by predictor:")
    print(shap.round(3).to_string())

    grid = pd.DataFrame({"bmi": [20, 25, 30, 35, 40, 45, 50]})
    for c in OTHERS.split(" + "):
        grid[c] = data[c].median()
    grid["xgb"] = model.predict_proba(grid[FEATURES])[:, 1]
    grid["logit_spline"] = smf.glm(SPLINE, data=data, family=sm.families.Binomial()).fit().predict(grid)
    print("\nPredicted probability by BMI, other predictors at medians:")
    print(grid.set_index("bmi")[["xgb", "logit_spline"]].round(3).to_string())

    fitted = pd.DataFrame({
        "logit": smf.glm(MAIN, data=data, family=sm.families.Binomial()).fit().predict(data),
        "logit_spline": smf.glm(SPLINE, data=data, family=sm.families.Binomial()).fit().predict(data),
        "xgb": model.predict_proba(data[FEATURES])[:, 1]})
    fitted["xgb_out_of_fold"] = oof.xgb
    cols = ["glucose", "bmi", "pedigree", "pregnancies", "age", "diabetes"]
    for title, rows_ in (("Earlier top-5 (linear logistic)", [445, 228, 159, 546, 622]),
                         ("Closest to 30% under linear logistic", [747, 547, 757, 21, 296, 69]),
                         ("Lean, older/multiparous: logistic models disagreed", [460, 749, 299, 401, 464, 93])):
        print(f"\n{title}:")
        print(pd.concat([data.loc[rows_, cols], fitted.loc[rows_].round(3)], axis=1).to_string())
    top = fitted.xgb.nlargest(5).index
    print("\nTop 5 under XGBoost (in-sample):")
    print(pd.concat([data.loc[top, cols], fitted.loc[top].round(3)], axis=1).to_string())
    print(f"\nIn-sample prediction range: xgb {fitted.xgb.min():.3f}-{fitted.xgb.max():.3f}, "
          f"out-of-fold {oof.xgb.min():.3f}-{oof.xgb.max():.3f}")
    print("Model saved to pima_xgb.json")


if __name__ == "__main__":
    main()
