"""Single feature pipeline shared by candle training and live inference."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

import pandas as pd


FEATURE_COLUMNS = [
    "Open", "High", "Low", "Close", "SMA_7", "SMA_14", "SMA_30",
    "EMA_7", "EMA_14", "Price_Change", "Price_Change_Pct",
    "Volatility_7", "Volatility_14", "RSI_14",
    "Close_Lag_1", "Close_Lag_2", "Close_Lag_3", "Close_Lag_7",
]
FEATURE_SCHEMA_VERSION = "candle_features_v1"
MAX_FEATURE_LOOKBACK = 30
HORIZONS = (3, 5, 15, 30, 60, 240)


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


def build_features(frame: pd.DataFrame, include_target: bool = False) -> pd.DataFrame:
    """Create the versioned, causal feature set shared by training and inference."""
    result = frame.copy().sort_values("Date").drop_duplicates("Date", keep="last")
    result["Date"] = pd.to_datetime(result["Date"], utc=True)
    result = result.loc[validate_ohlc(result)].copy()
    close = result["Close"]
    result["SMA_7"] = close.rolling(7).mean()
    result["SMA_14"] = close.rolling(14).mean()
    result["SMA_30"] = close.rolling(30).mean()
    result["EMA_7"] = close.ewm(span=7, adjust=False).mean()
    result["EMA_14"] = close.ewm(span=14, adjust=False).mean()
    result["Price_Change"] = close.diff()
    result["Price_Change_Pct"] = close.pct_change() * 100
    result["Volatility_7"] = close.rolling(7).std()
    result["Volatility_14"] = close.rolling(14).std()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    result["RSI_14"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))
    for lag in (1, 2, 3, 7):
        result[f"Close_Lag_{lag}"] = close.shift(lag)
    if include_target:
        raise ValueError("Use build_horizon_dataset(); next-row targets are prohibited")
    required = FEATURE_COLUMNS
    return result.dropna(subset=required).reset_index(drop=True)


def build_horizon_dataset(frame: pd.DataFrame, horizon_minutes: int) -> pd.DataFrame:
    """Build direct-return labels only where exact target and continuous context exist."""
    if horizon_minutes not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon_minutes}")
    ordered = frame.copy().sort_values("Date").drop_duplicates("Date", keep="last")
    ordered["Date"] = pd.to_datetime(ordered["Date"], utc=True)
    ordered = ordered.loc[validate_ohlc(ordered)].copy()
    features = build_features(ordered)
    # A session starts after every non-one-minute interval. rolling position
    # ensures indicators/lags never bridge a closure or missing-data gap.
    discontinuity = ordered["Date"].diff().ne(pd.Timedelta(minutes=1))
    ordered["_session"] = discontinuity.cumsum()
    ordered["_session_position"] = ordered.groupby("_session").cumcount()
    features = features.merge(
        ordered[["Date", "_session", "_session_position"]], on="Date", how="left", validate="one_to_one"
    )
    close_lookup = ordered.set_index("Date")["Close"]
    features["target_time"] = features["Date"] + pd.Timedelta(minutes=horizon_minutes)
    features["target_close"] = features["target_time"].map(close_lookup)
    target_sessions = features["target_time"].map(ordered.set_index("Date")["_session"])
    features["target_return"] = (features["target_close"] - features["Close"]) / features["Close"]
    exact_target = features["target_close"].notna()
    context_valid = features["_session_position"] >= MAX_FEATURE_LOOKBACK - 1
    same_session = target_sessions.eq(features["_session"])
    valid = (
        exact_target & context_valid & same_session
    )
    result = features.loc[valid].drop(columns=["_session", "_session_position"]).reset_index(drop=True)
    result.attrs["diagnostics"] = {
        "feature_rows": int(len(features)),
        "retained_rows": int(valid.sum()),
        "missing_exact_target_rows": int((~exact_target).sum()),
        "gap_rejected_rows": int((exact_target & (~context_valid | ~same_session)).sum()),
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
