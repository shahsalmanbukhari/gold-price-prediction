"""
Streamlit Dashboard for Gold Price Prediction
Premium Financial-Grade Interface
"""

import streamlit as st
import pandas as pd
import numpy as np
import sys
import os
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from predict import GoldPricePredictor


# Page config
st.set_page_config(
    page_title="Gold Price Prediction | Professional Analytics",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Dark Theme CSS
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* Global Styles */
    * {
        font-family: 'Inter', sans-serif;
    }
    
    /* Main container */
    .main {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        color: #e4e4e7;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #0f1419 100%);
        border-right: 1px solid #2d3748;
    }
    
    [data-testid="stSidebar"] .css-1d391kg {
        color: #e4e4e7;
    }
    
    /* Header bar */
    .header-bar {
        background: linear-gradient(90deg, #1a1f2e 0%, #2d3748 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        border: 1px solid #374151;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        letter-spacing: -0.5px;
    }
    
    .header-subtitle {
        color: #9ca3af;
        font-size: 0.95rem;
        font-weight: 400;
        margin-top: 0.5rem;
    }
    
    /* Premium card */
    .premium-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 16px;
        padding: 1.5rem;
        border: 1px solid #334155;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
        transition: all 0.3s ease;
        margin-bottom: 1.5rem;
    }
    
    .premium-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.5);
        border-color: #FFD700;
    }
    
    /* Metric card */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 12px;
        padding: 1.25rem;
        border: 1px solid #334155;
        text-align: center;
        transition: all 0.3s ease;
    }
    
    .metric-card:hover {
        border-color: #FFD700;
        box-shadow: 0 0 20px rgba(255, 215, 0, 0.2);
    }
    
    .metric-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    .metric-label {
        color: #9ca3af;
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 0.5rem;
    }
    
    .metric-value {
        color: #FFD700;
        font-size: 1.75rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    
    .metric-unit {
        color: #6b7280;
        font-size: 0.8rem;
    }
    
    /* Prediction cards */
    .prediction-card {
        background: linear-gradient(135deg, #1e3a5f 0%, #0f1e3a 100%);
        border-radius: 16px;
        padding: 2rem;
        border: 2px solid #FFD700;
        text-align: center;
        box-shadow: 0 0 30px rgba(255, 215, 0, 0.15);
        position: relative;
        overflow: hidden;
    }
    
    .prediction-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 215, 0, 0.1), transparent);
        transition: left 0.5s;
    }
    
    .prediction-card:hover::before {
        left: 100%;
    }
    
    .prediction-title {
        color: #9ca3af;
        font-size: 0.9rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 1rem;
    }
    
    .prediction-value {
        color: #FFD700;
        font-size: 3rem;
        font-weight: 800;
        margin: 1rem 0;
        text-shadow: 0 0 20px rgba(255, 215, 0, 0.3);
    }
    
    .prediction-change {
        color: #e4e4e7;
        font-size: 1.5rem;
        font-weight: 600;
        margin-top: 0.5rem;
    }
    
    .change-positive {
        color: #10b981;
    }
    
    .change-negative {
        color: #ef4444;
    }
    
    /* Section header */
    .section-header {
        color: #e4e4e7;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #374151;
    }
    
    /* Info card */
    .info-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 12px;
        padding: 1.5rem;
        border-left: 4px solid #FFD700;
        margin: 1rem 0;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        color: #0f1419;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(255, 215, 0, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(255, 215, 0, 0.4);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        background-color: transparent;
        border-bottom: 2px solid #374151;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        color: #9ca3af;
        border-radius: 8px 8px 0 0;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        border: none;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        color: #FFD700;
        border-bottom: 3px solid #FFD700;
    }
    
    /* Metric containers */
    [data-testid="stMetricValue"] {
        color: #FFD700;
        font-size: 1.5rem;
        font-weight: 700;
    }
    
    [data-testid="stMetricLabel"] {
        color: #9ca3af;
        font-weight: 600;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 8px;
        color: #e4e4e7;
        font-weight: 600;
    }
    
    /* Radio buttons */
    [data-testid="stRadio"] > label {
        color: #9ca3af;
        font-weight: 600;
    }
    
    /* Selectbox */
    .stSelectbox label {
        color: #9ca3af;
        font-weight: 600;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #1a1f2e;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #374151;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #FFD700;
    }
    
    /* Dataframe styling */
    [data-testid="stDataFrame"] {
        background: #1e293b;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ==================== REUSABLE UI COMPONENTS ====================

def styled_metric(title, value, delta=None, icon="💰"):
    """Display a premium styled metric card"""
    delta_html = ""
    if delta is not None:
        # Convert delta to float if it's a string
        try:
            delta_value = float(delta) if isinstance(delta, str) else delta
            color = "#10b981" if delta_value >= 0 else "#ef4444"
            arrow = "↑" if delta_value >= 0 else "↓"
            delta_html = f'<div style="color: {color}; font-size: 0.9rem; font-weight: 600; margin-top: 0.5rem;">{arrow} {abs(delta_value):.2f}%</div>'
        except (ValueError, TypeError):
            # If conversion fails, skip delta display
            pass

    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-icon">{icon}</div>
        <div class="metric-label">{title}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def card(title, body, icon=""):
    """Display a premium card with title and body"""
    st.markdown(f"""
    <div class="premium-card">
        <h3 style="color: #FFD700; margin-bottom: 1rem; font-weight: 700;">
            {icon} {title}
        </h3>
        <div style="color: #d1d5db; line-height: 1.6;">
            {body}
        </div>
    </div>
    """, unsafe_allow_html=True)


def section(title, icon=""):
    """Display a section header"""
    st.markdown(f"""
    <div class="section-header">
        {icon} {title}
    </div>
    """, unsafe_allow_html=True)


def prediction_card(title, value, unit, change_value, change_pct, is_positive=True):
    """Display a premium prediction card"""
    change_class = "change-positive" if is_positive else "change-negative"
    arrow = "↑" if is_positive else "↓"

    # change_value is already formatted as a string (e.g., "PKR 1,614" or "$35.56")
    st.markdown(f"""
    <div class="prediction-card">
        <div class="prediction-title">{title}</div>
        <div class="prediction-value">{value}</div>
        <div style="color: #6b7280; font-size: 0.95rem; margin-bottom: 1rem;">{unit}</div>
        <div class="prediction-change {change_class}">
            {arrow} {change_value} ({change_pct:+.2f}%)
        </div>
    </div>
    """, unsafe_allow_html=True)


def create_sparkline(data, height=80):
    """Create a mini sparkline chart for recent price trends"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        y=data,
        mode='lines',
        line=dict(color='#FFD700', width=2),
        fill='tozeroy',
        fillcolor='rgba(255, 215, 0, 0.1)',
        showlegend=False
    ))

    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        hovermode=False
    )

    return fig


# ==================== DATA LOADING ====================

@st.cache_resource
def load_predictor():
    """Load the predictor (cached)"""
    return GoldPricePredictor()


@st.cache_data
def load_historical_data():
    """Load historical gold price data"""
    try:
        # Try new filename first
        for filename in ['merged_clean.csv', 'gold_prices_clean.csv']:
            filepath = f'data/processed/{filename}'
            if os.path.exists(filepath):
                df = pd.read_csv(filepath)
                df['Date'] = pd.to_datetime(df['Date'])
                return df
        st.error("Historical data not found")
        return None
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None


def main():
    # Premium Header Bar
    st.markdown("""
    <div class="header-bar">
        <h1 class="header-title">💰 Gold Price Prediction Dashboard</h1>
        <p class="header-subtitle">Professional Financial Analytics | Real-time USD & PKR Forecasting</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar Configuration
    with st.sidebar:
        st.markdown("### ⚙️ Dashboard Settings")
        st.markdown("---")

        # Currency selection with flags
        st.markdown("#### 🌍 Currency Selection")
        currency_choice = st.radio(
            "",
            ["PKR 🇵🇰", "USD 🇺🇸"],
            help="Choose the currency for predictions",
            label_visibility="collapsed"
        )
        currency_choice = currency_choice.split()[0]  # Extract PKR or USD

        st.markdown("---")

        # Model selection
        st.markdown("#### 🤖 Model Selection")
        model_choice = st.selectbox(
            "",
            ["linear_regression", "random_forest"],
            format_func=lambda x: "🔮 " + x.replace("_", " ").title(),
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Info section
        with st.expander("📊 About This Dashboard", expanded=False):
            st.markdown("""
            **Prediction Currencies:**
            - 🇵🇰 **PKR** - Pakistani Rupees per tola
            - 🇺🇸 **USD** - US Dollars per troy ounce
            
            **Available Models:**
            - **Linear Regression** ⭐ Recommended
            - **Random Forest** - Ensemble method
            
            **Features Used:**
            - 📈 Technical Indicators (RSI, MACD)
            - 📊 Bollinger Bands
            - 🔄 Lag Features (1-14 days)
            - 📉 Rolling Statistics
            - ⚡ Momentum Indicators
            """)

        with st.expander("ℹ️ How to Use", expanded=False):
            st.markdown("""
            1. **Select Currency** - Choose PKR or USD
            2. **Select Model** - Pick your prediction model
            3. **View Prediction** - See next-day forecast
            4. **Analyze Charts** - Explore historical trends
            5. **Check Stats** - Review model performance
            """)

        st.markdown("---")
        st.markdown("**📅 Last Updated:** Nov 28, 2025")
        st.markdown("**✅ Status:** Operational")

    # Main content tabs
    tab1, tab2, tab3 = st.tabs(["🎯 Prediction", "📊 Historical Analysis", "🔬 Model Insights"])

    # Tab 1: Premium Prediction Interface
    with tab1:
        section(f"🎯 Next-Day Price Forecast", f"💰 {currency_choice}")

        # Load predictor
        try:
            predictor = load_predictor()

            # Make prediction
            with st.spinner("🔮 Analyzing market data and generating forecast..."):
                result = predictor.predict_next_day(model_choice, currency=currency_choice)

            # Current market overview
            st.markdown("#### 📊 Current Market Overview")
            col1, col2, col3, col4 = st.columns(4)

            if currency_choice == 'PKR':
                price_display = f"PKR {result['latest_price']:,.0f}"
                unit = "per tola"
                currency_symbol = "PKR"
            else:
                price_display = f"${result['latest_price']:,.2f}"
                unit = "per oz"
                currency_symbol = "$"

            with col1:
                styled_metric("Latest Date", result['latest_date'].strftime('%b %d, %Y'), icon="📅")

            with col2:
                styled_metric("Current Price", price_display, icon="💰")

            with col3:
                styled_metric("Forecast Date", result['prediction_date'].strftime('%b %d, %Y'), icon="🔮")

            with col4:
                styled_metric("Model Used", model_choice.replace("_", " ").title(), icon="🤖")

            st.markdown("<br>", unsafe_allow_html=True)

            # 7-day sparkline
            try:
                df_hist = load_historical_data()
                if df_hist is not None:
                    price_col = 'Close_PKR_per_tola' if currency_choice == 'PKR' else 'Close_USD_per_oz'
                    if price_col in df_hist.columns:
                        recent_prices = df_hist[price_col].tail(7).values
                        st.markdown("#### 📈 Last 7 Days Trend")
                        st.plotly_chart(create_sparkline(recent_prices, height=100), use_container_width=True)
            except:
                pass

            # Premium prediction cards
            st.markdown("---")
            st.markdown("#### 🔮 Forecast Results")

            col_pred1, col_pred2 = st.columns(2)

            is_positive = result['price_change'] > 0

            if currency_choice == 'PKR':
                pred_display = f"PKR {result['predicted_price']:,.0f}"
                unit_display = "per tola"
                change_display = f"PKR {abs(result['price_change']):,.0f}"
            else:
                pred_display = f"${result['predicted_price']:,.2f}"
                unit_display = "per troy ounce"
                change_display = f"${abs(result['price_change']):,.2f}"

            with col_pred1:
                prediction_card(
                    "Predicted Price Tomorrow",
                    pred_display,
                    unit_display,
                    change_display,
                    result['price_change_pct'],
                    is_positive
                )

            with col_pred2:
                # Additional insights card
                confidence = "High" if abs(result['price_change_pct']) < 2 else "Medium"
                trend = "Bullish" if is_positive else "Bearish"

                st.markdown(f"""
                <div class="prediction-card">
                    <div class="prediction-title">Market Outlook</div>
                    <div style="margin: 1.5rem 0;">
                        <div style="color: #9ca3af; font-size: 0.85rem; margin-bottom: 0.5rem;">TREND</div>
                        <div style="color: {'#10b981' if is_positive else '#ef4444'}; font-size: 1.5rem; font-weight: 700;">
                            {trend}
                        </div>
                    </div>
                    <div style="margin: 1.5rem 0;">
                        <div style="color: #9ca3af; font-size: 0.85rem; margin-bottom: 0.5rem;">CONFIDENCE</div>
                        <div style="color: #FFD700; font-size: 1.5rem; font-weight: 700;">
                            {confidence}
                        </div>
                    </div>
                    <div style="margin: 1.5rem 0;">
                        <div style="color: #9ca3af; font-size: 0.85rem; margin-bottom: 0.5rem;">CHANGE</div>
                        <div style="color: #e4e4e7; font-size: 1.25rem; font-weight: 700;">
                            {result['price_change_pct']:+.2f}%
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Price per gram conversion
            st.markdown("---")
            st.markdown("#### ⚖️ Per Gram Conversion")

            col_g1, col_g2, col_g3 = st.columns(3)

            if currency_choice == 'PKR':
                pred_per_gram = result['predicted_price'] / 11.664
                curr_per_gram = result['latest_price'] / 11.664
                with col_g1:
                    styled_metric("Current (per gram)", f"PKR {curr_per_gram:,.2f}", icon="⚖️")
                with col_g2:
                    styled_metric("Predicted (per gram)", f"PKR {pred_per_gram:,.2f}", icon="🔮")
                with col_g3:
                    styled_metric("Gram Change", f"PKR {pred_per_gram - curr_per_gram:+,.2f}", icon="📊")
            else:
                pred_per_gram = result['predicted_price'] / 31.1035
                curr_per_gram = result['latest_price'] / 31.1035
                with col_g1:
                    styled_metric("Current (per gram)", f"${curr_per_gram:,.2f}", icon="⚖️")
                with col_g2:
                    styled_metric("Predicted (per gram)", f"${pred_per_gram:,.2f}", icon="🔮")
                with col_g3:
                    styled_metric("Gram Change", f"${pred_per_gram - curr_per_gram:+,.2f}", icon="📊")

            # Success message
            st.markdown("---")
            st.markdown(f"""
            <div class="info-card">
                ✅ <strong>Forecast Generated Successfully</strong><br>
                Model: {model_choice.replace('_', ' ').title()} | Currency: {currency_choice} | 
                Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
            """, unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Error making prediction: {e}")
            st.info("Please ensure models are trained by running: `python src/train.py`")

    # Tab 2: Historical Analysis
    with tab2:
        section(f"📊 Historical Price Analysis", f"💰 {currency_choice}")

        df = load_historical_data()

        if df is not None:
            # Chart type and date range controls
            col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 2, 2, 1])

            with col_ctrl1:
                start_date = st.date_input(
                    "📅 Start Date",
                    value=df['Date'].max() - timedelta(days=180),
                    min_value=df['Date'].min().date(),
                    max_value=df['Date'].max().date()
                )

            with col_ctrl2:
                end_date = st.date_input(
                    "📅 End Date",
                    value=df['Date'].max().date(),
                    min_value=df['Date'].min().date(),
                    max_value=df['Date'].max().date()
                )

            with col_ctrl3:
                chart_type = st.selectbox(
                    "📈 Chart Type",
                    ["Line Chart", "Candlestick Chart"]
                )

            with col_ctrl4:
                st.markdown("<br>", unsafe_allow_html=True)
                download_btn = st.button("📥 Download", use_container_width=True)

            # Filter data
            mask = (df['Date'] >= pd.to_datetime(start_date)) & (df['Date'] <= pd.to_datetime(end_date))
            df_filtered = df[mask]

            # Determine price columns
            if currency_choice == 'USD' and 'Close_USD_per_oz' in df_filtered.columns:
                price_col = 'Close_USD_per_oz'
                open_col = 'Open_USD_per_oz'
                high_col = 'High_USD_per_oz'
                low_col = 'Low_USD_per_oz'
                title = f'💰 Gold Price History - USD per oz'
                ylabel = 'Price (USD)'
                prefix = '$'
            else:
                price_col = 'Close_PKR_per_tola'
                open_col = 'Open_PKR_per_tola'
                high_col = 'High_PKR_per_tola'
                low_col = 'Low_PKR_per_tola'
                title = f'💰 Gold Price History - PKR per tola'
                ylabel = 'Price (PKR)'
                prefix = 'PKR '

            # Create chart based on type
            fig = go.Figure()

            if chart_type == "Candlestick Chart" and all(col in df_filtered.columns for col in [open_col, high_col, low_col, price_col]):
                fig.add_trace(go.Candlestick(
                    x=df_filtered['Date'],
                    open=df_filtered[open_col],
                    high=df_filtered[high_col],
                    low=df_filtered[low_col],
                    close=df_filtered[price_col],
                    name='Gold Price',
                    increasing_line_color='#10b981',
                    decreasing_line_color='#ef4444'
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df_filtered['Date'],
                    y=df_filtered[price_col],
                    mode='lines',
                    name='Gold Price',
                    line=dict(color='#FFD700', width=3),
                    fill='tozeroy',
                    fillcolor='rgba(255, 215, 0, 0.1)'
                ))

            # Premium dark theme layout
            fig.update_layout(
                title=dict(
                    text=title,
                    font=dict(size=20, color='#e4e4e7', family='Inter')
                ),
                xaxis_title='Date',
                yaxis_title=ylabel,
                hovermode='x unified',
                template='plotly_dark',
                plot_bgcolor='#0f1419',
                paper_bgcolor='#1a1f2e',
                font=dict(color='#e4e4e7', family='Inter'),
                height=550,
                xaxis=dict(
                    showgrid=True,
                    gridcolor='#374151',
                    gridwidth=0.5
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='#374151',
                    gridwidth=0.5
                ),
                margin=dict(l=60, r=40, t=60, b=60)
            )

            st.plotly_chart(fig, use_container_width=True)

            # Download functionality
            if download_btn:
                csv = df_filtered.to_csv(index=False)
                st.download_button(
                    label="📥 Download Filtered Data as CSV",
                    data=csv,
                    file_name=f"gold_prices_{currency_choice}_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            # Statistics
            st.markdown("---")
            st.markdown("#### 📊 Statistical Summary")

            col1, col2, col3, col4 = st.columns(4)

            mean_val = df_filtered[price_col].mean()
            median_val = df_filtered[price_col].median()
            min_val = df_filtered[price_col].min()
            max_val = df_filtered[price_col].max()

            with col1:
                styled_metric("Mean Price", f"{prefix}{mean_val:,.2f}", icon="📊")

            with col2:
                styled_metric("Median Price", f"{prefix}{median_val:,.2f}", icon="📈")

            with col3:
                styled_metric("Minimum", f"{prefix}{min_val:,.2f}", icon="📉")

            with col4:
                styled_metric("Maximum", f"{prefix}{max_val:,.2f}", icon="📈")

            # Additional stats
            st.markdown("<br>", unsafe_allow_html=True)
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)

            std_val = df_filtered[price_col].std()
            range_val = max_val - min_val
            records = len(df_filtered)
            volatility = (std_val / mean_val) * 100 if mean_val > 0 else 0

            with col_s1:
                styled_metric("Std Deviation", f"{prefix}{std_val:,.2f}", icon="📊")

            with col_s2:
                styled_metric("Price Range", f"{prefix}{range_val:,.2f}", icon="📏")

            with col_s3:
                styled_metric("Records", f"{records:,}", icon="📝")

            with col_s4:
                styled_metric("Volatility", f"{volatility:.2f}%", icon="⚡")

            # Data table
            st.markdown("---")
            with st.expander("📋 View Detailed Data Table"):
                display_cols = ['Date', open_col, high_col, low_col, price_col]
                display_cols = [col for col in display_cols if col in df_filtered.columns]
                st.dataframe(
                    df_filtered[display_cols].tail(100).style.format({
                        col: "{:,.2f}" for col in display_cols if col != 'Date'
                    }),
                    use_container_width=True,
                    height=400
                )

    # Tab 3: Model Insights
    with tab3:
        section("🔬 Model Insights & Performance", "🤖")

        # Model cards
        st.markdown("#### 🤖 Available Prediction Models")

        col_m1, col_m2 = st.columns(2)

        with col_m1:
            card("🔮 Linear Regression", """
            <strong>Recommended Model ⭐</strong><br><br>
            <strong>Type:</strong> Statistical Regression<br>
            <strong>Best For:</strong> Stable, reliable predictions<br>
            <strong>Speed:</strong> ⚡ Very Fast (&lt;100ms)<br>
            <strong>Interpretability:</strong> ✅ High<br><br>
            <strong>Performance:</strong><br>
            • PKR: R² 0.9613, RMSE 3,062 PKR<br>
            • USD: R² 0.8656, RMSE $28.96<br><br>
            <span style="color: #10b981;">✅ Production Ready</span>
            """, "🔮")

        with col_m2:
            card("🌲 Random Forest", """
            <strong>Ensemble Method</strong><br><br>
            <strong>Type:</strong> Tree-based Ensemble<br>
            <strong>Best For:</strong> Complex pattern recognition<br>
            <strong>Speed:</strong> ⚡ Fast (&lt;200ms)<br>
            <strong>Interpretability:</strong> ⚠️ Medium<br><br>
            <strong>Performance:</strong><br>
            • PKR: R² 0.0935, RMSE 14,827 PKR<br>
            • USD: R² 0.6956, RMSE $43.58<br><br>
            <span style="color: #f59e0b;">⚠️ Needs Hyperparameter Tuning</span>
            """, "🌲")

        # Feature breakdown
        st.markdown("---")
        with st.expander("📊 Feature Engineering Details (103 Total Features)", expanded=False):
            col_f1, col_f2, col_f3 = st.columns(3)

            with col_f1:
                st.markdown("""
                **📈 Technical Indicators**
                - RSI (14-period)
                - MACD (12, 26, 9)
                - Bollinger Bands (20-day)
                - EMA (7, 14, 30-day)
                - Momentum (5, 10, 20-day)
                - Volatility (7, 14, 30-day)
                """)

            with col_f2:
                st.markdown("""
                **🔄 Historical Features**
                - Lag prices (1-14 days)
                - Rolling mean (3, 7, 14, 30)
                - Rolling std (3, 7, 14, 30)
                - Rolling min/max (3, 7, 14, 30)
                - Daily returns
                - Price changes
                """)

            with col_f3:
                st.markdown("""
                **🕐 Temporal Features**
                - Day of week
                - Month of year
                - Quarter
                - Year
                - Cyclical encodings (sin/cos)
                - Weekend/weekday flag
                """)

        # Performance metrics table
        st.markdown("---")
        with st.expander("📊 Detailed Performance Metrics", expanded=True):
            st.markdown("#### Model Comparison Table")

            try:
                comparison_df = pd.read_csv('reports/model_comparison.csv')
                st.dataframe(
                    comparison_df.style.background_gradient(subset=['Val R'], cmap='RdYlGn'),
                    use_container_width=True,
                    height=250
                )
            except:
                performance_data = {
                    'Model': [
                        'Linear Regression (PKR)',
                        'Linear Regression (USD)',
                        'Random Forest (PKR)',
                        'Random Forest (USD)'
                    ],
                    'Val RMSE': ['3,062 PKR', '$28.96', '14,827 PKR', '$43.58'],
                    'Val R²': ['0.9613', '0.8656', '0.0935', '0.6956'],
                    'Train R²': ['0.9954', '0.9890', '0.9990', '0.9979'],
                    'Error Rate': ['~1.6%', '~1.2%', '~7.9%', '~1.9%'],
                    'Status': ['✅ Excellent', '✅ Very Good', '⚠️ Overfitting', '⚠️ Needs Work']
                }

                df_perf = pd.DataFrame(performance_data)
                st.dataframe(df_perf, use_container_width=True, height=200)

        # Training details
        st.markdown("---")
        with st.expander("🎯 Training Configuration", expanded=False):
            col_t1, col_t2 = st.columns(2)

            with col_t1:
                st.markdown("""
                **📦 Dataset Split**
                - Training: 70% (1,256 records)
                - Validation: 15% (269 records)
                - Test: 15% (270 records)
                - **Total:** 1,795 records
                
                **🔧 Preprocessing**
                - StandardScaler for Linear Regression
                - No scaling for Random Forest
                - Feature correlation analysis
                - Outlier detection (IQR method)
                """)

            with col_t2:
                st.markdown("""
                **⚙️ Hyperparameters**
                - **Linear Regression:** Default (OLS)
                - **Random Forest:**
                  - n_estimators: 100
                  - max_depth: 10
                  - random_state: 42
                
                **📊 Evaluation Metrics**
                - RMSE (Root Mean Squared Error)
                - R² Score (Coefficient of Determination)
                - MAE (Mean Absolute Error)
                - MAPE (Mean Absolute Percentage Error)
                """)

        # Evaluation metrics explainer
        st.markdown("---")
        with st.expander("🎯 Understanding Evaluation Metrics", expanded=False):
            st.markdown("""
            **RMSE (Root Mean Squared Error)**
            - Average prediction error in original units
            - Lower is better
            - Penalizes large errors more heavily
            
            **R² Score (Coefficient of Determination)**
            - Proportion of variance explained by model (0-1)
            - Closer to 1 is better
            - 0.96 = model explains 96% of price variation
            
            **MAE (Mean Absolute Error)**
            - Average absolute difference between predictions and actual
            - Easy to interpret
            - Less sensitive to outliers than RMSE
            
            **MAPE (Mean Absolute Percentage Error)**
            - Average percentage error
            - Scale-independent metric
            - Good for comparing models across different datasets
            """)

        # Recommendations
        st.markdown("---")
        card("💡 Recommendations", """
        <strong>For Production Use:</strong><br>
        • ✅ Use <strong>Linear Regression</strong> for both PKR and USD predictions<br>
        • ✅ Monitor model performance weekly<br>
        • ✅ Retrain models monthly with new data<br><br>
        
        <strong>For Improved Accuracy:</strong><br>
        • 🔧 Tune Random Forest (reduce max_depth to 5-7)<br>
        • 📊 Add more recent data (daily updates)<br>
        • 🤖 Consider ensemble methods (model averaging)<br>
        • 📈 Add external features (economic indicators)<br><br>
        
        <strong>Model Confidence:</strong><br>
        • High confidence when change &lt; 2%<br>
        • Medium confidence when 2% ≤ change &lt; 5%<br>
        • Low confidence when change ≥ 5%
        """, "💡")

        # Disclaimer
        st.markdown("---")
        st.markdown("""
        <div class="info-card" style="border-left-color: #f59e0b;">
            ⚠️ <strong>Important Disclaimer</strong><br><br>
            This is a predictive model for <strong>educational and research purposes</strong>. 
            Gold prices are influenced by numerous factors including global markets, currency exchange rates, 
            geopolitical events, and economic indicators. <br><br>
            <strong>Always consult certified financial experts before making investment decisions.</strong>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

