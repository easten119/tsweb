"""현황판 탭 — 엑셀 계약현황판 구도 + 클릭 시 호실 카드"""
import streamlit as st

import board
import db
import templates
from ui import common as cm
from ui import unit_card


def board_options(cfg):
    return dict(colors=templates.status_colors(cfg), statuses=templates.status_names(cfg),
                floor_groups=cfg.get('floor_groups') or None)


def render(ctx):
    site, site_id, cfg = ctx['site'], ctx['site_id'], ctx['cfg']
    complexes = db.get_complexes(site_id)
    if not complexes:
        st.info("등록된 호실이 없습니다. 설정 탭 > 호실 등록에서 호실 목록을 올리세요.")
        return
    all_units = db.get_units(site_id=site_id)
    labels = db.get_floor_labels(site_id)
    customers = {c['unit_id']: c['customer_name'] for c in db.get_contracts(site_id=site_id, active_only=True)}

    c1, c2, c3, _ = st.columns([1, 1, 1.4, 2])
    type_filter = c1.selectbox("타입 강조", ["전체"] + sorted({u['type'] for u in all_units if u.get('type')}),
                               key=f"bd_type_{site_id}")
    if len(complexes) > 1:
        cx_id = c2.selectbox("단지", [c['id'] for c in complexes], key=f"bd_cx_{site_id}",
                             format_func=lambda i: next(c['complex_name'] for c in complexes if c['id'] == i))
    else:
        cx_id = complexes[0]['id']
    cx = next(c for c in complexes if c['id'] == cx_id)
    buildings = db.get_buildings(site_id=site_id, complex_id=cx_id)
    units = [u for u in all_units if u['complex_id'] == cx_id]
    bsite = {**site, 'name': site['name'] if len(complexes) == 1 else f"{site['name']} {cx['complex_name']}"}
    opts = board_options(cfg)

    c3.download_button("인쇄용 현황판 (HTML)", icon=":material/print:",
                       data=board.board_html(bsite, buildings, units, labels, customers, standalone=True,
                                             **opts).encode('utf-8'),
                       file_name=f"{bsite['name']}_동호수현황판.html", mime="text/html")

    sel = st.session_state.get(unit_card.STATE_KEY)
    clicked = board.render_board(bsite, buildings, units, labels, customers, sel_uid=sel,
                                 type_filter=None if type_filter == "전체" else type_filter,
                                 key=f"board_{site_id}_{cx_id}", **opts)
    if clicked and clicked != sel:
        unit_card.open_card(clicked)
        st.rerun()
    st.caption("호실을 클릭하면 아래에 호실 카드가 열립니다. 마우스를 올리면 계약자명이 보입니다.")

    sel = st.session_state.get(unit_card.STATE_KEY)
    if sel:
        unit_card.render(ctx, sel)
