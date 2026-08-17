"""Stable query-parameter router for the Streamlit application shell."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from app.ui.theme import apply_theme
from app.ui.header import render_sidebar_brand

apply_theme()
render_sidebar_brand()

ROUTES = {
    "overview": ("Overview", "▦", "MONITOR"),
    "live-forecasts": ("Live Forecasts", "⌁", "MONITOR"),
    "performance": ("Performance", "⌁", "MONITOR"),
    "non-accepted": ("Non-Accepted", "⊘", "MONITOR"),
    "models-training": ("Models & Training", "◇", "MODELS & DATA"),
    "historical-data": ("Historical Data", "▤", "MODELS & DATA"),
    "system-health": ("System Health", "◉", "SYSTEM"),
    "legacy": ("Legacy Forecast", "◇", "LEGACY"),
}

requested = st.query_params.get("page", "overview")
current = requested if requested in ROUTES else "overview"
for group in ("MONITOR", "MODELS & DATA", "SYSTEM", "LEGACY"):
    st.sidebar.caption(group)
    for route, (label, icon, item_group) in ROUTES.items():
        if item_group != group: continue
        if st.sidebar.button(f"{icon}  {label}", key=f"nav_{route}", use_container_width=True,
                             type="primary" if route == current else "secondary"):
            st.query_params["page"] = route
            st.rerun()

if current == "legacy":
    import app.streamlit_app  # explicitly labelled legacy UI
else:
    from app import pages
    {
        "overview": pages.overview,
        "live-forecasts": pages.live_forecasts,
        "performance": pages.performance,
        "non-accepted": pages.non_accepted,
        "models-training": pages.models_training,
        "historical-data": pages.historical_data,
        "system-health": pages.system_health,
    }[current]()
