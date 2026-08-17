import streamlit as st


def empty(title, detail):
    render_empty_state(title, detail)


def render_empty_state(title, detail, action_label=None, action_page=None):
    from html import escape
    st.markdown(f'<div class="gpi-empty"><strong>{escape(title)}</strong><span>{escape(detail)}</span></div>', unsafe_allow_html=True)
    if action_label and action_page:
        st.page_link(action_page, label=action_label)


def data_error(exc):
    st.error("Dashboard data is temporarily unavailable. The background worker is unaffected.")
    st.caption(str(exc))
