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


def _site_rows(sites, unit_summary, cancel_counts):
    rows = []
    for s in sites:
        summary = unit_summary.get(s['id'], {})
        total = sum(summary.values())
        contracted = summary.get('계약', 0)
        pre = summary.get('가계약', 0)
        rows.append({
            '현장명': s['name'], '지역': s['region'], '시작일': s['start_date'],
            '재직 인원': s['employee_count'],
            '총세대': total or None,
            '계약': contracted if total else None,
            '가계약': pre if total else None,
            '공실': summary.get('공실', 0) if total else None,
            '누적 해지': cancel_counts.get(s['id'], 0),
            '계약률(%)': round((contracted + pre) / total * 100, 1) if total else None,
        })
    return pd.DataFrame(rows)


def _site_table(df):
    st.dataframe(
        df, width="stretch", hide_index=True,
        column_config={
            '계약률(%)': st.column_config.ProgressColumn('계약률', format="%.1f%%", min_value=0, max_value=100),
        },
    )


def main_page():
    user = sidebar.page_setup("TAESUNG WEB", "🏗️")
    sidebar.show_flash()

    sites = sidebar.get_accessible_sites(user, db.get_all_sites())
    # 대시보드 지표는 진행중 현장만 집계 (완료 현장은 '완료 현장' 탭에서 별도 확인)
    active_sites = [s for s in sites if s['status'] == '진행중']
    done_sites = [s for s in sites if s['status'] != '진행중']

    unit_summary = db.get_all_site_unit_summary()
    cancel_counts = db.get_cancel_counts_by_site()
    total_emp = sum(s['employee_count'] for s in active_sites)
    total_units = sum(sum(unit_summary.get(s['id'], {}).values()) for s in active_sites)
    total_signed = sum(unit_summary.get(s['id'], {}).get('계약', 0) + unit_summary.get(s['id'], {}).get('가계약', 0)
                       for s in active_sites)

    role_label = sidebar.ROLE_LABELS.get(user['role'], user['role'])
    site_label = "진행중 담당 현장" if user['role'] == 'manager' else "진행중 현장"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(site_label, f"{len(active_sites)}개", f"완료 {len(done_sites)}개" if done_sites else None,
              delta_color="off")
    c2.metric("재직 직원 (진행중 현장)", f"{total_emp}명")
    c3.metric("계약률 (가계약 포함)", f"{total_signed / total_units * 100:.1f}%" if total_units else "-",
              f"{total_signed:,} / {total_units:,}세대" if total_units else None, delta_color="off")
    c4.metric("내 권한", role_label)

    if not sites:
        st.info("등록된 현장이 없습니다. 현장 관리 메뉴에서 현장을 추가하세요.")
        return

    st.markdown("### 현장 현황")
    tab_active, tab_done = st.tabs([f"🟢 진행중 현장 ({len(active_sites)})", f"⚪ 완료 현장 ({len(done_sites)})"])
    with tab_active:
        if active_sites:
            _site_table(_site_rows(active_sites, unit_summary, cancel_counts))
        else:
            st.info("진행중인 현장이 없습니다.")
    with tab_done:
        if done_sites:
            st.caption("현장 관리에서 상태를 '완료'로 바꾼 현장입니다. 상단 지표에는 포함되지 않습니다.")
            _site_table(_site_rows(done_sites, unit_summary, cancel_counts))
        else:
            st.info("완료된 현장이 없습니다.")


if 'user' not in st.session_state:
    login_page()
else:
    main_page()
