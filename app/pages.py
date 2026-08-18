"""Professional read-only dashboard pages built on shared UI/query services."""
from datetime import datetime, timezone
import math
import pandas as pd
import plotly.express as px
import streamlit as st

from app import dashboard_data as data
from app.dashboard_pages import build_training_metric_chart_data
from app.ui.cards import badge, metric_row, section, render_kpi_card, render_section_header, render_status_badge
from app.ui.charts import comparison_figure, line, market_svg
from app.ui.empty_states import data_error, empty, render_empty_state
from app.ui.formatting import age_seconds, datetime_text, duration, percent, price
from app.ui.layout import finish, page
from app.ui.tables import dataframe
from config.settings import get_settings
from realtime.redis_cache import get_redis_cache


def _context(title, subtitle):
    try: return page(title, subtitle)
    except Exception as exc:
        data_error(exc); finish(); return None


def _comparison(context):
    if not context["comparison_name"]:
        empty("No comparison model selected", "Choose Comparison model in the global header to align evaluated outcomes.")
        return
    aligned=data.aligned_comparison(context["model_name"],context["model_version"],context["comparison_name"],context["comparison_version"],context["horizon"],context["date_from"],context["date_to"])
    if aligned.empty:
        empty("Insufficient common samples", "Both models need evaluated records for the same provider, horizon, target timestamp and evaluator version.")
        return
    st.metric("Common evaluated samples",len(aligned))
    figure=comparison_figure(aligned)
    if figure: st.plotly_chart(figure,use_container_width=True)


def overview():
    context=_context("Overview","Live market, forecasts and model health")
    if not context:return
    try:
        live,candle,heartbeat,worker=data.latest_market()
        frame,states,run,heartbeat,notice,scheduler=data.overview_state(**{k:context[k] for k in ("model_name","model_version","horizon","date_from","date_to")})
        decisions=data.decisions(context["model_name"],context["model_version"],context["horizon"],context["date_from"],context["date_to"])
        market=data.market_series()
    except Exception as exc:data_error(exc);finish();return
    health=context["health"]
    accepted_ids=set(decisions.loc[decisions.acceptance_status=="ACCEPTED","prediction_id"].dropna()) if not decisions.empty else set()
    qualified=frame[frame.id.isin(accepted_ids)].tail(6) if not frame.empty else pd.DataFrame()
    metrics=data.performance(frame)
    latest=qualified.iloc[-1] if not qualified.empty else (frame.iloc[-1] if frame is not None and not frame.empty else None)
    cols=st.columns(4)
    with cols[0]:render_kpi_card("Live Gold",price(live.price_usd) if live else "—",f"{getattr(live,'provider',None) or 'No provider'} · {health.live_detail}",health.live_quote_status)
    with cols[1]:
        if latest is not None:
            movement=float(latest.predicted_return)*100
            render_kpi_card("Selected Forecast",price(latest.predicted_price),f"{movement:+.2f}% · {str(latest.predicted_trend).upper()} · target {context['horizon']}m",latest.status)
        else:render_kpi_card("Selected Forecast","No forecast",f"No {context['horizon']}m result for the viewing model","NO DATA")
    with cols[2]:render_kpi_card("Improvement over Persistence",percent(metrics.get("improvement_pct")),f"{percent(metrics.get('directional_accuracy'))} direction · {metrics.get('evaluated',0)} evaluated samples",context["model_status"] or "NO DATA")
    with cols[3]:render_kpi_card("System",health.overall_data_status.title(),health.live_detail,health.overall_data_status)

    render_section_header("Market and forecast", "Actual live snapshots and the selected horizon; gaps remain visible.")
    chart_col,forecast_col=st.columns([2,1],gap="medium")
    with chart_col:
        chart=market_svg(market,latest.predicted_price if latest is not None else None,latest.baseline_price if latest is not None else None)
        if chart:
            st.markdown(chart,unsafe_allow_html=True)
        else:render_empty_state("No market series","Live snapshots will appear here after the provider feed stores valid data.")
    with forecast_col:
        if latest is None:
            render_empty_state("No approved production model","The latest candidate did not beat the persistence baseline. Current baseline forecasts remain available for research only.","View training results","routed_pages/self_learning.py")
        else:
            decision=decisions[decisions.prediction_id==latest.id].iloc[0] if not decisions.empty and (decisions.prediction_id==latest.id).any() else None
            trust=getattr(decision,'trust_status_at_decision','Not evaluated') if decision is not None else 'Not evaluated'
            st.markdown(f'''<div style="background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:18px;min-height:350px;box-sizing:border-box">
              <div class="gpi-kpi-label">CURRENT FORECAST</div><div class="gpi-kpi-value">{price(latest.predicted_price)}</div>{render_status_badge(str(latest.predicted_trend).upper())}
              <div style="border-top:1px solid #E2E8F0;margin:16px 0 12px"></div>
              <div class="gpi-kpi-detail" style="line-height:2"><b>Expected movement</b> {float(latest.predicted_return)*100:+.3f}%<br><b>Target</b> {datetime_text(latest.target_at)}<br><b>Horizon</b> {latest.horizon_minutes} minutes<br><b>Model</b> {str(latest.model_name).replace('_',' ').title()}<br><b>Trust</b> {trust}<br><b>Data quality</b> {health.candle_status}</div></div>''',unsafe_allow_html=True)

    tab1,tab2,tab3,tab4=st.tabs(["Horizon performance","Latest predictions","Attention","System details"])
    with tab1:
        if states:dataframe(pd.DataFrame([{"Horizon":f"{x.horizon_minutes}m","Algorithm":str(x.algorithm).replace('_',' ').title(),"Trust":badge(x.trust_status),"Improvement":percent(x.offline_improvement_pct),"Live samples":x.rolling_sample_count,"Direction":percent(x.rolling_directional_accuracy_pct),"Last prediction":datetime_text(x.last_prediction_at)} for x in states]))
        else:empty("No active production models","No bundle has passed every promotion quality gate.")
    with tab2:
        if qualified.empty:empty("No qualified forecasts","No selected-model forecast passed every alert-quality rule in this period.")
        else:dataframe(pd.DataFrame([{"Horizon":f"{r.horizon_minutes}m","Created":datetime_text(r.prediction_created_at),"Target":datetime_text(r.target_at),"Reference":price(r.reference_price),"Prediction":price(r.predicted_price),"Direction":badge(str(r.predicted_trend).upper()),"Outcome":"Pending" if r.status=="PENDING" else "Evaluated"} for r in qualified.itertuples()]))
    with tab3:
        nonaccepted=decisions[decisions.acceptance_status!="ACCEPTED"] if not decisions.empty else pd.DataFrame()
        if nonaccepted.empty:empty("Nothing requires attention","No suppressed or rejected prediction decisions match this context.")
        else:dataframe(nonaccepted.acceptance_reason_code.value_counts().rename_axis("Reason").reset_index(name="Count"))
        if run:st.caption(f"Latest training: {run.status} · {run.new_version or 'no candidate'} · {run.error_message or run.trigger}")
    with tab4:
        st.markdown(f"**Live quote:** {health.live_detail}  \n**Candle context:** {health.candle_detail}  \n**Worker:** {health.worker_detail}  \n**Latest completed candle:** {datetime_text(getattr(candle,'candle_time',None))}")
    finish()


def live_forecasts():
    context=_context("Live Forecasts","Read-only forecasts generated by the independent background worker.")
    if not context:return
    try:frame=data.latest_forecasts(**{k:context[k] for k in ("model_name","model_version","horizon","date_from","date_to")});decisions=data.decisions(context["model_name"],context["model_version"],context["horizon"],context["date_from"],context["date_to"])
    except Exception as exc:data_error(exc);finish();return
    st.info(f"Viewing {context['model_name'] or 'no model'} · {context['model_version'] or '—'} · {badge(context['model_status'])}. Selection does not change worker inference.")
    if frame.empty:empty("No forecasts for this context","The selected model/version has no data for this horizon. No alternative model was substituted.");finish();return
    decision_by_id={r.prediction_id:r for r in decisions.itertuples()} if not decisions.empty else {}
    now=datetime.now(timezone.utc)
    for row in reversed(list(frame.itertuples())):
        decision=decision_by_id.get(row.id); target=pd.Timestamp(row.target_at).to_pydatetime();target=target.replace(tzinfo=timezone.utc) if target.tzinfo is None else target.astimezone(timezone.utc)
        with st.container(border=True):
            c1,c2,c3,c4=st.columns(4)
            c1.markdown(f"### {row.horizon_minutes} minutes");c1.caption(badge(str(row.predicted_trend).upper()))
            c2.metric("Reference",price(row.reference_price));c2.metric("Predicted",price(row.predicted_price),price(float(row.predicted_price)-float(row.reference_price)))
            c3.metric("Expected change",percent(float(row.predicted_return)*100,3));c3.metric("Countdown",duration(max(0,(target-now).total_seconds())))
            c4.markdown(f"**{badge(decision.acceptance_status if decision else 'UNDECIDED')}**");c4.caption(decision.acceptance_reason_detail if decision else "Decision audit unavailable")
            st.caption(f"Created {datetime_text(row.prediction_created_at)} · Target {datetime_text(row.target_at)} · {row.model_name} · {row.model_version} · Trust {getattr(decision,'trust_status_at_decision','—')} · Data gaps {row.missing_period_count} · Interval method {row.interval_method or 'not available'}")
    finish()


def performance():
    context=_context("Prediction Performance","Evaluated outcomes for the globally selected model and horizon.")
    if not context:return
    try:frame=data.predictions(**{k:context[k] for k in ("model_name","model_version","horizon","date_from","date_to")})
    except Exception as exc:data_error(exc);finish();return
    metrics=data.performance(frame)
    metric_row([("MAE",price(metrics.get("mae")),None,"Average absolute difference between predicted and actual prices."),("RMSE",price(metrics.get("rmse"))),("sMAPE",percent(metrics.get("smape"))),("Directional accuracy",percent(metrics.get("directional_accuracy")),None,"Percentage of evaluated forecasts whose direction matched actual movement."),("Persistence MAE",price(metrics.get("baseline_mae")),None,"Persistence assumes future price equals reference price."),("Improvement",price(metrics.get("improvement"))),("Evaluated",metrics.get("evaluated",0)),("Unresolvable",metrics.get("unresolvable",0)),("Median delay",duration(metrics.get("median_delay")))],3)
    evaluated=frame[frame.status=="EVALUATED"].copy() if not frame.empty else pd.DataFrame()
    if len(evaluated)<get_settings().ml.performance_minimum_samples:st.warning(f"At least {get_settings().ml.performance_minimum_samples} evaluated samples are required before declaring performance quality.")
    if not evaluated.empty:
        evaluated["absolute_error_numeric"]=pd.to_numeric(evaluated.absolute_error,errors="coerce")
        evaluated["rolling_direction"]=pd.to_numeric(evaluated.direction_correct,errors="coerce").rolling(30,min_periods=5).mean()*100
        for fig in (line(evaluated,"target_at","actual_price",title="Actual price over time"),line(evaluated,"target_at","absolute_error_numeric",title="Absolute error over time"),line(evaluated,"target_at","rolling_direction",title="Rolling directional accuracy"),px.histogram(evaluated,x="evaluation_delay_seconds",title="Evaluation delays")):
            if fig:st.plotly_chart(fig,use_container_width=True)
    else:empty("No evaluated predictions","Metrics and charts appear only after bounded same-provider evaluation.")
    section("Viewing model versus comparison model");_comparison(context);finish()


def non_accepted():
    context=_context("Non-Accepted Predictions","Alert-quality decisions—not rejected training candidates.")
    if not context:return
    try:frame=data.decisions(context["model_name"],context["model_version"],context["horizon"],context["date_from"],context["date_to"])
    except Exception as exc:data_error(exc);finish();return
    if frame.empty:empty("No prediction decisions","No accepted or non-accepted decisions match this selected model and horizon.");finish();return
    reasons=sorted(frame.acceptance_reason_code.dropna().unique());selected=st.multiselect("Reason",reasons,default=reasons,key="nonaccepted_reason")
    trust=sorted(frame.trust_status_at_decision.dropna().unique());selected_trust=st.multiselect("Trust status",trust,default=trust,key="nonaccepted_trust")
    filtered=frame[frame.acceptance_reason_code.isin(selected)&frame.trust_status_at_decision.isin(selected_trust)]
    rejected=filtered[filtered.acceptance_status!="ACCEPTED"]
    metric_row([("Total decisions",len(filtered)),("Non-accepted",len(rejected)),("Accepted",int((filtered.acceptance_status=="ACCEPTED").sum())),("Acceptance rate",percent((filtered.acceptance_status=="ACCEPTED").mean()*100 if len(filtered) else None))])
    if rejected.empty:empty("No non-accepted predictions","All matching decisions were accepted or no suppressed records exist.");finish();return
    c1,c2=st.columns(2)
    with c1:st.plotly_chart(px.bar(rejected.acceptance_reason_code.value_counts().rename_axis("reason").reset_index(name="count"),x="reason",y="count",title="Reasons"),use_container_width=True)
    with c2:st.plotly_chart(px.histogram(rejected,x="decision_at",color="acceptance_reason_code",title="Reasons over time"),use_container_width=True)
    table=rejected[["decision_at","horizon_minutes","model_name","model_version","reference_price","predicted_price","predicted_direction","trust_status_at_decision","acceptance_status","acceptance_reason_code","acceptance_reason_detail","required_sample_count","actual_sample_count","required_directional_accuracy","actual_directional_accuracy","required_baseline_improvement","actual_baseline_improvement","required_prediction_magnitude","actual_prediction_magnitude","data_fresh","missing_period_count"]]
    dataframe(table)
    for row in rejected.head(20).itertuples():
        with st.expander(f"Decision {row.id} · {row.acceptance_reason_code} · {datetime_text(row.decision_at)}"):
            st.json({column:getattr(row,column) for column in rejected.columns},expanded=False)
    finish()


def models_training():
    context=_context("Models & Training","Production state, candidate evidence and protected training controls.")
    if not context:return
    try:runs=data.training_runs();_,states,latest,_,_,_=data.overview_state(context["model_name"],context["model_version"],context["horizon"],context["date_from"],context["date_to"])
    except Exception as exc:data_error(exc);finish();return
    section("Production models")
    if states:dataframe(pd.DataFrame([{"Horizon":f"{x.horizon_minutes}m","Algorithm":x.algorithm,"Version":x.model_version,"Trust":badge(x.trust_status),"Test samples":x.offline_test_samples,"Improvement":percent(x.offline_improvement_pct),"Rolling samples":x.rolling_sample_count,"Directional accuracy":percent(x.rolling_directional_accuracy_pct)} for x in states]))
    else:empty("No approved production model","Candidate selection remains separate from promotion.")
    section("Training runs")
    if runs.empty:empty("No training runs","Training remains an explicit protected operation.")
    else:
        dataframe(runs[[c for c in ["started_at","completed_at","trigger","model_name","new_version","status","production_changed","error_message","candidate_path"] if c in runs]])
        chart=build_training_metric_chart_data(runs)
        if chart.empty:empty("No numeric candidate metrics","Training metrics are missing or null.")
        else:st.plotly_chart(px.line(chart,x="completed_at",y="value",color="metric",facet_row="horizon",line_dash="algorithm",markers=True,title="Candidate and persistence metrics"),use_container_width=True)
    section("Protected model actions")
    st.info("Viewing-model controls in the header never train, promote, rollback, change manifests, or alter worker inference.")
    if st.button("Queue candidate training",key="queue_training"):
        st.warning("Use the documented CLI or existing administrator workflow. Promotion and rollback require separate explicit review.")
    finish()


def historical_data():
    context=_context("Historical Data","Canonical HistData one-minute candles and import quality.")
    if not context:return
    try:(count,minimum,maximum),imports=data.historical_summary()
    except Exception as exc:data_error(exc);finish();return
    metric_row([("Candles",f"{count:,}"),("Minimum timestamp",datetime_text(minimum)),("Maximum timestamp",datetime_text(maximum)),("Provider","histdata"),("Symbol","XAUUSD"),("Timeframe","1m")],3)
    if imports.empty:empty("No import audit","No historical ZIP import records exist.");finish();return
    statuses=imports.status.astype(str).str.upper().value_counts();metric_row([("ZIP/CSV audits",len(imports)),("Completed",int(statuses.get("COMPLETED",0)+statuses.get("SUCCESS",0))),("Failed",int(statuses.get("FAILED",0))),("Skipped",int(statuses.get("SKIPPED",0))),("Duplicates",int(pd.to_numeric(imports.duplicate_rows,errors="coerce").sum())),("Invalid rows",int(pd.to_numeric(imports.invalid_rows,errors="coerce").sum()))],3)
    dataframe(imports[[c for c in ["started_at","completed_at","source_zip","source_csv","status","total_rows","inserted_rows","duplicate_rows","invalid_rows","error_message"] if c in imports]])
    finish()


def system_health():
    context=_context("System Health","Independent worker, infrastructure, scheduler and artifact diagnostics.")
    if not context:return
    try:heartbeat,provider,scheduler,notification,health=data.system_state();cache=get_redis_cache();redis_state="Available" if cache and cache.is_available() else "Optional / unavailable"
    except Exception as exc:data_error(exc);finish();return
    uptime=(datetime.now(timezone.utc)-(heartbeat.started_at if heartbeat.started_at.tzinfo else heartbeat.started_at.replace(tzinfo=timezone.utc))).total_seconds() if heartbeat else None
    metric_row([("Worker",badge(health)),("Instance",heartbeat.instance_id if heartbeat else "—"),("Uptime",duration(uptime)),("Provider",provider.provider_name if provider else "—"),("Provider health",badge("RUNNING" if provider and provider.is_healthy else "DEGRADED")),("PostgreSQL","Connected"),("Redis",redis_state),("Last quote",datetime_text(heartbeat.last_live_quote_at) if heartbeat else "—"),("Last prediction",datetime_text(heartbeat.last_prediction_at) if heartbeat else "—"),("Last evaluation",datetime_text(heartbeat.last_evaluation_at) if heartbeat else "—"),("Last notification",datetime_text(notification.created_at) if notification else "—"),("Last training",datetime_text(heartbeat.last_training_at) if heartbeat else "—")],3)
    if heartbeat and heartbeat.last_error:st.error(f"Current worker diagnostic: {heartbeat.last_error}")
    model_health=data.latest_model_health(context.get("model_version"))
    render_section_header("Production model health", "Rolling evaluated outcomes compared with persistence; at least 30 samples are required.")
    if model_health.empty:
        empty("No model-health checks yet", "Health checks appear after 30 evaluated predictions for a horizon and model version.")
    else:
        dataframe(pd.DataFrame([{
            "Horizon":f"{int(row.horizon_minutes)}m", "Model version":row.model_version,
            "Status":badge(row.status), "Model MAE":row.model_mae,
            "Persistence MAE":row.persistence_mae,
            "Directional accuracy":percent(float(row.directional_accuracy)*100 if pd.notna(row.directional_accuracy) else None),
            "Samples":row.sample_count, "Checked":datetime_text(row.checked_at),
            "Alert sent":"Yes" if row.alert_sent else "No",
        } for row in model_health.itertuples()]))
    with st.expander("Scheduler watermarks and troubleshooting",expanded=True):
        st.json({"last_candle_id":getattr(scheduler,"last_candle_id",None),"last_outcome_id":getattr(scheduler,"last_outcome_id",None),"last_successful_training":datetime_text(getattr(scheduler,"last_successful_training_at",None)),"last_training_attempt":datetime_text(getattr(scheduler,"last_training_attempt_at",None)),"production_manifest":str(data._production_manifest() or "No approved manifest")},expanded=False)
        st.markdown("Check `logs/background/`, `.env`, PostgreSQL availability and provider timestamps. Secrets are never displayed here.")
    finish()
