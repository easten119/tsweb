import streamlit as st
import sidebar

user = sidebar.page_setup("수수료", "💳", roles=sidebar.EDIT_ROLES)
st.info("🚧 준비중입니다. 산정 기준(지급 대상·요율·집행일)이 정해지면 구현합니다.")
