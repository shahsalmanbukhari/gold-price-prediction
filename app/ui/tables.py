import streamlit as st


def dataframe(frame, empty_message="No records match the selected context."):
    if frame is None or frame.empty:
        st.info(empty_message)
        return
    st.dataframe(frame, use_container_width=True, hide_index=True, height=min(420, 38 + len(frame) * 35))


def render_data_table(frame, empty_message="No records match the selected context."):
    dataframe(frame, empty_message)
