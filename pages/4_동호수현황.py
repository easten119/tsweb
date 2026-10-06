import streamlit as st
import db
import sidebar
import views
import board

user = sidebar.page_setup("동호수 현황", "🏢")

site_id, site, _ = sidebar.select_site(user)

complexes = db.get_complexes(site_id)
if not complexes:
    st.info("등록된 단지가 없습니다. 현장 관리 > 호실 일괄 업로드에서 데이터를 업로드하세요.")
    st.stop()

all_units = db.get_units(site_id=site_id)
labels = db.get_floor_labels(site_id)
customers = {c['unit_id']: c['customer_name'] for c in db.get_contracts(site_id=site_id, active_only=True)}

f1, f2, f3 = st.columns([1, 1, 2])
type_filter = f1.selectbox("타입 강조", ["전체"] + sorted({u['type'] for u in all_units if u.get('type')}))
if len(complexes) > 1:
    cx_id = f2.selectbox("단지", [c['id'] for c in complexes],
                         format_func=lambda i: next(c['complex_name'] for c in complexes if c['id'] == i))
else:
    cx_id = complexes[0]['id']

cx = next(c for c in complexes if c['id'] == cx_id)
buildings = db.get_buildings(site_id=site_id, complex_id=cx_id)
units = [u for u in all_units if u['complex_id'] == cx_id]
board_site = {**site, 'name': site['name'] if len(complexes) == 1 else f"{site['name']} {cx['complex_name']}"}

sel_id = st.session_state.get('_board_unit')
clicked = board.render_board(board_site, buildings, units, labels, customers, sel_uid=sel_id,
                             type_filter=None if type_filter == "전체" else type_filter, key=f"board_{site_id}_{cx_id}")
if clicked and clicked != sel_id:
    st.session_state['_board_unit'] = clicked
    st.rerun()

f3.download_button(
    "🖨️ 인쇄용 현황판 받기 (브라우저에서 열어 인쇄)",
    data=board.board_html(board_site, buildings, units, labels, customers, standalone=True).encode('utf-8'),
    file_name=f"{board_site['name']}_동호수현황판.html", mime="text/html")
st.caption("호실을 클릭하면 아래에 상세가 열립니다. 마우스를 올리면 계약자명이 보입니다. "
           "층 이름(근린생활시설·스카이라운지 등)은 현장 관리 > 층 표시 설정에서 바꿉니다.")

with st.expander("🔎 동/호수로 찾기"):
    c1, c2 = st.columns(2)
    bid, _ = sidebar.select_building(site_id, key="board_bld", container=c1)
    bunits = db.get_units(site_id=site_id, building_id=bid)
    if bunits:
        u = sidebar.select_unit(bunits, key="board_unit_sel", container=c2)
        if st.button("상세 보기"):
            st.session_state['_board_unit'] = u['id']
            st.rerun()

unit = db.get_unit(sel_id) if sel_id else None
if unit and unit['site_id'] == site_id:
    st.divider()
    t_col, x_col = st.columns([9, 1])
    with t_col:
        st.subheader(f"🔍 {sidebar.unit_title(unit)}")
    if x_col.button("✕ 닫기"):
        st.session_state.pop('_board_unit', None)
        st.rerun()
    views.render_unit_detail(unit, show_title=False)
