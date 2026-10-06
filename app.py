import time
import pandas as pd
import streamlit as st
import db
import sidebar

db.init_db()

MAX_FAILS = 5
LOCK_SECONDS = 60


def login_page():
    st.set_page_config(page_title="TAESUNG WEB", page_icon="🏗️", layout="centered")
    st.markdown("## 🏗️ TAESUNG WEB")
    st.caption("분양 현장 관리 시스템")

    locked_until = st.session_state.get('_login_locked_until', 0)
    if time.time() < locked_until:
        st.error(f"로그인 실패가 반복되어 잠시 잠겼습니다. {int(locked_until - time.time())}초 후 다시 시도하세요.")
        st.stop()

    with st.form("login_form"):
        username = st.text_input("아이디", placeholder="아이디를 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", width="stretch", type="primary")

    if submitted:
        user = db.authenticate_user(username, password)
        if user:
            st.session_state.pop('_login_fails', None)
            st.session_state.user = user
            st.rerun()
        else:
            fails = st.session_state.get('_login_fails', 0) + 1
            st.session_state['_login_fails'] = fails
            if fails >= MAX_FAILS:
                st.session_state['_login_locked_until'] = time.time() + LOCK_SECONDS
                st.session_state['_login_fails'] = 0
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def main_page():
    user = sidebar.page_setup("TAESUNG WEB", "🏗️")
    sidebar.show_flash()

    all_sites = db.get_all_sites()
    sites = sidebar.get_accessible_sites(user, all_sites)
    active_sites = [s for s in sites if s['status'] == '진행중']
    total_emp = sum(s['employee_count'] for s in sites)

    unit_summary = db.get_all_site_unit_summary()
    cancel_counts = db.get_cancel_counts_by_site()
    total_units = sum(sum(unit_summary.get(s['id'], {}).values()) for s in sites)
    total_signed = sum(unit_summary.get(s['id'], {}).get('계약', 0) + unit_summary.get(s['id'], {}).get('가계약', 0)
                       for s in sites)

    role_label = sidebar.ROLE_LABELS.get(user['role'], user['role'])
    site_label = "담당 현장" if user['role'] == 'manager' else "전체 현장"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(site_label, len(sites), f"진행중 {len(active_sites)}개")
    c2.metric("재직 직원", f"{total_emp}명")
    c3.metric("계약률(가계약 포함)", f"{total_signed / total_units * 100:.1f}%" if total_units else "-",
              f"{total_signed:,} / {total_units:,}세대" if total_units else None)
    c4.metric("내 권한", role_label)

    if not sites:
        st.info("등록된 현장이 없습니다. 현장 관리 메뉴에서 현장을 추가하세요.")
        return

    st.markdown("### 현장 현황")
    rows = []
    for s in sites:
        summary = unit_summary.get(s['id'], {})
        total = sum(summary.values())
        contracted = summary.get('계약', 0)
        pre = summary.get('가계약', 0)
        rows.append({
            '현장명': s['name'], '지역': s['region'], '시작일': s['start_date'], '상태': s['status'],
            '재직 인원': s['employee_count'],
            '총세대': total or None,
            '계약': contracted if total else None,
            '가계약': pre if total else None,
            '공실': summary.get('공실', 0) if total else None,
            '누적 해지': cancel_counts.get(s['id'], 0),
            '계약률(%)': round((contracted + pre) / total * 100, 1) if total else None,
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            '계약률(%)': st.column_config.ProgressColumn('계약률', format="%.1f%%", min_value=0, max_value=100),
        },
    )


if 'user' not in st.session_state:
    login_page()
else:
    main_page()
