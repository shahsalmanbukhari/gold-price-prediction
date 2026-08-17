from datetime import datetime, timedelta, timezone
from html import escape
import streamlit as st

from app.dashboard_data import HORIZONS, latest_market, model_options
from app.health import compute_health
from app.ui.cards import render_status_badge
from app.ui.formatting import datetime_text, price
from config.settings import get_settings


def compact_model_label(option):
    name = option.model_name.replace("_", " ").title()
    if "adaptive momentum" in name.lower(): name = "Adaptive Momentum"
    return f"{name} · {option.status.title()} · {option.horizon}m"


def render_sidebar_brand():
    st.sidebar.markdown('<div class="gpi-sidebar-brand">◆ Gold Price Intelligence<small>XAU/USD intelligence</small></div>', unsafe_allow_html=True)


def render_app_header():
    # Retained for backward-compatible page query defaults; it is intentionally
    # not a permanent global control because most pages do not use it.
    st.session_state.setdefault("selected_date_range", "30 days")
    try:
        live, candle, heartbeat, _ = latest_market()
        health = compute_health(live, candle, heartbeat, get_settings())
    except Exception:
        live = candle = heartbeat = None
        health = compute_health(None, None, None, get_settings())

    quote_status = health.live_quote_status.replace("INVALID_FUTURE_TIMESTAMP", "INVALID TIMESTAMP")
    controls = st.columns([1.25, 1.25, .75, 1.8, .35, .35], vertical_alignment="center")
    controls[0].markdown('<div class="gpi-brand-title">Gold Price Intelligence</div><div class="gpi-brand-sub">XAU/USD intelligence</div>', unsafe_allow_html=True)
    controls[1].markdown(f'<div class="gpi-quote">{price(getattr(live,"price_usd",None))}</div><div class="gpi-meta">{render_status_badge(quote_status)} · {escape(getattr(live,"provider",None) or "No provider")}</div>', unsafe_allow_html=True)
    current_horizon = st.session_state.get("selected_horizon", 15)
    horizon = controls[2].selectbox("Horizon", HORIZONS, index=HORIZONS.index(current_horizon) if current_horizon in HORIZONS else 2, format_func=lambda x: {60:"1 hour",240:"4 hours"}.get(x,f"{x} min"), key="selected_horizon")
    options = model_options(horizon)
    by_key = {item.key:item for item in options}
    keys = list(by_key)
    current = st.session_state.get("selected_model_key")
    if current not in keys: current = keys[0] if keys else None
    selected_key = controls[3].selectbox("Viewing model  ⓘ", keys, index=keys.index(current) if current in keys else 0, format_func=lambda key:compact_model_label(by_key[key]), key="selected_model_key") if keys else None
    with controls[4].popover("＋", help="Compare model"):
        comparison_keys=["NONE",*keys]
        if st.session_state.get("comparison_model_key") not in comparison_keys: st.session_state.comparison_model_key="NONE"
        comparison=st.selectbox("Compare with", comparison_keys, format_func=lambda key:"No comparison" if key=="NONE" else compact_model_label(by_key[key]), key="comparison_model_key")
    if controls[5].button("↻", help=f"Refresh data · Worker {health.worker_status}", use_container_width=True): st.rerun()
    selected=by_key.get(selected_key); compared=by_key.get(st.session_state.get("comparison_model_key"))
    if selected:
        st.session_state.selected_model_name=selected.model_name; st.session_state.selected_model_version=selected.model_version
    st.session_state.comparison_model_name=compared.model_name if compared else None
    st.session_state.comparison_model_version=compared.model_version if compared else None
    now=datetime.now(timezone.utc)
    return {"model_name":selected.model_name if selected else None,"model_version":selected.model_version if selected else None,
            "model_status":selected.status if selected else None,"comparison_name":compared.model_name if compared else None,
            "comparison_version":compared.model_version if compared else None,"horizon":horizon,
            "date_from":now-timedelta(days=30),"date_to":now,"live":live,"candle":candle,
            "heartbeat":heartbeat,"health":health,"worker_status":health.worker_status}


render_header = render_app_header
