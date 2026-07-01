import streamlit as st

_ROLE_LABELS = {'admin': '관리자', 'manager': '현장담당자', 'viewer': '뷰어'}


def get_accessible_sites(user, all_sites):
    """manager는 배정된 현장만, admin/viewer는 전체 반환."""
    if user.get('role') == 'manager':
        allowed_ids = set(user.get('site_ids', []))
        return [s for s in all_sites if s['id'] in allowed_ids]
    return list(all_sites)


def require_login():
    """미로그인 시 안내 메시지와 메인 페이지 이동 버튼을 표시하고 실행을 중단한다."""
    if 'user' not in st.session_state:
        st.error("로그인이 필요합니다. 세션이 만료되었거나 직접 URL로 접근하셨습니다.")
        st.page_link("app.py", label="🏠 메인 페이지로 이동")
        st.stop()


def render_sidebar(user):
    role = user.get('role', 'viewer')
    with st.sidebar:
        st.markdown(f"### 👤 {user['username']}")
        st.caption(f"권한: {_ROLE_LABELS.get(role, role)}")

        if role in ('admin', 'manager'):
            st.markdown("---")
            st.markdown("**🏗️ 근태관리**")
            st.page_link("pages/1_출근현황.py", label="📊 출근 현황")
            st.page_link("pages/2_직원관리.py", label="👷 직원 관리")
            st.page_link("pages/3_출근입력.py", label="📅 출근 입력")

        st.markdown("---")
        st.markdown("**📋 계약현황**")
        st.page_link("pages/4_동호수현황.py", label="🏢 동호수 현황")
        if role in ('admin', 'manager'):
            st.page_link("pages/5_입출금등록.py", label="💰 입출금 등록")
        st.page_link("pages/6_입출금리스트.py", label="📃 입출금 리스트")
        if role in ('admin', 'manager'):
            st.page_link("pages/7_계약등록.py", label="✏️ 계약 등록")
        st.page_link("pages/8_계약리스트.py", label="📋 계약 리스트")
        st.page_link("pages/9_호실별현황.py", label="🔍 호실별 현황")
        if role in ('admin', 'manager'):
            st.page_link("pages/10_해지.py", label="❌ 해지")
        st.page_link("pages/11_해지리스트.py", label="📋 해지 리스트")

        if role in ('admin', 'manager'):
            st.markdown("---")
            st.markdown("**💰 자금집행**")
            st.page_link("pages/12_일비정산.py", label="💴 일비 정산")
            st.page_link("pages/13_숙소비정산.py", label="🏠 숙소비 정산")
            st.page_link("pages/14_정산대장.py", label="📋 정산 대장")
            st.page_link("pages/15_기본정산.py", label="📊 기본 정산")
            st.page_link("pages/16_수수료.py", label="💳 수수료")

        if role == 'admin':
            st.markdown("---")
            st.page_link("pages/17_현장관리.py", label="📍 현장 관리")
            st.page_link("pages/18_사용자관리.py", label="🔑 사용자 관리")

        st.markdown("---")
        if st.button("로그아웃", use_container_width=True):
            del st.session_state['user']
            st.rerun()
