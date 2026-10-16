"""ui/layout.py — 앱 골격: 전역 CSS, 좌측 내비게이션, 현장 헤더"""
import html

import streamlit as st

import db
import templates
from ui import common as cm

CSS = """
<style>
/* 본문 밀도: 실무용 CRM처럼 여백을 줄인다 */
.block-container { padding-top: 1.1rem; padding-bottom: 2rem; max-width: 100%; }
h1, h2, h3 { letter-spacing: -0.2px; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #DDE2E9; border-radius:4px; padding:8px 12px; }
div[data-testid="stMetricLabel"] p { font-size:12px; color:#5B6575; }
.ts-crumb { font-size:12px; color:#6B7686; margin-bottom:2px; }
.ts-title { font-size:22px; font-weight:700; color:#111827; margin:0 0 2px 0; }
.ts-meta { font-size:12px; color:#6B7686; margin-bottom:10px; }
.ts-meta .tag { display:inline-block; border:1px solid #CBD3DE; border-radius:3px; padding:0 6px; margin-right:6px;
                background:#fff; color:#374151; }
.ts-kpis { display:flex; flex-wrap:wrap; border:1px solid #DDE2E9; background:#fff; border-radius:4px; margin-bottom:10px; }
.ts-kpi { flex:1; padding:8px 14px; border-right:1px solid #EEF1F5; min-width:90px; }
.ts-kpi:last-child { border-right:none; }
.ts-kpi .l { font-size:11px; color:#6B7686; }
.ts-kpi .v { font-size:18px; font-weight:700; color:#111827; }
.ts-kpi .v small { font-size:12px; font-weight:500; color:#6B7686; margin-left:2px; }
.ts-dot { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:4px; vertical-align:0; }
.ts-section { font-size:14px; font-weight:700; color:#1F2937; border-left:3px solid #1F4E8C; padding-left:8px;
              margin:14px 0 6px 0; }
/* 사이드바 */
section[data-testid="stSidebar"] .ts-brand { color:#fff; font-weight:800; font-size:17px; letter-spacing:2px; }
section[data-testid="stSidebar"] .ts-brand-sub { color:#8A99AE; font-size:11px; margin-bottom:6px; }
section[data-testid="stSidebar"] .ts-nav-h { color:#7E8DA3; font-size:11px; font-weight:700; letter-spacing:.5px;
              margin:14px 0 4px 2px; line-height:1.4; }
section[data-testid="stSidebar"] button[kind="tertiary"] { justify-content:flex-start; padding:3px 8px;
              color:#C9D3E0; width:100%; }
section[data-testid="stSidebar"] button[kind="tertiary"] > div { justify-content:flex-start; width:100%; }
section[data-testid="stSidebar"] button[kind="tertiary"] p { text-align:left; font-size:13px; }
section[data-testid="stSidebar"] button[kind="tertiary"]:hover { background:#223045; color:#fff; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.25rem; }
section[data-testid="stSidebar"] button[kind="secondary"] { justify-content:flex-start; }
/* 탭 */
div[data-baseweb="tab-list"] { gap: 2px; border-bottom:1px solid #D5DBE3; }
button[data-baseweb="tab"] { padding: 6px 14px; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ── 내비게이션 ────────────────────────────────────────────────────
def go(view, site_id=None, tab=None):
    st.session_state['view'] = view
    if site_id is not None:
        st.session_state['site_id'] = site_id
    if tab:
        st.session_state['site_tab'] = tab
    st.rerun()


def _nav_button(label, key, active=False, icon=None):
    return st.button(("▸ " if active else "") + label, key=key, type="tertiary", icon=icon, width="stretch")


def render_sidebar(user):
    view = st.session_state.get('view', 'dashboard')
    cur_site = st.session_state.get('site_id')
    sites = cm.accessible_sites(user)
    active = [s for s in sites if s['status'] == '진행중']
    done = [s for s in sites if s['status'] != '진행중']
    with st.sidebar:
        st.markdown("<div class='ts-brand'>TAESUNG</div><div class='ts-brand-sub'>분양현장 통합관리</div>",
                    unsafe_allow_html=True)
        if _nav_button("대시보드", "nav_dash", view == 'dashboard', ":material/space_dashboard:"):
            go('dashboard')

        st.markdown("<div class='ts-nav-h'>진행중 현장</div>", unsafe_allow_html=True)
        if not active:
            st.caption("없음")
        for s in active:
            if _nav_button(s['name'], f"nav_site_{s['id']}", view == 'site' and cur_site == s['id'],
                           ":material/apartment:"):
                go('site', s['id'])
        if done:
            with st.expander(f"완료 현장 ({len(done)})"):
                for s in done:
                    if _nav_button(s['name'], f"nav_site_{s['id']}", view == 'site' and cur_site == s['id']):
                        go('site', s['id'])

        if cm.is_admin(user):
            st.markdown("<div class='ts-nav-h'>관리</div>", unsafe_allow_html=True)
            for v, label, icon in (('admin_sites', '현장 관리', ':material/domain_add:'),
                                   ('admin_users', '사용자 관리', ':material/manage_accounts:'),
                                   ('admin_check', '데이터 점검', ':material/fact_check:')):
                if _nav_button(label, f"nav_{v}", view == v, icon):
                    go(v)

        st.markdown("<div class='ts-nav-h'>계정</div>", unsafe_allow_html=True)
        st.caption(f"{user['username']} · {cm.ROLE_LABELS.get(user['role'], user['role'])}")
        with st.popover("비밀번호 변경", width="stretch"):
            with st.form("self_pw_form", clear_on_submit=True):
                cur_pw = st.text_input("현재 비밀번호", type="password")
                pw1 = st.text_input("새 비밀번호", type="password")
                pw2 = st.text_input("새 비밀번호 확인", type="password")
                if st.form_submit_button("변경", type="primary"):
                    if not db.authenticate_user(user['username'], cur_pw):
                        st.error("현재 비밀번호가 올바르지 않습니다.")
                    elif (problem := cm.password_problem(pw1, pw2)):
                        st.error(problem)
                    else:
                        db.update_user_password(user['id'], pw1)
                        user['must_change_password'] = False
                        st.success("변경되었습니다.")
        if st.button("로그아웃", width="stretch", icon=":material/logout:"):
            st.session_state.clear()
            st.rerun()


# ── 현장 헤더 ─────────────────────────────────────────────────────
def site_kpis(site, cfg, units_summary, extra=None):
    names = templates.status_names(cfg)
    colors = templates.status_colors(cfg)
    total = sum(units_summary.values())
    signed = sum(units_summary.get(n, 0) for n in names)
    items = [("총 세대", f"{total:,}", "")]
    for n in names:
        items.append((f"<span class='ts-dot' style='background:{colors[n][0]}'></span>{html.escape(n)}",
                      f"{units_summary.get(n, 0):,}", ""))
    items.append(("공실", f"{units_summary.get('공실', 0):,}", ""))
    items.append(("계약률", f"{signed / total * 100:.1f}" if total else "-", "%" if total else ""))
    for label, value, unit in (extra or []):
        items.append((label, value, unit))
    cells = "".join(f"<div class='ts-kpi'><div class='l'>{l}</div><div class='v'>{v}<small>{u}</small></div></div>"
                    for l, v, u in items)
    st.markdown(f"<div class='ts-kpis'>{cells}</div>", unsafe_allow_html=True)


def site_header(site, cfg):
    tmpl = templates.PRESETS.get(site.get('template') or '', {}).get('label', site.get('template') or '-')
    st.markdown(
        f"<div class='ts-crumb'>대시보드 / {'진행중' if site['status'] == '진행중' else '완료'} 현장</div>"
        f"<div class='ts-title'>{html.escape(site['name'])}</div>"
        f"<div class='ts-meta'><span class='tag'>{html.escape(site['region'] or '')}</span>"
        f"<span class='tag'>{html.escape(tmpl)}</span>"
        f"<span class='tag'>{'진행중' if site['status'] == '진행중' else '완료'}</span>"
        f"시작일 {html.escape(str(site.get('start_date') or '-'))}</div>",
        unsafe_allow_html=True)
