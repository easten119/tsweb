import streamlit as st
import db
import sidebar

st.set_page_config(
    page_title="TAESUNG WEB",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()


def login_page():
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("## 🏗️ TAESUNG WEB")
        st.markdown("---")
        with st.form("login_form"):
            username = st.text_input("아이디", placeholder="아이디를 입력하세요")
            password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
            submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")

            if submitted:
                user = db.authenticate_user(username, password)
                if user:
                    st.session_state.user = dict(user)
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

        st.caption("초기 관리자: admin / admin1234")


def main_page():
    user = st.session_state.user
    sidebar.render_sidebar(user)

    # Main dashboard
    st.title("🏗️ TAESUNG WEB")
    st.markdown("---")

    all_sites = db.get_all_sites()
    sites = sidebar.get_accessible_sites(user, all_sites)
    active_sites = [s for s in sites if s['status'] == '진행중']
    total_emp = sum(s['employee_count'] for s in sites)

    role_label = {'admin': '관리자', 'manager': '현장담당자', 'viewer': '뷰어'}.get(user['role'], user['role'])
    site_label = "담당 현장" if user['role'] == 'manager' else "전체 현장"
    col1, col2, col3 = st.columns(3)
    col1.metric(site_label, len(sites), f"진행중 {len(active_sites)}개")
    col2.metric("재직 직원", f"{total_emp}명")
    col3.metric("내 권한", role_label)

    if sites:
        st.markdown("### 현장 현황")
        import pandas as pd
        unit_summary = db.get_all_site_unit_summary()  # {site_id: {status: count}}

        rows = []
        for s in sites:
            summary = unit_summary.get(s['id'], {})
            total        = sum(summary.values())
            contracted   = summary.get('계약', 0)
            pre_contract = summary.get('가계약', 0)

            if total > 0:
                rate = f"{(contracted + pre_contract) / total * 100:.1f}%"
                rows.append({
                    '현장명':    s['name'],
                    '지역':      s['region'],
                    '시작일':    s['start_date'],
                    '상태':      s['status'],
                    '재직 인원': s['employee_count'],
                    '총세대':    total,
                    '계약':      contracted,
                    '가계약':    pre_contract,
                    '계약률':    rate,
                })
            else:
                rows.append({
                    '현장명':    s['name'],
                    '지역':      s['region'],
                    '시작일':    s['start_date'],
                    '상태':      s['status'],
                    '재직 인원': s['employee_count'],
                    '총세대':    '-',
                    '계약':      '-',
                    '가계약':    '-',
                    '계약률':    '-',
                })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("등록된 현장이 없습니다. 현장 관리 메뉴에서 현장을 추가하세요.")


if 'user' not in st.session_state:
    login_page()
else:
    main_page()
