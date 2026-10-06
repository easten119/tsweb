"""
sidebar.py — 페이지 공통 처리 (로그인·권한·사이드바·현장/동/호실 선택·금액 입력 헬퍼)

모든 페이지는 맨 위에서 page_setup()을 호출한다:
    user = sidebar.page_setup("출근 현황", "📊", roles=('admin', 'manager'))
"""
import streamlit as st
import db

ROLE_LABELS = {'admin': '관리자', 'manager': '현장담당자', 'viewer': '뷰어'}
_ROLE_LABELS = ROLE_LABELS  # 구버전 호환
EDIT_ROLES = ('admin', 'manager')
MIN_PASSWORD_LEN = 8


# ===================================================================
# 로그인 / 권한
# ===================================================================

def require_login():
    if 'user' not in st.session_state:
        st.error("로그인이 필요합니다. 세션이 만료되었거나 새로고침·직접 URL로 접근하셨습니다.")
        st.page_link("app.py", label="🏠 로그인 페이지로 이동")
        st.stop()


def require_role(user, roles):
    if roles and user.get('role') not in roles:
        st.error("이 메뉴에 접근할 권한이 없습니다.")
        st.stop()


def can_edit(user):
    return user.get('role') in EDIT_ROLES


def page_setup(title, icon, roles=None, wide=True):
    """set_page_config + 로그인/권한 확인 + 사이드바 + 비밀번호 강제변경. user 반환."""
    st.set_page_config(page_title=title, page_icon=icon, layout="wide" if wide else "centered")
    require_login()
    user = st.session_state.user
    require_role(user, roles)
    render_sidebar(user)
    if user.get('must_change_password'):
        force_password_change(user)
    st.title(f"{icon} {title}")
    return user


def password_problem(pw1, pw2):
    if not pw1:
        return "새 비밀번호를 입력하세요."
    if len(pw1) < MIN_PASSWORD_LEN:
        return f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다."
    if pw1 == db.DEFAULT_ADMIN_PASSWORD:
        return "초기 비밀번호는 사용할 수 없습니다."
    if pw1 != pw2:
        return "비밀번호가 일치하지 않습니다."
    return None


def force_password_change(user):
    st.warning("🔒 초기 비밀번호로 로그인했습니다. 계속하려면 비밀번호를 변경하세요.")
    with st.form("force_pw_form"):
        pw1 = st.text_input("새 비밀번호", type="password")
        pw2 = st.text_input("새 비밀번호 확인", type="password")
        if st.form_submit_button("변경", type="primary"):
            problem = password_problem(pw1, pw2)
            if problem:
                st.error(problem)
            else:
                db.update_user_password(user['id'], pw1)
                user['must_change_password'] = False
                st.success("변경되었습니다.")
                st.rerun()
    st.stop()


# ===================================================================
# 사이드바
# ===================================================================

def render_sidebar(user):
    role = user.get('role', 'viewer')
    editor = role in EDIT_ROLES
    with st.sidebar:
        st.markdown(f"### 👤 {user['username']}")
        st.caption(f"권한: {ROLE_LABELS.get(role, role)}")
        st.page_link("app.py", label="🏠 대시보드")

        if editor:
            st.markdown("---")
            st.markdown("**🏗️ 근태관리**")
            st.page_link("pages/1_출근현황.py", label="📊 출근 현황")
            st.page_link("pages/2_직원관리.py", label="👷 직원 관리")
            st.page_link("pages/3_출근입력.py", label="📅 출근 입력")

        st.markdown("---")
        st.markdown("**📋 계약현황**")
        st.page_link("pages/4_동호수현황.py", label="🏢 동호수 현황")
        if editor:
            st.page_link("pages/5_입출금등록.py", label="💰 입출금 등록")
        st.page_link("pages/6_입출금리스트.py", label="📃 입출금 리스트")
        if editor:
            st.page_link("pages/7_계약등록.py", label="✏️ 계약 등록")
        st.page_link("pages/8_계약리스트.py", label="📋 계약 리스트")
        st.page_link("pages/9_호실별현황.py", label="🔍 호실별 현황")
        if editor:
            st.page_link("pages/10_해지.py", label="❌ 해지")
        st.page_link("pages/11_해지리스트.py", label="📋 해지 리스트")

        if editor:
            st.markdown("---")
            st.markdown("**💰 자금집행**")
            st.page_link("pages/12_일비정산.py", label="💴 일비 정산")
            st.page_link("pages/13_숙소비정산.py", label="🏠 숙소비 정산")
            st.page_link("pages/14_정산대장.py", label="📋 정산 대장")
            st.page_link("pages/15_기본정산.py", label="📊 기본 정산")
            st.page_link("pages/16_수수료.py", label="💳 수수료")

        if role == 'admin':
            st.markdown("---")
            st.markdown("**⚙️ 관리**")
            st.page_link("pages/17_현장관리.py", label="📍 현장 관리")
            st.page_link("pages/18_사용자관리.py", label="🔑 사용자 관리")
            st.page_link("pages/19_데이터점검.py", label="🩺 데이터 점검")

        st.markdown("---")
        with st.expander("🔒 내 비밀번호 변경"):
            with st.form("self_pw_form", clear_on_submit=True):
                cur_pw = st.text_input("현재 비밀번호", type="password")
                pw1 = st.text_input("새 비밀번호", type="password")
                pw2 = st.text_input("새 비밀번호 확인", type="password")
                if st.form_submit_button("변경"):
                    if not db.authenticate_user(user['username'], cur_pw):
                        st.error("현재 비밀번호가 올바르지 않습니다.")
                    elif (problem := password_problem(pw1, pw2)):
                        st.error(problem)
                    else:
                        db.update_user_password(user['id'], pw1)
                        user['must_change_password'] = False
                        st.success("변경되었습니다.")
        if st.button("로그아웃", width="stretch"):
            st.session_state.clear()
            st.rerun()


# ===================================================================
# 현장 / 동 / 호실 선택
# ===================================================================

def get_accessible_sites(user, all_sites):
    """manager는 배정된 현장만, admin/viewer는 전체."""
    if user.get('role') == 'manager':
        allowed = set(user.get('site_ids', []))
        return [s for s in all_sites if s['id'] in allowed]
    return list(all_sites)


def accessible_site_ids(user):
    """manager → 담당 현장 id 목록 / admin·viewer → None(제한 없음)."""
    if user.get('role') == 'manager':
        return list(user.get('site_ids', []))
    return None


def select_site(user, key="site_sel", label="현장 선택", allow_all=False, container=None):
    """접근 가능한 현장 선택. allow_all이면 '전체'(None) 선택지 포함.
    반환: (site_id 또는 None, site dict 또는 None, 접근가능 현장 목록)"""
    sites = get_accessible_sites(user, db.get_all_sites())
    if not sites:
        st.error("담당 현장이 배정되지 않았습니다. 관리자에게 문의하세요.")
        st.stop()
    box = container or st
    if len(sites) == 1 and not allow_all:
        box.caption(f"현장: **{sites[0]['name']}**")
        return sites[0]['id'], sites[0], sites
    options = ([None] if allow_all else []) + [s['id'] for s in sites]
    by_id = {s['id']: s for s in sites}
    # 페이지를 옮겨 다녀도 마지막 선택 현장을 유지
    last = st.session_state.get('_last_site_id')
    if key not in st.session_state and last in options:
        st.session_state[key] = last
    sid = box.selectbox(label, options, key=key,
                        format_func=lambda i: '전체' if i is None else
                        f"{by_id[i]['name']}" + ("" if by_id[i]['status'] == '진행중' else " (완료)"))
    if sid is not None:
        st.session_state['_last_site_id'] = sid
    return sid, by_id.get(sid), sites


def building_label(b, multi_complex):
    return f"{b['complex_name']} {b['building_no']}동" if multi_complex else f"{b['building_no']}동"


def select_building(site_id, key="bld_sel", label="동 선택", container=None, include_all=False):
    """동 선택 (단지가 여러 개면 '단지명 동' 형태로 구분). 반환: building_id 또는 None(전체)."""
    buildings = db.get_buildings(site_id=site_id)
    if not buildings:
        if include_all:
            return None, []
        st.info("등록된 동이 없습니다. 현장 관리 > 호실 일괄 업로드에서 등록하세요.")
        st.stop()
    multi = len({b['complex_id'] for b in buildings}) > 1
    by_id = {b['id']: b for b in buildings}
    options = ([None] if include_all else []) + list(by_id)
    box = container or st
    bid = box.selectbox(label, options, key=key,
                        format_func=lambda i: '전체' if i is None else building_label(by_id[i], multi))
    return bid, buildings


def select_unit(units, key="unit_sel", label="호수 선택", container=None, show_status=True):
    by_id = {u['id']: u for u in units}
    box = container or st
    uid = box.selectbox(
        label, list(by_id), key=key,
        format_func=lambda i: f"{by_id[i]['unit_no']}" + (f"  ({by_id[i]['status']})" if show_status else ""))
    return by_id[uid]


def unit_title(u):
    return f"{u.get('complex_name') or ''} {u.get('building_no') or ''}동 {u.get('unit_no') or ''}".strip()


# ===================================================================
# 직원 표시
# ===================================================================

def employee_labels(employees):
    """{emp_id: 표시이름}. 동명이인은 팀·연락처 끝자리로 구분한다."""
    from collections import Counter
    counts = Counter(e['name'] for e in employees)
    labels = {}
    for e in employees:
        if counts[e['name']] > 1:
            tail = (e.get('phone') or '')[-4:]
            extra = " / ".join(x for x in [e.get('team') or '', tail and f"☎{tail}"] if x)
            labels[e['id']] = f"{e['name']} ({extra or '#' + str(e['id'])})"
        else:
            labels[e['id']] = e['name']
    if len(set(labels.values())) < len(labels):  # 그래도 겹치면 id 부착
        labels = {k: f"{v} #{k}" for k, v in labels.items()}
    return labels


# ===================================================================
# 금액 입력 / 알림
# ===================================================================

def fmt_amount_key(key):
    """on_change 콜백: 입력값을 천단위 콤마로 정리."""
    cleaned = str(st.session_state.get(key, "")).replace(",", "").replace(" ", "")
    if cleaned.isdigit():
        st.session_state[key] = f"{int(cleaned):,}"


def parse_amount(text):
    """'1,000' → 1000, 빈칸 → 0, 숫자 외 문자 → None"""
    cleaned = str(text or "").replace(",", "").replace(" ", "").replace("원", "")
    if not cleaned:
        return 0
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def flash(msg, kind="success"):
    """rerun 후에도 보이는 알림 메시지 예약."""
    st.session_state['_flash'] = (kind, msg)


def show_flash():
    item = st.session_state.pop('_flash', None)
    if item:
        getattr(st, item[0])(item[1])


def excel_bytes(sheets):
    """{시트명: DataFrame} → xlsx bytes"""
    import io
    import pandas as pd
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
            ws = writer.sheets[name[:31]]
            for col_cells in ws.columns:
                width = max(len(str(c.value or '')) for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(8, width * 1.6), 40)
    return buf.getvalue()


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
