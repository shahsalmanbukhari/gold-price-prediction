from datetime import datetime, timezone
import streamlit as st
from config.settings import get_settings
from app.dashboard_data import _production_manifest, latest_market
from app.ui.formatting import datetime_text


def render_footer(meta=None):
    try: live,_,_,health=latest_market()
    except Exception: live,health=None,"UNKNOWN"
    manifest=_production_manifest()
    production=manifest.get("model_version") if manifest else "No approved production model"
    st.markdown(f"""<div class="gpi-footer">
    Data provider: {getattr(live,'provider',None) or '—'} &nbsp;·&nbsp;
    Latest data: {datetime_text(getattr(live,'timestamp',None))} &nbsp;·&nbsp;
    Production: {production} &nbsp;·&nbsp; Worker: {health} &nbsp;·&nbsp;
    App: dashboard-v2 &nbsp;·&nbsp; Refreshed: {datetime_text(datetime.now(timezone.utc))}<br/>
    Forecasts are analytical estimates, not guaranteed trading outcomes or financial advice.
    </div>""",unsafe_allow_html=True)
