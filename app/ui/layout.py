import streamlit as st
from app.ui.theme import apply_theme
from app.ui.header import render_app_header
from app.ui.footer import render_footer


def page(title, subtitle=None):
    apply_theme()
    context = render_app_header()
    render_page_heading(title, subtitle, context["health"].overall_data_status)
    return context


def render_page_heading(title, subtitle=None, status=None):
    from html import escape
    from datetime import datetime, timezone
    from app.ui.cards import render_status_badge
    st.markdown(f'<div class="gpi-page-heading"><div><h1>{escape(title)}</h1><p>{escape(subtitle or "")}</p></div><div style="text-align:right"><div>{render_status_badge(status)}</div><div class="gpi-meta" style="margin-top:5px">Last updated {datetime.now(timezone.utc).strftime("%H:%M UTC")}</div></div></div>', unsafe_allow_html=True)


def finish(meta=None):
    render_footer(meta)
