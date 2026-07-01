import streamlit as st
import sidebar

st.set_page_config(page_title="기본 정산", page_icon="📊", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("📊 기본 정산")
st.info("🚧 준비중입니다.")
