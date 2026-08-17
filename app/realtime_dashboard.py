"""Deprecated standalone entry point retained for bookmarks and traceability."""

import streamlit as st

from app.dashboard_pages import render_live_predictions

st.warning(
    "This standalone dashboard is deprecated. It now renders the same approved "
    "trained-model view as /live-predictions and never runs legacy adaptive forecasts."
)
render_live_predictions()
