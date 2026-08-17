import streamlit as st

TOKENS = {
    "gold": "#C89B3C", "primary": "#2563EB", "secondary": "#64748B", "success": "#16865B",
    "warning": "#D97706", "error": "#DC2626", "neutral": "#64748B",
    "background": "#F6F8FB", "surface": "#FFFFFF", "text": "#0F172A",
    "muted": "#64748B", "border": "#E2E8F0", "radius": "12px",
}
CHART_COLORS = ["#C89B3C", "#2563EB", "#16865B", "#DC2626", "#94A3B8"]


def apply_theme():
    if not st.session_state.get("_gpi_page_configured"):
        st.set_page_config(page_title="Gold Price Intelligence", page_icon="◉", layout="wide")
        st.session_state._gpi_page_configured = True
    st.markdown(f"""
    <style>
    html, body, [class*="css"] {{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}}
    .stApp {{background:{TOKENS['background']}; color:{TOKENS['text']};}}
    .block-container {{max-width:1540px; padding-top:.55rem; padding-bottom:1.5rem;}}
    [data-testid="stSidebar"] {{background:#0F172A; min-width:240px; max-width:240px;}}
    [data-testid="stSidebar"] * {{color:#CBD5E1;}}
    [data-testid="stSidebarNav"] span {{white-space:normal!important; line-height:1.25!important;}}
    [data-testid="stSidebarNavLink"] {{border-radius:8px; min-height:38px;}}
    [data-testid="stSidebarNavLink"][aria-current="page"] {{background:#1E293B!important;}}
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"], [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{justify-content:flex-start;border:0;border-radius:8px;min-height:38px;padding-left:12px;font-weight:550;box-shadow:none}}
    [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{background:transparent;color:#CBD5E1}}
    [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {{background:#1E293B;color:#FFFFFF}}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{margin-top:10px;color:#64748B!important;font-size:11px;font-weight:750;letter-spacing:.05em}}
    [data-testid="stSidebarHeader"] {{height:2.8rem;}}
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {{display:none!important;}}
    h1 {{font-size:1.75rem!important; letter-spacing:-.02em;}}
    h2 {{font-size:1.25rem!important; margin-top:1.5rem!important;}}
    h3 {{font-size:1rem!important;}}
    [data-testid="stMetric"] {{background:{TOKENS['surface']}; border:1px solid {TOKENS['border']}; border-radius:{TOKENS['radius']}; padding:12px 14px; box-shadow:0 1px 2px rgba(15,23,42,.03);}}
    [data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {{background:{TOKENS['surface']}; border-color:{TOKENS['border']}!important; border-radius:{TOKENS['radius']};}}
    .gpi-badge {{display:inline-flex;align-items:center;padding:3px 9px;border-radius:999px;font-size:.75rem;font-weight:700;border:1px solid {TOKENS['border']};background:#F1F5F9;color:{TOKENS['text']};}}
    .gpi-topbar {{height:78px;background:#fff;border:1px solid {TOKENS['border']};border-radius:12px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:.55rem;box-shadow:0 1px 2px rgba(15,23,42,.03)}}
    .gpi-brand-title {{font-size:15px;font-weight:750;color:#0F172A}} .gpi-brand-sub {{font-size:12px;color:#64748B;margin-top:2px}}
    .gpi-quote {{font-size:26px;font-weight:750;letter-spacing:-.02em;color:#0F172A}} .gpi-meta {{font-size:12px;color:#64748B}}
    .gpi-page-heading {{display:flex;justify-content:space-between;align-items:end;margin:.65rem 0 .8rem}} .gpi-page-heading h1 {{margin:0!important}} .gpi-page-heading p{{margin:.15rem 0 0;color:#64748B;font-size:13px}}
    .gpi-kpi {{height:132px;background:#fff;border:1px solid {TOKENS['border']};border-radius:12px;padding:15px 16px;box-sizing:border-box;box-shadow:0 1px 2px rgba(15,23,42,.03)}}
    .gpi-kpi-label {{font-size:12px;color:#64748B;font-weight:650;text-transform:uppercase;letter-spacing:.03em}} .gpi-kpi-value {{font-size:27px;color:#0F172A;font-weight:750;letter-spacing:-.025em;margin:8px 0 4px}} .gpi-kpi-detail{{font-size:12px;color:#64748B;line-height:1.35}}
    .gpi-section-title{{font-size:15px;font-weight:750;color:#0F172A;margin:0}} .gpi-section-caption{{font-size:12px;color:#64748B;margin-top:2px}}
    .gpi-empty{{min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:22px;background:#fff;border:1px dashed #CBD5E1;border-radius:12px}} .gpi-empty strong{{font-size:16px;color:#0F172A}} .gpi-empty span{{font-size:13px;color:#64748B;max-width:360px;margin-top:7px}}
    .gpi-sidebar-brand{{padding:8px 8px 16px;color:#fff!important;font-weight:750;font-size:15px;border-bottom:1px solid #1E293B;margin-bottom:10px}} .gpi-sidebar-brand small{{display:block;color:#94A3B8!important;font-weight:500;margin-top:3px}}
    [data-testid="stSidebarContent"], [data-testid="stSidebarUserContent"] {{background:#0F172A!important;}}
    .gpi-footer {{margin-top:2.5rem;padding:1rem 0;border-top:1px solid {TOKENS['border']};color:{TOKENS['muted']};font-size:.78rem;}}
    @media(max-width:780px) {{.block-container{{padding:.35rem .7rem 1rem}} h1{{font-size:1.4rem!important}} .gpi-topbar{{height:auto;min-height:68px;padding:10px;flex-wrap:wrap}} .gpi-quote{{font-size:21px}} .gpi-kpi{{height:118px}}}}
    </style>""", unsafe_allow_html=True)
