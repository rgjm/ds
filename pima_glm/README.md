# Pima diabetes GLM

Logistic regression (binomial GLM, logit link) predicting diabetes from the Pima Indians Diabetes
dataset (768 women aged 21+, NIDDK via UCI; `pima-indians-diabetes.csv`, column notes in `.names`).

```sh
.venv/bin/python glm.py     # fits, evaluates, writes pima_glm.pickle; output saved in results.txt
```

- Zeros in glucose, blood pressure, BMI, skin thickness and insulin are recoded as missing.
- Main model: pregnancies + glucose + blood_pressure + bmi + pedigree + age, on 724 complete rows.
  Skin thickness and insulin are excluded (30% / 49% missing) and don't improve the fit on the
  392 rows where they're recorded.
- Load the final model with `statsmodels.genmod.generalized_linear_model.GLMResults.load("pima_glm.pickle")`
  and call `.predict(df)` on a DataFrame with the same column names.

`compare_glms.py` fits the same predictors as binomial/logit, gaussian/identity (linear probability)
and poisson/log (relative risk) GLMs and compares effects, AIC, CV AUC/Brier and out-of-range
predictions; output in `compare_results.txt`.

`bmi_splines.py` refits the logistic model with BMI as a natural cubic spline (3-6 df) plus a
penalised-spline GAM check; output in `bmi_spline_results.txt`, curve in `bmi_spline.png`.

`xgb_model.py` trains XGBoost (nested CV: inner 5-fold grid search, outer 10 folds shared with the
logistic models), plus an all-768-rows/8-variable variant; output in `xgb_results.txt`, final model
in `pima_xgb.json` (load with `xgboost.XGBClassifier().load_model("pima_xgb.json")`).
