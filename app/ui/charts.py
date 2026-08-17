import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from html import escape
from app.ui.theme import CHART_COLORS


def style_figure(figure, height=390):
    if figure is None: return None
    figure.update_layout(height=height, margin={"l":18,"r":18,"t":52,"b":28}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF", font={"family":"Inter, sans-serif","color":"#475569","size":12}, hovermode="x unified", legend={"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"left","x":0}, legend_title=None)
    figure.update_xaxes(showgrid=False, zeroline=False)
    figure.update_yaxes(gridcolor="#E2E8F0", zeroline=False)
    return figure


def line(frame, x, y, color=None, title=None, markers=False, **kwargs):
    if frame is None or frame.empty or y not in frame:
        return None
    clean = frame.copy()
    clean[y] = pd.to_numeric(clean[y], errors="coerce")
    clean[x] = pd.to_datetime(clean[x], utc=True, errors="coerce")
    clean = clean.dropna(subset=[x, y]).sort_values(x)
    if clean.empty: return None
    return style_figure(px.line(clean, x=x, y=y, color=color, markers=markers, title=title,
                   color_discrete_sequence=CHART_COLORS, **kwargs))


def comparison_figure(frame):
    if frame is None or frame.empty: return None
    figure = go.Figure()
    for column, label, color, dash in (
        ("actual_price", "Actual", CHART_COLORS[2], "solid"),
        ("viewing_predicted_price", "Viewing model", CHART_COLORS[0], "solid"),
        ("comparison_predicted_price", "Comparison model", CHART_COLORS[1], "dot"),
        ("baseline_price", "Persistence baseline", CHART_COLORS[4], "dash"),
    ):
        if column in frame and frame[column].notna().any():
            figure.add_scatter(x=frame.target_at, y=frame[column], name=label, mode="lines+markers", connectgaps=False, line={"color":color,"dash":dash})
    figure.update_layout(title="Actual vs prediction")
    return style_figure(figure)


def market_svg(frame, prediction=None, baseline=None):
    """Fast, responsive overview sparkline that does not depend on an iframe."""
    if frame is None or frame.empty or "actual_price" not in frame: return None
    values=pd.to_numeric(frame.actual_price,errors="coerce").dropna().tail(240)
    if len(values)<2: return None
    low,high=float(values.min()),float(values.max()); span=max(high-low,.01)
    points=[]
    for index,value in enumerate(values):
        x=36+(index/(len(values)-1))*864; y=270-((float(value)-low)/span)*210
        points.append(f"{x:.1f},{y:.1f}")
    marker=""
    if prediction is not None:
        py=270-((float(prediction)-low)/span)*210
        marker+=f'<circle cx="900" cy="{py:.1f}" r="6" fill="#C89B3C"/><text x="820" y="{max(18,py-12):.1f}" fill="#64748B" font-size="11">Forecast</text>'
    if baseline is not None:
        by=270-((float(baseline)-low)/span)*210
        marker+=f'<line x1="36" x2="900" y1="{by:.1f}" y2="{by:.1f}" stroke="#94A3B8" stroke-dasharray="5 5"/><text x="38" y="{max(15,by-6):.1f}" fill="#64748B" font-size="10">Persistence</text>'
    return f'''<div style="background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:14px;height:350px;box-sizing:border-box"><div class="gpi-section-title">Actual vs prediction</div><div class="gpi-section-caption">Recent live snapshots · gaps are not interpolated</div><svg viewBox="0 0 936 300" width="100%" height="290" role="img" aria-label="Actual gold price and selected forecast"><line x1="36" x2="900" y1="270" y2="270" stroke="#E2E8F0"/><line x1="36" x2="900" y1="165" y2="165" stroke="#E2E8F0"/><line x1="36" x2="900" y1="60" y2="60" stroke="#E2E8F0"/><polyline points="{' '.join(points)}" fill="none" stroke="#0F172A" stroke-width="2.5" stroke-linejoin="round"/>{marker}<text x="36" y="292" fill="#64748B" font-size="10">Actual price</text></svg></div>'''
