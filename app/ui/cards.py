import streamlit as st
from html import escape

STATUS_ICON = {"RUNNING":"●", "TRUSTED":"✓", "PRODUCTION":"✓", "PENDING":"◷", "PROBATION":"◷", "DEGRADED":"!", "REJECTED":"×", "FAILED":"×", "STOPPED":"○", "LEGACY":"◇", "BASELINE":"—", "CANDIDATE":"◆", "SUPPRESSED":"!", "ACCEPTED":"✓", "EVALUATED":"✓", "UNRESOLVABLE":"×"}


def badge(status):
    value = str(status or "UNKNOWN").upper()
    return f"{STATUS_ICON.get(value, '•')} {value}"


def render_status_badge(status):
    value = str(status or "UNKNOWN").upper()
    tone = "success" if value in {"HEALTHY","RUNNING","FRESH","CURRENT","TRUSTED","PRODUCTION","EVALUATED","ACCEPTED"} else "danger" if value in {"INVALID","INVALID_FUTURE_TIMESTAMP","FAILED","OFFLINE","UNRESOLVABLE"} else "warning" if value in {"WARNING","DEGRADED","STALE","REJECTED","SUPPRESSED","PROBATION"} else "neutral"
    colors={"success":("#EAF7F1","#16865B"),"warning":("#FFF7E8","#B45309"),"danger":("#FEF0F0","#DC2626"),"neutral":("#F1F5F9","#64748B")}[tone]
    return f'<span class="gpi-badge" style="background:{colors[0]};color:{colors[1]};border-color:{colors[0]}">{escape(badge(value))}</span>'


def render_model_badge(status):
    return render_status_badge(status)


def render_kpi_card(label, value, detail="", status=None):
    status_html = f'<div style="margin-top:6px">{render_status_badge(status)}</div>' if status else ""
    st.markdown(f'<div class="gpi-kpi"><div class="gpi-kpi-label">{escape(str(label))}</div><div class="gpi-kpi-value">{escape(str(value))}</div><div class="gpi-kpi-detail">{escape(str(detail))}</div>{status_html}</div>', unsafe_allow_html=True)


def render_forecast_card(title, value, detail, status=None):
    render_kpi_card(title, value, detail, status)


def render_health_summary(summary):
    st.markdown(render_status_badge(summary.overall_data_status), unsafe_allow_html=True)
    st.caption(" · ".join([summary.live_detail, summary.candle_detail, summary.worker_detail]))


def metric_row(items, columns=4):
    for start in range(0, len(items), columns):
        cells = st.columns(min(columns, len(items)-start))
        for cell, item in zip(cells, items[start:start+columns]):
            cell.metric(item[0], item[1], item[2] if len(item) > 2 else None, help=item[3] if len(item) > 3 else None)


def section(title, caption=None):
    st.subheader(title)
    if caption: st.caption(caption)


def render_section_header(title, caption=None):
    st.markdown(f'<div style="margin:1.1rem 0 .55rem"><div class="gpi-section-title">{escape(title)}</div>{f"<div class=\"gpi-section-caption\">{escape(caption)}</div>" if caption else ""}</div>', unsafe_allow_html=True)
