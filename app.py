"""
TAESUNG WEB — 분양현장 통합관리

화면 구조
  대시보드 → 현장 선택 → 현장 화면(탭: 현황판·계약관리·입출금·해지·계좌현황·실적·직원/근태·정산·설정)
  관리자: 현장 관리 · 사용자 관리 · 데이터 점검
"""
import time

import streamlit as st

import db
from ui import common as cm
from ui import layout

st.set_page_config(page_title="TAESUNG WEB", page_icon=":material/apartment:", layout="wide",
                   initial_sidebar_state="expanded")
db.init_db()
layout.inject_css()

MAX_FAILS = 5
LOCK_SECONDS = 60


def login_page():
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("<div style='height:8vh'></div>"
                    "<div class='ts-title' style='font-size:26px;letter-spacing:3px'>TAESUNG</div>"
                    "<div class='ts-meta'>분양현장 통합관리 시스템</div>", unsafe_allow_html=True)
        locked_until = st.session_state.get('_login_locked_until', 0)
        if time.time() < locked_until:
            st.error(f"로그인 실패가 반복되어 잠시 잠겼습니다. {int(locked_until - time.time())}초 후 다시 시도하세요.")
            st.stop()
        with st.form("login_form"):
            username = st.text_input("아이디")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", width="stretch", type="primary")
        if submitted:
            user = db.authenticate_user(username, password)
            if user:
                st.session_state.pop('_login_fails', None)
                st.session_state.user = user
                st.session_state['view'] = 'dashboard'
                st.rerun()
            fails = st.session_state.get('_login_fails', 0) + 1
            st.session_state['_login_fails'] = fails
            if fails >= MAX_FAILS:
                st.session_state['_login_locked_until'] = time.time() + LOCK_SECONDS
                st.session_state['_login_fails'] = 0
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def force_password_change(user):
    st.markdown("<div class='ts-title'>비밀번호 변경</div>", unsafe_allow_html=True)
    st.warning("초기 비밀번호로 로그인했습니다. 계속하려면 비밀번호를 변경하세요.")
    with st.form("force_pw_form"):
        pw1 = st.text_input("새 비밀번호", type="password")
        pw2 = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경", type="primary"):
            problem = cm.password_problem(pw1, pw2)
            if problem:
                st.error(problem)
            else:
                db.update_user_password(user['id'], pw1)
                user['must_change_password'] = False
                st.rerun()


def main():
    user = st.session_state.user
    layout.render_sidebar(user)
    cm.show_flash()
    if user.get('must_change_password'):
        force_password_change(user)
        return

    view = st.session_state.get('view', 'dashboard')
    if view == 'site':
        from ui import site
        site.render(user, st.session_state.get('site_id'))
    elif view.startswith('admin_') and cm.is_admin(user):
        from ui import admin
        admin.render(user, view)
    else:
        from ui import dashboard
        dashboard.render(user)


if 'user' not in st.session_state:
    login_page()
else:
    main()
