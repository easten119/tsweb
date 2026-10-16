"""ui/site.py — 현장 화면 (엑셀 시트처럼 탭으로 이동)"""
import importlib

import streamlit as st

import db
import templates
from ui import common as cm
from ui import layout

# (탭 이름, 모듈, 편집권한 필요 여부)
TABS = [
    ("현황판", "ui.tab_board", False),
    ("계약관리", "ui.tab_contracts", False),
    ("입출금", "ui.tab_tx", False),
    ("해지", "ui.tab_cancel", False),
    ("계좌현황", "ui.tab_accounts", False),
    ("실적", "ui.tab_stats", False),
    ("직원·근태", "ui.tab_staff", True),
    ("정산", "ui.tab_settle", True),
    ("설정", "ui.tab_settings", True),
]


def render(user, site_id):
    site = db.get_site(site_id) if site_id else None
    allowed = {s['id'] for s in cm.accessible_sites(user)}
    if not site or site['id'] not in allowed:
        st.warning("현장을 찾을 수 없거나 접근 권한이 없습니다.")
        if st.button("대시보드로"):
            layout.go('dashboard')
        return
    cfg = templates.load_config(site)
    editable = cm.can_edit(user)
    ctx = {'user': user, 'site': site, 'site_id': site['id'], 'cfg': cfg, 'editable': editable}

    layout.site_header(site, cfg)
    summary = db.get_unit_status_summary(site['id'])
    layout.site_kpis(site, cfg, summary, extra=[("재직 인원", f"{len(db.get_employees(site['id']))}", "명")])

    tabs = [t for t in TABS if editable or not t[2]]
    names = [t[0] for t in tabs]
    key = f"site_tabs_{site['id']}"
    want = st.session_state.pop('site_tab', None)
    if want in names:
        st.session_state[key] = want
    containers = st.tabs(names, key=key, on_change="rerun")
    current = st.session_state.get(key) or names[0]
    for (name, module, _), box in zip(tabs, containers):
        if name == current:
            with box:
                importlib.import_module(module).render(ctx)
