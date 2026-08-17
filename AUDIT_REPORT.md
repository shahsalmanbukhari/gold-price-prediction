# Gold Price Prediction — Audit Report and Implementation Status

Audit date: 2026-08-17  
Repository: `/Users/developer/PycharmProjects/GoldPricePredicton`

Scope: training, prediction, multi-horizon forecasting, post-horizon evaluation, persistence, retraining, dashboard behavior, database state, and README accuracy.

The original audit below was produced read-only. It is retained as a historical
record of the architecture observed before corrective implementation.

> **Status update — 2026-08-17:** Several findings in the original audit have
> since been corrected. Sections 1–18 describe the original evidence and must
> not be interpreted as the current implementation without consulting
> [Section 19](#19-post-audit-implementation-status--2026-08-17).

## 1. Executive summary

The application currently has three materially different prediction implementations:

1. The default Original Forecast Dashboard uses legacy daily CSV-trained artifacts through `src/predict.py`.
2. The visible multi-horizon dashboard uses an `adaptive_momentum` calculation in `HorizonPredictionService`.
3. `RealtimeModelTrainer.predict_next_price()` loads newly trained candle-model artifacts, but no user-facing page calls it.

The central architectural defect is that the visible 3m–240m forecasts are not produced by the model trained by `RealtimeModelTrainer`. Retraining therefore does not improve or replace their forecasting algorithm. It can only change the displayed `model_version` label indirectly and possibly affect an adaptive error-bias term through evaluated predictions.

Critical findings:

- Visible multi-horizon forecasts are momentum extrapolations, not trained-model inference.
- The stored `model_version` can name a realtime artifact that was never used to calculate the prediction.
- Post-horizon evaluation selects the first live quote at or after the target with no maximum delay. Observed evaluated predictions used quotes approximately 4 hours 48–50 minutes late.
- Target times are wall-clock offsets, not future market-minute targets.
- The realtime trainer has no untouched test set, baseline comparison, walk-forward validation, embargo, or gap-aware target construction.
- The current realtime artifacts contain 128 features, while current code defines exactly 18. `predict_next_price()` is therefore artifact/schema incompatible.
- `horizon_predictions` lacks symbol, provider, timeframe, algorithm version, explicit status, and a uniqueness constraint.
- The performance page reports `100 - percentage error` as “accuracy” and shows best/worst horizons with as little as one observation.
- Background retraining writes directly to active artifact paths non-atomically, without candidate promotion, a cross-process lock, or automated rollback.
- The configured 250,000-row training cap uses only about 8.5 wall-clock months of the available 17.4-year candle range.
- Missing-minute gaps are detected for display context but ignored during training and forecasting.

Direct answers:

1. **Does the visible multi-horizon page use the model trained by `RealtimeModelTrainer`?** No.
2. **What generates its predictions?** Median recent log-return drift, horizon scaling, volatility-based intervals, and an adaptive historical-error bias.
3. **Does retraining change those displayed predictions?** Not directly. It does not replace the forecasting calculation.
4. **Which user-facing page uses `predict_next_price()`?** None found.
5. **Is the legacy daily model still active?** Yes. It is the default forecast page.
6. **Can two pages show unrelated predictions?** Yes. The original dashboard and live dashboard use unrelated algorithms and timeframes.
7. **Are paths unused?** Yes. `RealtimeModelTrainer.predict_next_price()` and `RealtimePredictor` are not connected to routed pages or the active streamer.

## 2. Architecture found in code

The project is a Python/Streamlit application, not a frontend-plus-REST-backend architecture.

```text
HistData ZIPs
    → historical importer
    → gold_price_candles (histdata/XAUUSD/1m)

Live provider
    → enhanced streamer
    → prices (irregular live snapshots)
    → HorizonPredictionService
    → horizon_predictions
    → post-horizon evaluator
    → performance dashboards

gold_price_candles
    → shared candle feature builder
    → RealtimeModelTrainer
    → *_realtime.pkl artifacts
    → currently no routed user-facing inference consumer

Legacy processed CSV
    → legacy trainer
    → legacy daily artifacts
    → Original Forecast Dashboard
```

Navigation is defined in `app/main.py:10-24`:

- Original Forecast Dashboard
- Intelligent Overview
- Live Predictions
- Performance
- Self-Learning

The enhanced streamer creates the provider, persistence layer, prediction service, and retraining scheduler in `realtime/streamer_enhanced.py:48-60`. For each new live snapshot, it persists the quote, evaluates due predictions, and generates a new horizon batch at lines 189-208.

### Finding A-01 — Disconnected training and visible inference

- **Severity:** Critical
- **Evidence:** `src/realtime_trainer.py:324-386`; `src/horizon_prediction_service.py:97-113`
- **Current behavior:** The trainer writes sklearn artifacts, while the live page uses a separate mathematical forecast.
- **Risk:** Users may believe retraining improves visible predictions when it does not.
- **Recommended correction:** Make the visible service load and execute explicitly versioned horizon artifacts, or clearly relabel the dashboard as an adaptive momentum baseline.

## 3. Prediction-path matrix

| Prediction path | Source | User-facing consumer | Input | Features/target | Model/algorithm | Artifact | Persistence | Active |
|---|---|---|---|---|---|---|---|---|
| Multi-horizon live | `src/horizon_prediction_service.py:35-142` | Live Predictions; streamer and page fallback | `gold_price_candles`, plus latest `prices` quote | Recent close log returns; feature builder only used as availability gate | Adaptive momentum | None used; artifact mtime may label version | `horizon_predictions` | Yes |
| Realtime trained-model inference | `src/realtime_trainer.py:324-386` | None found | `gold_price_candles` | Current candle feature builder; next-row close target | LR/RF/XGBoost | `*_model_realtime.pkl`, scaler, feature list | None | No routed consumer |
| Legacy daily forecast | `src/predict.py:13-127` | `app/streamlit_app.py:415-522` | Processed daily CSV | Legacy 111-column feature set; next row/day | LR/RF/XGBoost | Legacy `*_model.pkl`, `scaler.pkl` | None | Yes |
| Legacy realtime predictor | `src/realtime_predictor.py:25-238` | None found | Redis or irregular `prices` snapshots | Separate realtime feature implementation | Legacy serialized model | Legacy model/scaler | `predictions` | Self-test/manual only |
| Standalone realtime dashboard | `app/realtime_dashboard.py` | Not routed by `app/main.py` | Horizon service | Same adaptive forecast | Adaptive momentum | None used | `horizon_predictions` | Inactive unless manually launched |
| Legacy evaluation | `src/evaluate.py` | None | Processed CSV | Legacy features/targets | Evaluates legacy artifacts | Legacy artifacts | Reports/files | Manual |

### Exact visible multi-horizon algorithm

At `src/horizon_prediction_service.py:97-113`:

```text
returns = diff(log(close))
recent_returns = last 60 returns
drift = median(recent_returns)
volatility = standard deviation(recent_returns)

forecast_return =
    drift * horizon_minutes / sqrt(max(1, horizon_minutes / 5))
    + adaptive_bias

predicted_price =
    latest_live_or_candle_price * exp(forecast_return)
```

The adaptive bias is calculated from up to 100 evaluated predictions for the same horizon, with at least five required observations (`src/horizon_prediction_service.py:60-76`).

Uncertainty is heuristic:

```text
interval_pct =
    max(0.0005, 1.96 * volatility * sqrt(horizon_minutes))

confidence =
    clip(100 * (1 - interval_pct * 8), 50, 99)
```

This is not a calibrated prediction interval or statistically validated confidence probability.

### Finding P-01 — Misleading model identity

- **Severity:** Critical
- **Evidence:** `src/horizon_prediction_service.py:42-51,126`
- **Current behavior:** Predictions are saved as `adaptive_momentum`, but `model_version` can be taken from the newest realtime artifact timestamp.
- **Risk:** Performance may be attributed to an artifact that was never loaded.
- **Recommended correction:** Store separate `algorithm_name`, `algorithm_version`, and actual artifact version. Never assign an artifact version unless that artifact generated the value.

### Finding P-02 — Dead trained inference path

- **Severity:** High
- **Evidence:** No call to `predict_next_price()` was found outside `src/realtime_trainer.py:415`.
- **Current behavior:** Training creates artifacts that no routed dashboard consumes.
- **Risk:** Training expenditure has no production inference effect.
- **Recommended correction:** Connect approved artifact inference to the production lifecycle with compatibility checks and explicit fallback behavior.

### Finding P-03 — Unrelated predictions across pages

- **Severity:** High
- **Evidence:** `app/streamlit_app.py:415-522`; `app/dashboard_pages.py:124-149`
- **Current behavior:** The original page presents legacy daily artifact predictions; the live page presents adaptive momentum.
- **Risk:** Users may compare incompatible forecasts without knowing their datasets, targets, or algorithms differ.
- **Recommended correction:** Display algorithm, dataset, timeframe, horizon, and version prominently on every page.

## 4. Training-data audit

### Exact production candle query

The trainer calls `CandleDataService.completed_1m()` at `src/realtime_trainer.py:83-93`. The query is defined at `src/candle_data_service.py:14-25`:

```text
Table: gold_price_candles
Provider: histdata
Symbol: XAUUSD
Timeframe: 1m
Ordering: candle_time DESC in SQL, reversed to ascending afterward
Maximum rows: TRAINING_MAX_CANDLES, default 250,000
```

`candles_to_frame()` sorts ascending and drops duplicate timestamps at `src/candle_features.py:27-33`.

### Database evidence

| Property | Observed value |
|---|---:|
| Total `histdata/XAUUSD/1m` candles | 6,100,225 |
| Minimum candle UTC | 2009-03-15 22:00:00 UTC |
| Maximum candle UTC | 2026-08-14 21:58:00 UTC |
| Latest training-window rows | 250,000 |
| Latest-window start | 2025-11-28 10:49:00 UTC |
| Latest-window end | 2026-08-14 21:58:00 UTC |
| Latest-window wall-clock span | 259.46 days, approximately 8.5 months |
| Continuous-minute equivalent | 173.61 days |
| Duplicate HistData timestamps | 0 |
| Invalid OHLC records found | 0 |
| NULL volume | 6,100,225 |
| Positive volume | 0 |
| Gap events in latest 250,000 | 207 |
| Missing minutes in latest window | 123,630 |
| Largest latest-window gap | 4,382 minutes |
| Gap events across all candles | 35,632 |
| Missing minutes across all candles | 3,059,614 |
| Largest overall gap | 4,601 minutes |

The code would load 250,000 rows under the current configuration. An actual training invocation was deliberately not run because it would overwrite model artifacts.

The available history spans approximately 17.4 years. Only the newest 250,000 rows—about 8.5 wall-clock months—are used by default.

### Verification results

- Only `gold_price_candles` used: **Yes.**
- `prices` snapshots used as training candles: **No.**
- Sorted before feature generation: **Yes.**
- Duplicate timestamp defense: **Database uniqueness plus DataFrame deduplication.**
- Complete-candle status enforced: **No explicit completion column exists.** All stored candle rows are assumed completed.
- Full OHLC validation enforced at import: **Partially.**
- Missing gaps detected during training: **No.**
- Weekend/market closures intentionally handled: **No.**
- HistData fixed UTC−5 conversion: Implemented at `src/historical_zip_importer.py:124-137`.
- Volume treated as a feature: **No.**

### Finding D-01 — Training across discontinuities

- **Severity:** Critical
- **Evidence:** `src/candle_features.py:71`; `src/realtime_trainer.py:83-93`
- **Current behavior:** The target uses the next database row even if it occurs after a gap or closure.
- **Risk:** The target semantics are not consistently “next minute.”
- **Recommended correction:** Build contiguous sessions, require an exact one-minute successor, and implement a market-calendar/closure policy.

### Finding D-02 — Most available history excluded

- **Severity:** High
- **Evidence:** 250,000-row cap versus 6,100,225 eligible rows.
- **Current behavior:** Approximately 4.1% of available candles are used.
- **Risk:** Training may be dominated by the most recent regime; long-history training claims are inaccurate.
- **Recommended correction:** Make the dataset-window policy explicit and compare rolling versus longer chronological datasets.

### Finding D-03 — Import validation is incomplete

- **Severity:** Medium
- **Evidence:** `src/historical_zip_importer.py:152-157`
- **Current behavior:** Positive values and `high >= low` are checked, but full open/close containment is not clearly enforced.
- **Risk:** Structurally invalid candles could be accepted.
- **Recommended correction:** Require `high >= max(open, close, low)` and `low <= min(open, close, high)`.

## 5. Leakage audit

### Exact feature order

Defined at `src/candle_features.py:10-15`:

1. `Open`
2. `High`
3. `Low`
4. `Close`
5. `SMA_7`
6. `SMA_14`
7. `SMA_30`
8. `EMA_7`
9. `EMA_14`
10. `Price_Change`
11. `Price_Change_Pct`
12. `Volatility_7`
13. `Volatility_14`
14. `RSI_14`
15. `Close_Lag_1`
16. `Close_Lag_2`
17. `Close_Lag_3`
18. `Close_Lag_7`

### Feature construction

| Feature | Formula/source | Window | Uses future data? |
|---|---|---:|---|
| Open/High/Low/Close | Current completed candle | Current row | No |
| SMA_7/14/30 | Rolling mean of close | 7/14/30 | No |
| EMA_7/14 | `ewm(span=n, adjust=False)` on close | 7/14 | No |
| Price_Change | `Close.diff()` | 1 | No |
| Price_Change_Pct | `Close.pct_change() * 100` | 1 | No |
| Volatility_7/14 | Rolling standard deviation of close price level | 7/14 | No |
| RSI_14 | Rolling mean gain/loss from close delta | 14 | No |
| Close_Lag_1/2/3/7 | `Close.shift(n)` | 1/2/3/7 | No |

Implementation: `src/candle_features.py:49-71`.

Target:

```python
Target = Close.shift(-1)
```

Therefore:

```text
target at row t = close at next retained row
```

It is only `close at t+1 minute` when the next row is exactly one minute later.

### Leakage checklist

| Check | Result |
|---|---|
| Negative feature shifts | No |
| Centered rolling windows | No |
| Global normalization before split | No |
| Scaler fitted before split | No |
| Scaler fit only on training rows | Yes |
| Backfill from future observations | No evidence |
| Current target close used as input | No; current close is a valid persistence feature |
| Random shuffling | No |
| Deduplication after target creation | No; deduplication occurs first |
| Indicators cross missing gaps | Yes |
| Training target crosses split boundary | Yes |
| Final untouched test data | No realtime test set exists |

The realtime trainer computes causal features before splitting, fits the scaler only on training rows, and applies it to validation rows. That scaler behavior is correct. However, the last training feature row can use a target from the validation period because the negative target shift happens before splitting.

### Artifact compatibility evidence

Read-only artifact inspection found:

```text
Current code feature count:                 18
linear_regression_model_realtime.pkl:      128
linear_regression_scaler_realtime.pkl:     128
linear_regression_features_realtime.pkl:   list of 128
random_forest_model_realtime.pkl:          128
random_forest_scaler_realtime.pkl:         128
random_forest_features_realtime.pkl:       list of 128
```

### Finding L-01 — Artifact/schema mismatch

- **Severity:** Critical
- **Evidence:** `src/candle_features.py:10-15`; `src/realtime_trainer.py:340-364`
- **Current behavior:** `predict_next_price()` loads a 128-column artifact list while current code creates 18 features.
- **Risk:** Inference failure or incompatible inputs.
- **Recommended correction:** Add explicit feature-schema validation and reject incompatible artifacts before activation.

### Finding L-02 — Split-boundary target leakage

- **Severity:** High
- **Evidence:** Target is shifted before the chronological split in `src/realtime_trainer.py`.
- **Current behavior:** The final training feature may have a validation-period target.
- **Risk:** Optimistic validation and improperly separated datasets.
- **Recommended correction:** Purge boundary rows with an embargo at least as large as the prediction horizon.

### Finding L-03 — Training and visible inference inconsistency

- **Severity:** Critical
- **Evidence:** The horizon service verifies that shared features are nonempty but does not use their values.
- **Current behavior:** Visible forecasting uses close returns; training uses 18 OHLC indicators.
- **Risk:** Trainer metrics do not validate visible predictions.
- **Recommended correction:** Use one versioned feature and inference pipeline for the production model.

## 6. Model-evaluation audit

### Realtime trainer split

The trainer uses a chronological training/validation division at `src/realtime_trainer.py:107-158`.

- Training set: Yes.
- Validation set: Yes.
- Untouched test set: **No.**
- Walk-forward validation: **No.**
- Gap/embargo: **No.**
- Horizon targets purged at boundaries: **No.**
- Random shuffle: No evidence.

Realtime trainer metrics:

- Training RMSE
- Validation RMSE
- Training R²
- Validation R²

Missing:

- MAE
- MAPE or sMAPE
- Directional accuracy
- Persistence baseline
- Zero-return baseline
- Most-common-direction baseline
- Improvement over baseline
- Confidence calibration
- Per-regime metrics

Legacy `src/evaluate.py:58-108` calculates RMSE, MAE, MAPE, and R², but it evaluates the old daily CSV model rather than the visible multi-horizon forecast.

Numerical realtime-model metrics are **NOT VERIFIED** because running training would modify active artifacts.

Whether a reported high R² is primarily price-level persistence is also **NOT VERIFIED numerically**. Structurally this is a serious risk because current close is an input, the target is the next price level, and no persistence baseline is calculated.

### Finding E-01 — No untouched realtime test set

- **Severity:** Critical
- **Evidence:** `src/realtime_trainer.py:107-158`
- **Current behavior:** Only train and validation partitions exist.
- **Risk:** There is no unbiased promotion measurement.
- **Recommended correction:** Add chronological train/validation/test or purged walk-forward evaluation.

### Finding E-02 — No naive baselines

- **Severity:** Critical
- **Current behavior:** Neither realtime training nor horizon evaluation compares against persistence or zero return.
- **Risk:** A model can appear accurate while performing worse than “future price equals current close.”
- **Recommended correction:** Require baseline MAE, RMSE, directional accuracy, and relative improvement.

## 7. Multi-horizon audit

All visible horizons are produced by one adaptive formula.

| Horizon | Exact target | Separate model? | Input | Target-time rule | Closure handling |
|---:|---|---|---|---|---|
| 3m | Predicted price after scaled return | No | Up to 300 candles; recent 60 returns | `created_at + 3 minutes` | Ignored |
| 5m | Same | No | Same | `+5 minutes` | Ignored |
| 15m | Same | No | Same | `+15 minutes` | Ignored |
| 30m | Same | No | Same | `+30 minutes` | Ignored |
| 60m | Same | No | Same | `+60 minutes` | Ignored |
| 240m | Same | No | Same | `+240 minutes` | Ignored |

- Recursively calls a one-minute trained model: **No.**
- Momentum extrapolation: **Yes.**
- Output: price, trend, heuristic range, and heuristic confidence.
- Missing-candle behavior: Reports a count but still forecasts.
- Independent horizon evaluation: Each stored row is evaluated independently.
- Independent horizon training: **No.**
- Calibrated uncertainty: **No.**

A 240-minute forecast means four wall-clock hours, not 240 actual tradable one-minute candles.

### Finding H-01 — Horizon semantics incorrect around closures

- **Severity:** Critical
- **Evidence:** `src/horizon_prediction_service.py:117`
- **Current behavior:** Target time is a simple `timedelta`.
- **Risk:** Weekend and closure forecasts have inconsistent economic horizons.
- **Recommended correction:** Define elapsed-time versus market-minute semantics and implement an approved calendar policy.

### Finding H-02 — Confidence is not calibrated

- **Severity:** High
- **Current behavior:** Confidence is clipped to 50–99 from a volatility heuristic.
- **Risk:** Users may interpret it as a validated probability.
- **Recommended correction:** Label it heuristic until empirical coverage is calibrated by horizon.

## 8. Prediction-lifecycle audit

### `horizon_predictions` schema

Entity: `src/database.py:209-236`.

| Field | Type | Constraint/index |
|---|---|---|
| `id` | Integer | Primary key |
| `batch_id` | String | Not null, indexed |
| `created_at` | DateTime | Not null, indexed |
| `target_at` | DateTime | Not null, indexed |
| `horizon_minutes` | Integer | Not null, indexed |
| `horizon_label` | String | Not null |
| `current_price` | Float | Not null |
| `predicted_price` | Float | Not null |
| `confidence` | Float | Nullable |
| `lower_bound` | Float | Nullable |
| `upper_bound` | Float | Nullable |
| `predicted_trend` | String | Nullable |
| `model_name` | String | Not null |
| `model_version` | String | Not null, indexed |
| `actual_price` | Float | Nullable |
| `actual_at` | DateTime | Nullable |
| `error_amount` | Float | Nullable |
| `error_pct` | Float | Nullable |
| `accuracy_score` | Float | Nullable |
| `actual_trend` | String | Nullable |
| `direction_correct` | Boolean | Nullable |
| `result_class` | String | Nullable, indexed |
| `evaluated_at` | DateTime | Nullable |
| `context` | JSON | Nullable |

Missing requested fields:

- `symbol`
- `timeframe`
- typed `feature_data_until`
- explicit `reference_price`
- `predicted_return`
- `algorithm_version`
- explicit `status`
- typed `latest_live_price_time`
- typed `last_completed_candle_time`
- typed `missing_period_count`
- absolute-error field
- actual provider and evaluation-policy version

Some of these values exist only inside JSON context.

There is no database uniqueness constraint. Duplicate prevention is only an application comparison with the most recent prediction context. No duplicate `(batch_id, horizon_minutes)` rows existed at audit time, but the schema does not prevent them.

### Post-horizon evaluation behavior

Evaluator: `src/horizon_prediction_service.py:147-182`.

1. Selects rows where `actual_price IS NULL` and `target_at <= datetime.utcnow()`.
2. Queries `prices`.
3. Filters `symbol = XAUUSD` and `source = live_api`.
4. Does **not** filter provider.
5. Selects the first live quote with `timestamp >= target_at`.
6. Uses `price_usd`.
7. Missing outcomes remain pending.
8. No target tolerance exists.
9. During closures, the first later quote can be used even days later.
10. No completed-candle concept applies because irregular quotes supply the actual.
11. Selection is independent of predicted value.
12. Pending records retry on later streamer iterations.
13. Outcome fields commit together, without a row lock.
14. Evaluation is normally idempotent because evaluated rows no longer match `actual_price IS NULL`.
15. Database constraints do not prohibit later manual alteration.

Actual formulas:

```text
error_amount = actual_price - predicted_price
```

This is signed, not absolute.

```text
error_pct =
    ABS(actual_price - predicted_price) / actual_price * 100

accuracy_score = MAX(0, 100 - error_pct)
```

The denominator is actual price, not the prediction reference price.

Direction uses a ±0.05% stability band:

```text
change_pct = (end - start) / start * 100

up     when change_pct > 0.05
down   when change_pct < -0.05
stable otherwise

direction_correct = predicted_trend == actual_trend
```

### Observed database outcome

At audit time:

- One six-horizon adaptive-momentum batch existed.
- The 3m and 5m rows were resolved.
- The 15m, 30m, 60m, and 240m rows were pending.
- The 3m selected actual was approximately 17,400 seconds late.
- The 5m selected actual was approximately 17,280 seconds late.
- Prediction creation was around `2026-08-16 22:17`, while stored live context reported approximately `2026-08-17 03:17`, a five-hour discrepancy.

The exact external cause—provider timestamp behavior versus another timezone boundary—is **NOT VERIFIED** without capturing the raw response at ingestion.

### Finding LC-01 — Actual outcome can be hours or days late

- **Severity:** Critical
- **Evidence:** No maximum tolerance; observed outcomes were approximately 4h48–4h50 late.
- **Current behavior:** The first quote after the target wins regardless of distance.
- **Risk:** Evaluation does not measure the requested horizon.
- **Recommended correction:** Use a bounded, documented actual-selection window and mark expired outcomes unresolvable.

### Finding LC-02 — Provider is not pinned

- **Severity:** Critical
- **Current behavior:** Evaluator filters source and symbol but not provider.
- **Risk:** Cross-provider differences contaminate metrics.
- **Recommended correction:** Persist intended provider and filter actual outcomes accordingly.

### Finding LC-03 — No immutable prediction identity

- **Severity:** High
- **Current behavior:** No unique rule or database immutability enforcement exists.
- **Risk:** Duplicate forecasts and ambiguous attribution.
- **Recommended correction:** Add a uniqueness rule covering symbol, timeframe, horizon, feature cutoff, and algorithm version; restrict updates to outcome fields.

### Finding LC-04 — Future timestamp considered fresh

- **Severity:** Critical
- **Current behavior:** A timestamp later than local UTC produces a negative age and is treated as current.
- **Risk:** Predictions operate on temporally inconsistent observations.
- **Recommended correction:** Reject or quarantine timestamps outside a clock-skew tolerance and preserve raw and ingestion timestamps separately.

## 9. Performance-page audit

Routed page: `app/dashboard_pages.py:152-209`.

### Filters

- Date range: 1, 7, 30, or 90 days.
- Horizon.
- No model-version filter.
- No provider filter.
- No algorithm filter.
- No evaluation-delay filter.

### Displayed metrics and charts

- Resolved sample count.
- Mean `accuracy_score`.
- Mean `error_pct`.
- Mean direction correctness.
- Target threshold.
- Best/worst horizon.
- Resolved count by horizon.
- Rolling 20-record accuracy chart.
- Record table with creation time, horizon, predicted price, actual price, error percentage, accuracy, predicted/actual trend, result class, and model version.

### Missing or inadequate

| Requirement | Result |
|---|---|
| Pending predictions | Not shown on performance page |
| Failed/unresolvable | No status exists |
| MAE | Not shown |
| RMSE | Not shown |
| MAPE/sMAPE | Mean stored error percentage only |
| Directional accuracy | Yes |
| Baselines | No |
| Improvement over baseline | No |
| Accuracy by horizon | Yes, using `100-error_pct` |
| Accuracy over time | Rolling score |
| Prediction count | Resolved count only |
| Pending count | Overview only |
| Model version | In records, without grouping/filtering |
| Target time | Missing from record table |
| Reference price | Missing from record table |
| Evaluation time | Missing from record table |
| Minimum-sample warning | No |

### Finding UI-01 — Misleading “accuracy”

- **Severity:** Critical
- **Current behavior:** `max(0, 100-error_pct)` is presented as accuracy.
- **Risk:** A high score can look impressive even when the forecast adds no value over persistence.
- **Recommended correction:** Label it price-closeness score if retained; lead with MAE, RMSE, directional accuracy, and baseline improvement.

### Finding UI-02 — Incompatible populations aggregated

- **Severity:** High
- **Current behavior:** Overview values can mix horizons and model versions.
- **Risk:** Poor horizons or regressions are concealed.
- **Recommended correction:** Require horizon and algorithm/version grouping.

### Finding UI-03 — No small-sample protection

- **Severity:** High
- **Evidence:** Current resolved horizons had one observation each, yet best/worst ranking was available.
- **Risk:** Rankings are statistically meaningless.
- **Recommended correction:** Suppress ranking below a documented minimum and show confidence intervals.

### Finding UI-04 — Incomplete lifecycle inspection

- **Severity:** Medium
- **Current behavior:** Target time, reference price, actual timestamp, evaluation delay, and evaluation time are absent.
- **Risk:** Incorrect evaluations cannot be diagnosed from the UI.
- **Recommended correction:** Add a full record drill-down.

## 10. Retraining audit

Scheduler: `realtime/training_scheduler.py`.

### Triggers

| Trigger | Actual condition |
|---|---|
| Time | Process-local elapsed time reaches configured interval, default 24h |
| New candle | At least 50 candle IDs after startup baseline |
| Resolved outcome | At least 50 evaluated prediction IDs after startup baseline |
| Accuracy | Same minimum count and average `accuracy_score < 85` |
| Manual | An unprocessed pending `retraining_runs` row exists |
| CLI train | Calls `RealtimeModelTrainer.train_model(... use_realtime=False)` |
| CLI retrain | Calls exactly the same function |

CLI equivalence is visible at `start-all.sh:167-180`.

### Operational answers

- Multiple jobs in one scheduler process: guarded by `_training_task`.
- Multiple jobs across processes: **Possible.**
- Database/distributed lock: **No.**
- Failures isolated: Exception is recorded, but artifacts may already have changed.
- Atomic artifact writes: **No.**
- Old production model preserved: Copied to archive before training, but not automatically restored.
- Candidate evaluated before promotion: **No separate candidate stage.**
- Baseline improvement required: **No.**
- Promotion automatic: Direct overwrite.
- Rollback implemented: **No automated rollback.**
- Model version stored on predictions: Yes, but it may not identify the generating algorithm.
- Streamer safely reloads model: Visible streamer does not execute the artifact.
- Partial model load possible: **Yes.**
- `--train` differs from `--retrain`: **No.**
- Minimum outcome count enforced: 50.
- Statistical adequacy of 50: **Not established.**
- Time trigger durable across restart: **No.**

### `retraining_runs`

Entity: `src/database.py:239-256`.

It records trigger, status, timestamps, model identity, dataset size, metrics JSON, and error information. The table contained zero records during the audit, so successful runtime examples are **NOT VERIFIED**.

### Finding R-01 — Non-atomic production overwrite

- **Severity:** Critical
- **Evidence:** `src/realtime_trainer.py:251-263`
- **Current behavior:** Model, scaler, and feature files are dumped separately to active paths.
- **Risk:** A crash or concurrent read can expose a mixed artifact set.
- **Recommended correction:** Write a complete version bundle to a temporary directory, validate it, then atomically switch a manifest or pointer.

### Finding R-02 — No promotion gate

- **Severity:** Critical
- **Current behavior:** Successful training overwrites production regardless of baseline improvement.
- **Risk:** A worse model can be promoted automatically.
- **Recommended correction:** Require untouched chronological results, baseline improvement, and schema compatibility.

### Finding R-03 — No distributed training lock

- **Severity:** High
- **Current behavior:** Every streamer process has an independent memory-only guard.
- **Risk:** Multiple processes can overwrite artifacts concurrently.
- **Recommended correction:** Use a PostgreSQL advisory lock or durable job lease.

### Finding R-04 — Trigger state resets on restart

- **Severity:** High
- **Current behavior:** Baseline IDs and last-retrain time initialize at process startup.
- **Risk:** Restarts alter trigger behavior and may prevent accumulated data from triggering.
- **Recommended correction:** Persist watermarks and last successful training time.

## 11. Database/schema audit

Relevant tables:

- `prices`: irregular live snapshots.
- `gold_price_candles`: completed/imported OHLC rows.
- `historical_data_imports`: historical import audit.
- `horizon_predictions`: visible multi-horizon lifecycle.
- `predictions`: legacy realtime-predictor output.
- `retraining_runs`: training requests/results.
- `models`: model-registry-like table, currently empty.

Positive findings:

- Historical candles are separate from live snapshots.
- Training reads `gold_price_candles`, not `prices`.
- HistData uniqueness prevents duplicate provider/symbol/timeframe/timestamp rows.
- Historical volume is NULL and is not a feature.
- No invalid OHLC rows were found by the audit query.
- No raw live quote is used as OHLC by the candle trainer.

### Finding DB-01 — Float persistence for financial values

- **Severity:** Medium
- **Evidence:** `src/database.py:209-236`
- **Current behavior:** Prediction, actual, current, and error prices use floating-point types.
- **Risk:** Avoidable financial precision inconsistency.
- **Recommended correction:** Use decimal-safe persistence with an explicit rounding policy.

### Finding DB-02 — Missing outcome provenance

- **Severity:** High
- **Current behavior:** Rows do not identify actual provider, selection tolerance, or evaluator version.
- **Risk:** Metrics cannot be reproduced after policy changes.
- **Recommended correction:** Persist source table/provider, selected timestamp, delay, tolerance, and evaluator version.

### Finding DB-03 — No unresolved state

- **Severity:** High
- **Current behavior:** Missing actuals remain pending indefinitely.
- **Risk:** Silent backlog and survivor bias.
- **Recommended correction:** Add pending, evaluated, unresolvable, and failed states with reason and retry count.

## 12. README inaccuracies

README inspected: `README.md`.

### Explicit requested checks

- Mermaid block uses `````mermaid```: **Already correct** at line 38.
- Configuration table has `Variable`, `Required`, `Purpose`: **Already correct** at lines 97-98.
- `.env.example` link is relative: **Already correct** at line 117.
- Precise evaluator documentation: **Missing.**
- Trained-model versus visible-prediction relationship: Mentioned partially, but not explicit enough that retraining does not drive visible prices.

### README-01 — Diagram implies trained-feature inference

- **Severity:** High
- **Evidence:** README lines 46-50 and line 69.
- **Current behavior:** The diagram routes shared features into prediction services.
- **Risk:** Readers infer that visible forecasts execute the trained model.
- **Recommended correction:** State that current visible forecasts use adaptive momentum and only use feature construction as an availability check.

### README-02 — Evaluator policy missing

- **Severity:** Critical
- **Current behavior:** It does not disclose first-quote-after-target selection, absent provider filter, or absent tolerance.
- **Risk:** Metrics appear horizon-correct when they may use much later quotes.
- **Recommended correction:** Document source, provider, timestamp rule, tolerance, closures, formulas, and unresolved behavior.

### README-03 — Scheduled retraining described too strongly

- **Severity:** High
- **Evidence:** README around line 314.
- **Current behavior:** The 24-hour timer is process-local and resets after restart.
- **Risk:** Operators assume durable daily scheduling.
- **Recommended correction:** Describe it as elapsed-uptime scheduling until trigger state is persisted.

### README-04 — Versioned Python command can fail

- **Severity:** Medium
- **Evidence:** README line 131 uses `python3.12`; the host exposes Python 3.12.6 through `python3` but previously reported the versioned command unavailable.
- **Current behavior:** Correct Python may be installed while the documented command fails.
- **Risk:** Setup confusion.
- **Recommended correction:** Use `python3 -m venv .venv`, then verify Python is 3.12.x.

### README-05 — Artifact incompatibility warning missing

- **Severity:** Critical
- **Current behavior:** README discusses artifact inference without noting that existing artifacts expect 128 features while current code defines 18.
- **Risk:** Operators expect inference to succeed.
- **Recommended correction:** Document artifact-schema/version requirements and current incompatibility until corrected.

### README-06 — Test commands not fully proven

- **Severity:** Medium
- **Evidence:** README lines 369-394.
- **Current behavior:** Some documented diagnostics can call external providers or require configured credentials.
- **Risk:** Commands may fail in isolated environments or write state.
- **Recommended correction:** Separate pure unit, database integration, and external-provider tests with prerequisites.

No absolute `file:///Users/developer/...` link was present in the current README.

## 13. Critical defects

1. Visible horizon predictions do not use the trained realtime model.
2. Stored artifact-derived `model_version` does not identify the generating algorithm.
3. Realtime artifacts expect 128 features while current code creates 18.
4. Actual-price evaluation has no maximum delay; observed examples were nearly five hours late.
5. Actual-price provider is not pinned.
6. Wall-clock horizons are treated as market horizons.
7. Training labels cross gaps and closures as though the next row were the next minute.
8. No untouched realtime test set or baseline comparison exists.
9. Production artifacts are overwritten non-atomically.
10. No candidate promotion gate or baseline-improvement requirement exists.
11. Future-dated live timestamps can be treated as fresh.
12. Performance “accuracy” is only `100 - percentage error`.

## 14. High-priority defects

1. No prediction uniqueness constraint.
2. Missing symbol, timeframe, algorithm version, provider, and typed provenance.
3. No permanent failed/unresolvable state.
4. No distributed training lock.
5. Retraining scheduler state resets at process restart.
6. Performance aggregates across versions and sometimes horizons.
7. Rankings appear without minimum sample requirements.
8. Only about 8.5 months of the available 17.4-year history is used.
9. No market-calendar policy.
10. No split purge/embargo.
11. Legacy and live algorithms are presented without sufficient distinction.
12. `RealtimePredictor` uses a separate feature implementation and legacy symbol assumptions.

## 15. Medium-priority improvements

1. Persist prediction prices and errors with decimal-safe types.
2. Expand import-time OHLC validation.
3. Add explicit candle-completion semantics if live candles are introduced.
4. Add artifact manifests with hashes, feature schema, and library versions.
5. Distinguish expected closures from unexpected data gaps.
6. Show evaluation-delay distribution.
7. Add a full prediction-lifecycle drill-down.
8. Rename heuristic intervals/confidence until calibrated.
9. Add provider price-scale continuity monitoring.
10. Clearly label or retire the legacy daily page.
11. Add composite indexes after reviewing final query plans.
12. Preserve raw provider timestamps and ingestion provenance.

## 16. Read-only SQL diagnostics

These queries do not modify data.

### Candle partitions and ranges

```sql
SELECT
    provider,
    symbol,
    timeframe,
    COUNT(*) AS row_count,
    MIN(candle_time) AS minimum_time,
    MAX(candle_time) AS maximum_time
FROM gold_price_candles
GROUP BY provider, symbol, timeframe
ORDER BY provider, symbol, timeframe;
```

### Effective latest training window

```sql
WITH training_window AS (
    SELECT candle_time
    FROM gold_price_candles
    WHERE provider = 'histdata'
      AND symbol = 'XAUUSD'
      AND timeframe = '1m'
    ORDER BY candle_time DESC
    LIMIT 250000
)
SELECT
    COUNT(*) AS rows,
    MIN(candle_time) AS minimum_time,
    MAX(candle_time) AS maximum_time,
    MAX(candle_time) - MIN(candle_time) AS wall_clock_span
FROM training_window;
```

### Duplicate candles

```sql
SELECT provider, symbol, timeframe, candle_time, COUNT(*) AS duplicates
FROM gold_price_candles
GROUP BY provider, symbol, timeframe, candle_time
HAVING COUNT(*) > 1
ORDER BY duplicates DESC, candle_time;
```

### Invalid OHLC candles

```sql
SELECT COUNT(*) AS invalid_candles
FROM gold_price_candles
WHERE open_price <= 0
   OR high_price <= 0
   OR low_price <= 0
   OR close_price <= 0
   OR high_price < low_price
   OR high_price < GREATEST(open_price, close_price)
   OR low_price > LEAST(open_price, close_price);
```

### Missing-minute gaps

```sql
WITH ordered AS (
    SELECT
        candle_time,
        LAG(candle_time) OVER (ORDER BY candle_time) AS previous_time
    FROM gold_price_candles
    WHERE provider = 'histdata'
      AND symbol = 'XAUUSD'
      AND timeframe = '1m'
)
SELECT
    COUNT(*) AS gap_events,
    SUM(
        GREATEST(
            FLOOR(EXTRACT(EPOCH FROM (candle_time - previous_time)) / 60) - 1,
            0
        )
    ) AS missing_minutes,
    MAX(candle_time - previous_time) AS largest_gap
FROM ordered
WHERE previous_time IS NOT NULL
  AND candle_time - previous_time > INTERVAL '1 minute';
```

### Weekend rows

```sql
SELECT
    EXTRACT(ISODOW FROM candle_time AT TIME ZONE 'UTC') AS utc_weekday,
    COUNT(*) AS rows
FROM gold_price_candles
WHERE provider = 'histdata'
  AND symbol = 'XAUUSD'
  AND timeframe = '1m'
GROUP BY 1
ORDER BY 1;
```

### Volume quality

```sql
SELECT
    COUNT(*) FILTER (WHERE volume IS NULL) AS null_volume,
    COUNT(*) FILTER (WHERE volume = 0) AS zero_volume,
    COUNT(*) FILTER (WHERE volume > 0) AS positive_volume
FROM gold_price_candles
WHERE provider = 'histdata'
  AND symbol = 'XAUUSD'
  AND timeframe = '1m';
```

### Live duplicates

```sql
SELECT provider, raw_symbol, "timestamp", COUNT(*) AS rows
FROM prices
WHERE source = 'live_api'
GROUP BY provider, raw_symbol, "timestamp"
HAVING COUNT(*) > 1
ORDER BY rows DESC;
```

### Future or stale live timestamps

```sql
SELECT
    id,
    provider,
    symbol,
    raw_symbol,
    "timestamp",
    created_at,
    EXTRACT(EPOCH FROM ("timestamp" - created_at)) AS provider_minus_insert_seconds
FROM prices
WHERE source = 'live_api'
  AND (
      "timestamp" > created_at + INTERVAL '5 minutes'
      OR "timestamp" < created_at - INTERVAL '10 minutes'
  )
ORDER BY created_at DESC;
```

### Price-scale discontinuities

```sql
WITH ordered AS (
    SELECT
        id,
        provider,
        "timestamp",
        price_usd,
        LAG(price_usd) OVER (
            PARTITION BY provider, raw_symbol
            ORDER BY "timestamp"
        ) AS previous_price
    FROM prices
    WHERE source = 'live_api'
)
SELECT *,
       ABS(price_usd - previous_price) / NULLIF(previous_price, 0) * 100
           AS change_pct
FROM ordered
WHERE previous_price IS NOT NULL
  AND ABS(price_usd - previous_price) / NULLIF(previous_price, 0) > 0.05
ORDER BY "timestamp" DESC;
```

### Pending counts and evaluation delay

```sql
SELECT
    horizon_minutes,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE actual_price IS NULL) AS pending,
    COUNT(*) FILTER (WHERE actual_price IS NOT NULL) AS evaluated,
    AVG(actual_at - target_at)
        FILTER (WHERE actual_at IS NOT NULL) AS average_evaluation_delay,
    MAX(actual_at - target_at)
        FILTER (WHERE actual_at IS NOT NULL) AS maximum_evaluation_delay
FROM horizon_predictions
GROUP BY horizon_minutes
ORDER BY horizon_minutes;
```

### Model/version-separated metrics

```sql
SELECT
    model_name,
    model_version,
    horizon_minutes,
    COUNT(*) AS samples,
    AVG(ABS(actual_price - predicted_price)) AS mae,
    SQRT(AVG(POWER(actual_price - predicted_price, 2))) AS rmse,
    AVG(error_pct) AS stored_mean_error_pct,
    AVG(CASE WHEN direction_correct THEN 1.0 ELSE 0.0 END) * 100
        AS directional_accuracy
FROM horizon_predictions
WHERE actual_price IS NOT NULL
GROUP BY model_name, model_version, horizon_minutes
ORDER BY model_name, model_version, horizon_minutes;
```

### Persistence baseline comparison

```sql
SELECT
    model_name,
    model_version,
    horizon_minutes,
    COUNT(*) AS samples,
    AVG(ABS(actual_price - predicted_price)) AS model_mae,
    AVG(ABS(actual_price - current_price)) AS persistence_mae,
    AVG(ABS(actual_price - current_price))
      - AVG(ABS(actual_price - predicted_price)) AS mae_improvement
FROM horizon_predictions
WHERE actual_price IS NOT NULL
GROUP BY model_name, model_version, horizon_minutes
ORDER BY horizon_minutes, model_version;
```

### Duplicate horizon predictions

```sql
SELECT batch_id, horizon_minutes, COUNT(*) AS rows
FROM horizon_predictions
GROUP BY batch_id, horizon_minutes
HAVING COUNT(*) > 1;
```

### Provider and symbol consistency

```sql
SELECT source, provider, symbol, raw_symbol, COUNT(*) AS rows
FROM prices
GROUP BY source, provider, symbol, raw_symbol
ORDER BY source, provider, symbol, raw_symbol;
```

## 17. Recommended implementation sequence

1. Freeze current production artifacts and prediction records for traceability.
2. Define exact horizon semantics: elapsed minutes versus market minutes.
3. Fix provider timestamp validation and standardize UTC handling.
4. Redesign `horizon_predictions` provenance, uniqueness, status, and immutability.
5. Fix actual selection with provider pinning and bounded tolerance.
6. Add failed/unresolvable lifecycle states.
7. Build gap-aware contiguous training examples.
8. Purge split boundaries and add chronological test/walk-forward evaluation.
9. Implement persistence, zero-return, and direction baselines.
10. Version one shared feature schema and artifact bundle.
11. Train separate horizon models or approve a clearly defined multi-output model.
12. Connect the visible page to the approved production artifact.
13. Add candidate training, atomic artifacts, promotion criteria, lock, and rollback.
14. Rebuild performance reporting around MAE, RMSE, directional accuracy, baseline improvement, sample count, version, and delay.
15. Clearly separate or retire the legacy daily page.
16. Update README after the implementation is verified.

## 18. Files that would need modification

No files other than this report were modified to save the audit. Likely future implementation scope:

### Prediction and evaluation

- `src/horizon_prediction_service.py`
- `src/candle_data_service.py`
- `src/candle_features.py`
- `realtime/streamer_enhanced.py`

### Training and artifact lifecycle

- `src/realtime_trainer.py`
- `realtime/training_scheduler.py`
- `start-all.sh`

### Database and migrations

- `src/database.py`
- `migrations/versions/`

### Dashboard

- `app/dashboard_pages.py`
- `app/streamlit_app.py`
- `app/main.py`
- Potentially `app/realtime_dashboard.py`

### Legacy consolidation

- `src/predict.py`
- `src/train.py`
- `src/evaluate.py`
- `src/realtime_predictor.py`
- `src/realtime_features.py`

### Provider and timestamps

- `realtime/providers/gold_api_provider.py`
- `src/live_price_service.py`

### Tests and documentation

- `test_gold_api_integration.py`
- New isolated prediction, evaluator, training-split, model-promotion, and dashboard tests
- `README.md`, after fixes are approved and implemented

---

This report began as evidence from a read-only audit. Items marked **NOT
VERIFIED** in the historical sections require additional runtime evidence or a
controlled test environment before a definitive conclusion can be made.

## 19. Post-audit implementation status — 2026-08-17

This section records verified changes made after the original audit. It does
not erase the original findings; it identifies which findings are resolved,
partially resolved, or still operationally blocked.

### 19.1 Current production architecture

The current approved paths are explicitly separated:

```text
legacy_daily
    Legacy experimental dashboard and artifacts; not production inference.

adaptive_momentum_baseline
    Heuristic research baseline; not presented as a trained model.

trained_multi_horizon
    Versioned direct return models for 3m, 5m, 15m, 30m, 60m and 240m.
```

Production inference now requires a complete, approved artifact bundle. It
does not silently fall back to adaptive momentum when no approved model is
available. Candidate bundles are promoted only after passing persistence and
artifact-quality gates. Expected quality rejection is recorded as `REJECTED`,
not `FAILED`, and leaves the production manifest unchanged.

The visible dashboard is read-only with respect to model activation. The
`Viewing model` selector changes displayed results only; it cannot train,
promote, roll back, alter the production manifest, or change worker inference.

### 19.2 Prediction and evaluation lifecycle

`horizon_predictions` now stores explicit lifecycle, provenance, timing,
baseline and outcome fields. Supported statuses are:

```text
PENDING
EVALUATED
UNRESOLVABLE
FAILED
LEGACY
```

Current horizon semantics are elapsed UTC minutes:

```text
3, 5, 15, 30, 60, 240
```

Training targets require an exact candle at `feature_candle_time + horizon`.
The next available row after a gap is not treated as the target.

Outcome evaluation now:

1. Pins the actual to the prediction's stored provider and normalized symbol.
2. Uses only `prices` rows with `source = 'live_api'`.
3. Selects the first quote at or after `target_at`.
4. Requires it within `PREDICTION_ACTUAL_TOLERANCE_SECONDS`, default 90.
5. Marks expired outcomes `UNRESOLVABLE` rather than using an hours-late quote.
6. Uses idempotent/concurrency-safe lifecycle updates.
7. Records persistence-baseline error and improvement.

The obsolete `100 - percentage_error` value is not presented as model
accuracy. Current performance reporting uses MAE, RMSE, sMAPE, directional
accuracy, persistence MAE, baseline improvement, sample counts and evaluation
delay.

### 19.3 Training, features and artifact lifecycle

The shared feature schema is versioned as `candle_features_v1` and contains the
18 ordered candle features documented in Section 5. Training and inference use
the same implementation and ordering.

Current multi-horizon training:

- Reads completed `histdata/XAUUSD/1m` rows from `gold_price_candles`.
- Creates a direct return target independently for every horizon.
- Rejects targets across missing timestamps.
- Uses configurable chronological 70%/15%/15% train/validation/test splits.
- Purges split boundaries by the maximum 240-minute horizon.
- Fits scalers on training rows only.
- Calculates candidate and persistence/zero-return baseline metrics.
- Writes versioned candidates before any promotion decision.

The incompatible legacy realtime artifacts that expect 128 features are not
eligible for production inference. Artifact manifests validate feature count,
ordered names, schema version, horizon, scaler/model compatibility and file
checksums before loading.

Training outcomes are:

```text
PROMOTED — every required quality gate passed
REJECTED — training succeeded but quality gates did not pass
FAILED   — training or artifact creation failed unexpectedly
```

The current bundle policy remains all-or-nothing: every required horizon must
pass before the complete bundle is promoted. A candidate worse than
persistence at any required horizon remains archived for diagnosis and cannot
replace production.

### 19.4 Background lifecycle and notifications

Prediction generation, evaluation, notification delivery, heartbeat updates
and retraining checks run in `realtime/streamer_enhanced.py`, independently of
Streamlit. Closing the browser or stopping Streamlit does not stop an installed
background worker. The worker cannot operate while the computer is powered
off.

The macOS `launchd` integration is managed through:

```text
scripts/install-background-service.sh
scripts/start-background-service.sh
scripts/status-background-service.sh
scripts/stop-background-service.sh
scripts/uninstall-background-service.sh
```

Forecast-ready and outcome-evaluated notifications are distinct, persistent
and idempotent. Optional external delivery uses a generic configured webhook;
webhook failure does not roll back predictions or stop the worker.

### 19.5 Live-provider timestamp correction

The timestamp issue observed in the original audit has been diagnosed and
corrected without increasing `LIVE_CLOCK_SKEW_SECONDS`.

#### Root cause

Older persisted live rows contain provider timestamps approximately three
hours in the future and no raw timestamp provenance. Queries ordered only by
`prices.timestamp DESC`, allowing those preserved invalid rows to shadow newer
valid quotes. The prior Gold API parser also accepted naive timestamps by
assigning UTC and treated every numeric value as epoch seconds.

Existing invalid rows were preserved for traceability; none were deleted.

#### Correct parsing and provenance

`src/provider_timestamps.py` now:

- Parses ISO-8601 `Z` as UTC.
- Parses explicit positive/negative offsets and converts with
  `astimezone(timezone.utc)`.
- Distinguishes epoch seconds from milliseconds by value magnitude.
- Rejects missing, naive and ambiguous provider timestamps.
- Never substitutes ingestion time for a missing provider timestamp.

Live persistence preserves:

```text
provider_timestamp_raw
provider_metadata.parsedProviderTimestampUtc
provider_metadata.ingestedAtUtc
ingested_at
created_at
```

`prices.timestamp`, `prices.ingested_at` and `prices.created_at` use
timezone-aware database types. `latest_valid_live_price()` excludes legacy
future/stale rows from operational reads while keeping them in PostgreSQL.

Verified provider example:

```text
Raw field:                    updatedAt
Raw value:                    2026-08-17T01:22:01Z
Raw type:                     str
Parsed provider UTC:          2026-08-17T01:22:01+00:00
Request started UTC:          2026-08-17T01:22:13.364238+00:00
Request completed UTC:        2026-08-17T01:22:13.919119+00:00
Database ingested UTC:        2026-08-17T01:22:13.921554+00:00
Difference at persistence:    -13.064 seconds
Provider:                     gold_api
```

Server clock evidence:

```text
Python:  2026-08-17T01:16:30.671409+00:00
date -u: Mon Aug 17 01:16:30 UTC 2026
date:    Mon Aug 17 06:16:30 PKT 2026
```

The OS clock and Python UTC clock agreed. PostgreSQL may display an aware UTC
instant as `+05:00` in a Pakistan-time database session; this is presentation,
not a five-hour timestamp shift.

### 19.6 Session-aware candle freshness

`src/market_session.py` implements the current explicit XAU/USD weekend policy:

```text
Expected closure: Friday 22:00 UTC through Sunday 22:00 UTC
```

During expected closure, the dashboard reports:

```text
MARKET_CLOSED
Candle context retained from the last market session
```

After reopening, a completed one-minute candle must be within
`COMPLETED_CANDLE_FRESHNESS_SECONDS`, default 180 seconds. A Friday candle is
not considered fresh on Monday merely because the former three-day wall-clock
limit has not expired.

Verified state after reopening with the latest candle still at
`2026-08-14 21:58 UTC`:

```text
Live quote:       FRESH
Worker:           DEGRADED
Candle context:   STALE_AFTER_REOPEN
Overall:          DEGRADED

Live quote available, but completed candle context is stale.
```

Production prediction remains unavailable until a valid completed one-minute
candle source resumes. This is intentional safety behavior.

### 19.7 Prediction suppression and dashboard consistency

Production generation is blocked for:

- Future-dated live quote.
- Clock difference beyond configured tolerance.
- Naive or ambiguous provider timestamp.
- Stale live quote.
- Expected market closure.
- Stale candle context after reopening.
- Missing or discontinuous required candles.
- Missing or incompatible production artifacts.

Input failures are recorded as non-accepted decisions for configured horizons.
Relevant reason codes include `FUTURE_LIVE_TIMESTAMP`, `STALE_LIVE_PRICE`,
`STALE_CANDLE_CONTEXT`, `MISSING_CANDLES` and `MARKET_UNAVAILABLE`.

The header, Overview and System Health page consume the centralized
`HealthSummary` from `app/health.py`:

```text
live_quote_status
worker_status
candle_status
overall_data_status
```

A future timestamp can no longer simultaneously appear as age zero, Fresh or
Healthy. The displayed offset uses an exact human-readable value such as
`Provider timestamp is 3h 2m ahead of server UTC`.

### 19.8 Current dashboard structure

The routed Streamlit UI currently provides:

```text
Overview
Live Forecasts
Performance
Non-Accepted
Models & Training
Historical Data
System Health
Legacy Forecast
```

Shared presentation components live under `app/ui/`. The shell uses a compact
header, grouped dark navigation, common health status, consistent formatting,
readable empty states and model-scoped queries. The legacy page is separated
and labelled rather than presented as the current production model.

### 19.9 Verification status

Latest automated verification after timestamp/session corrections:

```text
Python compilation: passed
Automated test suite: 41 passed
Background worker: launchd service starts and persists valid quotes
Valid quote acceptance: verified
Future/ambiguous quote rejection: verified by regression tests
Weekend closure behavior: verified
Post-reopen stale-candle blocking: verified
Non-accepted suppression records: verified in PostgreSQL
```

The latest corrected database row was:

```text
id:              6101782
provider:        gold_api
raw timestamp:   2026-08-17T01:22:01Z
timestamp UTC:   2026-08-17T01:22:01+00:00
ingested UTC:    2026-08-17T01:22:13.921554+00:00
created UTC:     2026-08-17T01:22:13.921554+00:00
```

### 19.10 Remaining limitations and follow-up work

1. A continuous approved one-minute candle source is not currently producing
   post-reopen completed candles, so trained-model production inference is
   correctly suppressed.
2. The weekend policy is explicit but intentionally minimal. Exchange holiday
   schedules and provider-specific daily maintenance windows require an
   approved market calendar before they can be classified automatically.
3. Legacy invalid future rows remain in `prices` for traceability. Operational
   queries exclude them; a cleanup must not run without an unambiguous reviewed
   predicate.
4. Model quality must not be claimed until an approved candidate beats the
   persistence baseline on a sufficiently large untouched chronological test
   set.
5. Streamlit headless screenshot capture was intermittent because some Chrome
   sessions remained in Streamlit's loading skeleton; application route tests
   and rendered manual inspection succeeded, but a durable Playwright/Selenium
   visual regression harness remains advisable.
