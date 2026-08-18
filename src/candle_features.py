"""Single feature pipeline shared by candle training and live inference."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

import pandas as pd
import numpy as np


BASIC_FEATURE_COLUMNS = [
    "Open", "High", "Low", "Close", "SMA_7", "SMA_14", "SMA_30",
    "EMA_7", "EMA_14", "Price_Change", "Price_Change_Pct",
    "Volatility_7", "Volatility_14", "RSI_14",
    "Close_Lag_1", "Close_Lag_2", "Close_Lag_3", "Close_Lag_7",
]
FEATURE_SCHEMA_VERSION = "candle_features_v2"
MAX_FEATURE_LOOKBACK = 30
HORIZONS = (3, 5, 15, 30, 60, 240)

ADVANCED_FEATURE_COLUMNS = [
    "session_minute", "bid_ask_spread_proxy", "volatility_5", "volatility_15",
    "volatility_30", "vol_ratio_5_15", "vol_ratio_15_30", "momentum_3",
    "momentum_5", "momentum_10", "momentum_30", "z_score_5", "z_score_15",
    "z_score_30", "range_pct", "upper_shadow", "lower_shadow", "body_pct",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos", "session_open", "session_return",
]
FEATURE_COLUMNS = BASIC_FEATURE_COLUMNS + ADVANCED_FEATURE_COLUMNS


@dataclass(frozen=True)
class CandleContinuity:
    missing_periods: tuple

    @property
    def continuous(self):
        return not self.missing_periods


def candles_to_frame(candles: Sequence) -> pd.DataFrame:
    rows = [{
        "Date": c.candle_time, "Open": float(c.open_price),
        "High": float(c.high_price), "Low": float(c.low_price),
        "Close": float(c.close_price), "Volume": float(c.volume) if c.volume is not None else None,
    } for c in candles]
    return pd.DataFrame(rows).sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True) if rows else pd.DataFrame()


def detect_missing_minutes(frame: pd.DataFrame) -> CandleContinuity:
    if frame.empty or len(frame) < 2:
        return CandleContinuity(())
    times = pd.to_datetime(frame["Date"], utc=True)
    missing = []
    for previous, current in zip(times[:-1], times[1:]):
        cursor = previous + timedelta(minutes=1)
        while cursor < current:
            missing.append(cursor.to_pydatetime())
            cursor += timedelta(minutes=1)
    return CandleContinuity(tuple(missing))


def validate_ohlc(frame: pd.DataFrame) -> pd.Series:
    """Return a mask for positive, internally consistent OHLC rows."""
    return (
        (frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
        & (frame["High"] >= frame[["Open", "Close", "Low"]].max(axis=1))
        & (frame["Low"] <= frame[["Open", "Close", "High"]].min(axis=1))
    )


def add_advanced_features(df: pd.DataFrame, include_ex_post_session_features: bool = True) -> pd.DataFrame:
    """Add session, microstructure, volatility, momentum and cyclical features.

    Ex-post session progress/remaining fields are useful for completed-session
    research but are deliberately excluded by ``build_features`` because a live
    session's final length is unknowable at inference time.
    """
    result = df.copy()
    aliases = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "candle_time": "Date"}
    for lower, canonical in aliases.items():
        if canonical not in result and lower in result:
            result[canonical] = result[lower]
    required = {"Date", "Open", "High", "Low", "Close"}
    if missing := required.difference(result.columns):
        raise ValueError(f"Advanced feature input lacks columns: {sorted(missing)}")
    result["Date"] = pd.to_datetime(result["Date"], utc=True)
    result = result.sort_values("Date").reset_index(drop=True)
    if "session_id" not in result:
        result["session_id"] = result["Date"].diff().ne(pd.Timedelta(minutes=1)).cumsum().astype(int)
    grouped = result.groupby("session_id", sort=False)
    result["session_minute"] = grouped.cumcount()
    maximum_minute = grouped["session_minute"].transform("max")
    if include_ex_post_session_features:
        result["session_minute_pct"] = (result["session_minute"] / maximum_minute.replace(0, np.nan)).fillna(0)
        result["session_remaining"] = maximum_minute - result["session_minute"]
        result["session_remaining_pct"] = result["session_remaining"] / (maximum_minute + 1)
    close = result["Close"]
    result["returns"] = grouped["Close"].pct_change(fill_method=None)
    candle_range = result["High"] - result["Low"]
    safe_range = candle_range.replace(0, np.nan)
    result["bid_ask_spread_proxy"] = candle_range / close
    for window in (5, 15, 30):
        result[f"volatility_{window}"] = result.groupby("session_id")["returns"].transform(
            lambda values, size=window: values.rolling(size).std()
        )
        result[f"momentum_{window}"] = close / grouped["Close"].shift(window) - 1
        rolling_mean = grouped["Close"].transform(lambda values, size=window: values.rolling(size).mean())
        rolling_std = grouped["Close"].transform(lambda values, size=window: values.rolling(size).std())
        result[f"z_score_{window}"] = (close - rolling_mean) / rolling_std.replace(0, np.nan)
    result["momentum_3"] = close / grouped["Close"].shift(3) - 1
    result["momentum_10"] = close / grouped["Close"].shift(10) - 1
    result["vol_ratio_5_15"] = result["volatility_5"] / result["volatility_15"].replace(0, np.nan)
    result["vol_ratio_15_30"] = result["volatility_15"] / result["volatility_30"].replace(0, np.nan)
    result["range_pct"] = candle_range / close * 100
    result["upper_shadow"] = (result["High"] - result[["Open", "Close"]].max(axis=1)) / safe_range
    result["lower_shadow"] = (result[["Open", "Close"]].min(axis=1) - result["Low"]) / safe_range
    result["body_pct"] = (result["Close"] - result["Open"]).abs() / safe_range
    result["hour_sin"] = np.sin(2 * np.pi * result.Date.dt.hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * result.Date.dt.hour / 24)
    result["dow_sin"] = np.sin(2 * np.pi * result.Date.dt.dayofweek / 7)
    result["dow_cos"] = np.cos(2 * np.pi * result.Date.dt.dayofweek / 7)
    result["session_open"] = grouped["Open"].transform("first")
    prior_close = grouped["Close"].last().shift(1)
    result["session_close_prev"] = result["session_id"].map(prior_close)
    result["session_return"] = close / result["session_open"] - 1
    return result.replace([np.inf, -np.inf], np.nan)


def select_features(df: pd.DataFrame, target: str, max_features: int = 50) -> list[str]:
    """Rank finite numeric features with mutual information without imputing from the future."""
    from sklearn.feature_selection import mutual_info_regression
    if target not in df:
        raise ValueError(f"Unknown target column: {target}")
    numeric = df.select_dtypes(include=[np.number]).drop(columns=[target], errors="ignore")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna(axis=1, how="all")
    usable = pd.concat([numeric, pd.to_numeric(df[target], errors="coerce").rename(target)], axis=1).dropna()
    if usable.empty or numeric.empty:
        return []
    importance = mutual_info_regression(usable[numeric.columns], usable[target], random_state=42)
    return pd.Series(importance, index=numeric.columns).nlargest(min(max_features, len(numeric.columns))).index.tolist()


def create_chronological_folds(df: pd.DataFrame, num_folds: int = 5):
    if num_folds < 2 or len(df) < num_folds:
        raise ValueError("Not enough rows for the requested chronological folds")
    ordered = df.sort_values("Date") if "Date" in df else df.copy()
    indexes = np.array_split(np.arange(len(ordered)), num_folds)
    return [(ordered.iloc[:chunk[0]].copy(), ordered.iloc[chunk].copy()) for chunk in indexes[1:] if len(chunk)]


def test_feature_stability(df: pd.DataFrame, feature_list, num_folds: int = 5) -> dict:
    """Summarize distribution drift across non-overlapping chronological test folds."""
    folds = create_chronological_folds(df, num_folds)
    results = {}
    for feature in feature_list:
        if feature not in df:
            raise ValueError(f"Unknown feature: {feature}")
        stats = [{"mean": test[feature].mean(), "std": test[feature].std(),
                  "min": test[feature].min(), "max": test[feature].max()} for _, test in folds]
        means = np.asarray([item["mean"] for item in stats], dtype=float)
        mean = float(np.nanmean(means))
        results[feature] = {"mean_of_means": mean, "std_of_means": float(np.nanstd(means)),
                            "cv_of_means": float(np.nanstd(means) / abs(mean)) if mean else 999.0,
                            "fold_stats": stats}
    return results


def build_features(frame: pd.DataFrame, include_target: bool = False) -> pd.DataFrame:
    """Create the versioned, causal feature set shared by training and inference."""
    result = frame.copy().sort_values("Date").drop_duplicates("Date", keep="last")
    result["Date"] = pd.to_datetime(result["Date"], utc=True)
    result = result.loc[validate_ohlc(result)].copy()
    # Reset every stateful indicator after any missing minute. This prevents
    # rolling, lagged, and exponentially weighted values from bridging closures.
    result["_continuity_segment"] = result["Date"].diff().ne(pd.Timedelta(minutes=1)).cumsum()
    grouped_close = result.groupby("_continuity_segment", sort=False)["Close"]
    result["SMA_7"] = grouped_close.transform(lambda values: values.rolling(7).mean())
    result["SMA_14"] = grouped_close.transform(lambda values: values.rolling(14).mean())
    result["SMA_30"] = grouped_close.transform(lambda values: values.rolling(30).mean())
    result["EMA_7"] = grouped_close.transform(lambda values: values.ewm(span=7, adjust=False).mean())
    result["EMA_14"] = grouped_close.transform(lambda values: values.ewm(span=14, adjust=False).mean())
    result["Price_Change"] = grouped_close.diff()
    result["Price_Change_Pct"] = grouped_close.pct_change(fill_method=None) * 100
    result["Volatility_7"] = grouped_close.transform(lambda values: values.rolling(7).std())
    result["Volatility_14"] = grouped_close.transform(lambda values: values.rolling(14).std())
    delta = grouped_close.diff()
    gain = delta.clip(lower=0).groupby(result["_continuity_segment"]).transform(
        lambda values: values.rolling(14).mean()
    )
    loss = (-delta.clip(upper=0)).groupby(result["_continuity_segment"]).transform(
        lambda values: values.rolling(14).mean()
    )
    result["RSI_14"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))
    for lag in (1, 2, 3, 7):
        result[f"Close_Lag_{lag}"] = grouped_close.shift(lag)
    if include_target:
        raise ValueError("Use build_horizon_dataset(); next-row targets are prohibited")
    result = add_advanced_features(result, include_ex_post_session_features=False)
    required = FEATURE_COLUMNS
    return result.dropna(subset=required).drop(columns=["_continuity_segment", "session_id"]).reset_index(drop=True)


def build_horizon_dataset(frame: pd.DataFrame, horizon_minutes: int) -> pd.DataFrame:
    """Build direct-return labels only where exact target and continuous context exist."""
    if horizon_minutes not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon_minutes}")
    ordered = frame.copy().sort_values("Date").drop_duplicates("Date", keep="last")
    ordered["Date"] = pd.to_datetime(ordered["Date"], utc=True)
    ordered = ordered.loc[validate_ohlc(ordered)].copy()
    features = build_features(ordered)
    # Model-target sessions are deliberately stricter than the persisted market
    # sessions: any missing minute starts a new target-continuity segment.
    from src.session_builder import build_sessions, assert_targets_within_sessions

    strict_sessions = build_sessions(ordered, gap_threshold_minutes=2)
    session_map = pd.concat(strict_sessions, ignore_index=True)[["Date", "session_id"]]
    ordered = ordered.merge(session_map, on="Date", how="left", validate="one_to_one")
    features = features.merge(
        ordered[["Date", "session_id"]], on="Date", how="left", validate="one_to_one"
    )
    close_lookup = ordered.set_index("Date")["Close"]
    features["target_time"] = features["Date"] + pd.Timedelta(minutes=horizon_minutes)
    features["target_close"] = features["target_time"].map(close_lookup)
    target_sessions = features["target_time"].map(ordered.set_index("Date")["session_id"])
    features["target_session_id"] = target_sessions
    features["horizon_minutes"] = horizon_minutes
    features["target_return"] = (features["target_close"] - features["Close"]) / features["Close"]
    exact_target = features["target_close"].notna()
    context_valid = features["session_minute"] >= MAX_FEATURE_LOOKBACK - 1
    same_session = target_sessions.eq(features["session_id"])
    valid = (
        exact_target & context_valid & same_session
    )
    features["target_status"] = "eligible"
    features.loc[~same_session | ~exact_target, "target_status"] = "session_end"
    result = features.loc[valid].reset_index(drop=True)
    assert_targets_within_sessions(result)
    result.attrs["diagnostics"] = {
        "feature_rows": int(len(features)),
        "retained_rows": int(valid.sum()),
        "missing_exact_target_rows": int((~exact_target).sum()),
        "gap_rejected_rows": int((exact_target & (~context_valid | ~same_session)).sum()),
        "session_end_rows": int((~same_session | ~exact_target).sum()),
    }
    return result


def latest_continuous_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Return one inference row only when the latest feature context is continuous."""
    ordered = frame.copy().sort_values("Date").drop_duplicates("Date", keep="last")
    if len(ordered) < MAX_FEATURE_LOOKBACK:
        return pd.DataFrame(), f"Need at least {MAX_FEATURE_LOOKBACK} completed candles"
    recent = ordered.tail(MAX_FEATURE_LOOKBACK)
    if not validate_ohlc(recent).all():
        return pd.DataFrame(), "Recent feature window contains invalid OHLC values"
    times = pd.to_datetime(recent["Date"], utc=True)
    if not times.diff().dropna().eq(pd.Timedelta(minutes=1)).all():
        return pd.DataFrame(), "Recent feature window is discontinuous"
    built = build_features(ordered)
    if built.empty or pd.Timestamp(built.iloc[-1]["Date"]) != times.iloc[-1]:
        return pd.DataFrame(), "Latest candle cannot produce the approved feature schema"
    return built.tail(1), None
