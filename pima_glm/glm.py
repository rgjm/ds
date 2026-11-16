#!/usr/bin/env python3
"""Logistic-regression GLM (binomial, logit link) for diabetes in the Pima Indians Diabetes dataset.

Data: pima-indians-diabetes.csv (768 women of Pima heritage, aged 21+; NIDDK via UCI).
Zeros in glucose, blood pressure, skin thickness, insulin and BMI are physiologically impossible
and are recoded as missing. Skin thickness (30% missing) and insulin (49% missing) are left out of
the main model and checked separately on complete cases.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

COLS = ["pregnancies", "glucose", "blood_pressure", "skin_thickness", "insulin",
        "bmi", "pedigree", "age", "diabetes"]
MAIN = "diabetes ~ pregnancies + glucose + blood_pressure + bmi + pedigree + age"
FULL = MAIN + " + skin_thickness + insulin"
# odds ratios are reported per these increments so they're easier to read
UNITS = {"pregnancies": 1, "glucose": 10, "blood_pressure": 10, "bmi": 5, "pedigree": 0.5,
         "age": 10, "skin_thickness": 10, "insulin": 50}
SEED = 42


def load():
    df = pd.read_csv("pima-indians-diabetes.csv", header=None, names=COLS)
    for c in ["glucose", "blood_pressure", "skin_thickness", "insulin", "bmi"]:
        df[c] = df[c].replace(0, np.nan)
    return df


def fit(formula, data):
    return smf.glm(formula, data=data, family=sm.families.Binomial()).fit()


def odds_ratios(model):
    ci = model.conf_int()
    rows = []
    for v in model.params.index.drop("Intercept"):
        u = UNITS[v]
        rows.append({"variable": v, "per": u, "odds_ratio": np.exp(model.params[v] * u),
                     "ci_low": np.exp(ci.loc[v, 0] * u), "ci_high": np.exp(ci.loc[v, 1] * u),
                     "p_value": model.pvalues[v]})
    return pd.DataFrame(rows).set_index("variable")


def calibration(y, p, bins=5):
    d = pd.DataFrame({"y": y, "p": p})
    d["bin"] = pd.qcut(d.p, bins, labels=False)
    return d.groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))


def cv_auc(formula, data, folds=10):
    aucs = []
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=SEED).split(data, data.diabetes):
        m = fit(formula, data.iloc[tr])
        aucs.append(roc_auc_score(data.diabetes.iloc[te], m.predict(data.iloc[te])))
    return np.mean(aucs), np.std(aucs)


def main():
    pd.set_option("display.width", 120)
    df = load()
    print(f"{len(df)} rows, {df.diabetes.mean():.1%} diabetic. Missing after recoding zeros:")
    print(df.isna().sum()[lambda s: s > 0].to_string(), "\n")

    data = df.dropna(subset=["glucose", "blood_pressure", "bmi"])
    print(f"Main model uses {len(data)} complete rows (dropped {len(df) - len(data)}).\n")

    train, test = train_test_split(data, test_size=0.25, stratify=data.diabetes, random_state=SEED)
    model = fit(MAIN, train)
    print(model.summary(), "\n")
    print("Odds ratios (95% CI):")
    print(odds_ratios(model).round(3).to_string(), "\n")

    p = model.predict(test)
    y = test.diabetes
    pred = (p >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
    print(f"Held-out test set (n={len(test)}):")
    print(f"  AUC {roc_auc_score(y, p):.3f}   accuracy {accuracy_score(y, pred):.3f} "
          f"(baseline {1 - y.mean():.3f})   Brier {brier_score_loss(y, p):.3f}")
    print(f"  at 0.5 cutoff: sensitivity {tp / (tp + fn):.3f}, specificity {tn / (tn + fp):.3f}")
    print("  calibration by predicted-risk quintile:")
    print(calibration(y.values, p.values).round(3).to_string(), "\n")

    m, s = cv_auc(MAIN, data)
    print(f"10-fold CV AUC, main model: {m:.3f} ± {s:.3f}")

    cc = df.dropna()
    m_main, s_main = cv_auc(MAIN, cc)
    m_full, s_full = cv_auc(FULL, cc)
    full = fit(FULL, cc)
    print(f"\nSensitivity check on {len(cc)} rows with skin thickness and insulin recorded:")
    print(f"  CV AUC without them {m_main:.3f} ± {s_main:.3f}, with them {m_full:.3f} ± {s_full:.3f}")
    print(f"  AIC without {fit(MAIN, cc).aic:.1f}, with {full.aic:.1f}")
    print(odds_ratios(full).loc[["skin_thickness", "insulin"]].round(3).to_string())

    final = fit(MAIN, data)
    final.save("pima_glm.pickle")
    print(f"\nFinal model refit on all {len(data)} rows saved to pima_glm.pickle")
    print(odds_ratios(final).round(3).to_string())


if __name__ == "__main__":
    main()
