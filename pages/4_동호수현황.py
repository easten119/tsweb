import math
import pandas as pd
import streamlit as st
import db
import sidebar
import views

user = sidebar.page_setup("동호수 현황", "🏢")

site_id, site, _ = sidebar.select_site(user)

# ── 상단 요약 ─────────────────────────────────────────────────────
summary = db.get_unit_status_summary(site_id)
total = sum(summary.values())
signed = summary.get('계약', 0) + summary.get('가계약', 0)
m = st.columns(6)
m[0].metric("총 세대", f"{total:,}")
m[1].metric("계약", f"{summary.get('계약', 0):,}")
m[2].metric("가계약", f"{summary.get('가계약', 0):,}")
m[3].metric("공실", f"{summary.get('공실', 0):,}")
m[4].metric("계약률", f"{signed / total * 100:.1f}%" if total else "-")
m[5].metric("누적 해지", f"{db.get_cancel_counts_by_site().get(site_id, 0):,}건")

STATUS_STYLE = {
    "공실":   "background-color:#FFFFFF;color:#333333",
    "가계약": "background-color:#4A90D9;color:#FFFFFF;font-weight:600",
    "계약":   "background-color:#E74C3C;color:#FFFFFF;font-weight:600",
}
DIM_STYLE = {
    "공실":   "background-color:#FFFFFF;color:#CCCCCC",
    "가계약": "background-color:#D6E6F7;color:#7FA7D6",
    "계약":   "background-color:#F7D3CF;color:#D98880",
}
EMPTY_STYLE = "background-color:#EEEEEE;color:#BBBBBB"
TYPE_STYLE = "background-color:#F7F7F7;color:#666666;font-size:11px"

st.markdown(
    '<div style="display:flex;gap:14px;align-items:center;margin:6px 0;font-size:13px;">'
    '<span style="display:inline-block;width:14px;height:14px;background:#FFF;border:1px solid #aaa"></span>공실'
    '<span style="display:inline-block;width:14px;height:14px;background:#4A90D9"></span>가계약'
    '<span style="display:inline-block;width:14px;height:14px;background:#E74C3C"></span>계약'
    '<span style="display:inline-block;width:14px;height:14px;background:#EEE;border:1px solid #ccc"></span>없는 호실(✕)'
    '<span style="color:#888">· 호실을 클릭하면 아래에 상세가 열립니다</span></div>',
    unsafe_allow_html=True,
)

f1, f2 = st.columns([1, 3])
type_filter = f1.selectbox("타입 강조", ["전체"] + sorted({u['type'] for u in db.get_units(site_id=site_id) if u.get('type')}))
st.divider()


def parse_unit_no(unit_no):
    """'4601' → (46, 1). 숫자 3자리 이상만 인식."""
    s = str(unit_no).strip()
    if len(s) >= 3 and s.isdigit():
        return int(s[:-2]), int(s[-2:])
    return None, None


def _select_cb(key, grid):
    """셀 클릭 시 선택 호실 id를 기억한다."""
    state = st.session_state.get(key)
    try:
        cells = state.selection.cells
    except AttributeError:
        cells = (state or {}).get('selection', {}).get('cells', [])
    if cells:
        uid = grid.get((int(cells[0][0]), str(cells[0][1])))
        if uid:
            st.session_state['_board_unit'] = uid


def render_building(bld, units):
    parsed = []
    for u in units:
        f, l = parse_unit_no(u['unit_no'])
        if f is not None:
            parsed.append((f, l, u))
    st.markdown(f"<div style='text-align:center;font-weight:700;background:#dee2e6;border-radius:4px;"
                f"padding:3px 0;margin-bottom:4px'>{bld['building_no']}동</div>", unsafe_allow_html=True)
    if not parsed:
        st.caption("호실 없음")
        return
    unparsed = len(units) - len(parsed)
    max_floor = max(p[0] for p in parsed)
    lines = sorted({p[1] for p in parsed})
    umap = {(f, l): u for f, l, u in parsed}
    cols = [f"{l}라인" for l in lines]
    floors = list(range(max_floor, 0, -1))

    data, styles, grid = [], [], {}
    for ri, f in enumerate(floors):
        row, srow = [], []
        for l, col in zip(lines, cols):
            u = umap.get((f, l))
            if u:
                row.append(u['unit_no'])
                dim = type_filter != "전체" and u.get('type') != type_filter
                palette = DIM_STYLE if dim else STATUS_STYLE
                srow.append(palette.get(u['status'], palette['공실']))
                grid[(ri, col)] = u['id']
            else:
                row.append("✕")
                srow.append(EMPTY_STYLE)
        data.append(row)
        styles.append(srow)
    # 라인별 타입 행
    type_row = []
    for l in lines:
        ts = []
        for f in floors:
            t = (umap.get((f, l)) or {}).get('type')
            if t and t not in ts:
                ts.append(t)
        type_row.append("/".join(ts[:2]))
    data.append(type_row)
    styles.append([TYPE_STYLE] * len(lines))

    df = pd.DataFrame(data, columns=cols, index=[f"{f}F" for f in floors] + ["타입"])
    style_df = pd.DataFrame(styles, columns=cols, index=df.index)
    key = f"grid_{bld['id']}"
    row_h = 27
    st.dataframe(
        df.style.apply(lambda _: style_df, axis=None),
        key=key, on_select=lambda k=key, g=grid: _select_cb(k, g), selection_mode="single-cell",
        width="content", height=(len(df) + 1) * (row_h + 1) + 10, row_height=row_h,
        column_config={c: st.column_config.TextColumn(c, width=58) for c in cols},
    )
    if unparsed:
        st.caption(f"⚠️ 호수 형식을 인식하지 못한 호실 {unparsed}개 (예: 4601 형식이어야 함)")


def render_complex(cx):
    buildings = db.get_buildings(site_id=site_id, complex_id=cx['id'])
    if not buildings:
        st.info("등록된 동이 없습니다.")
        return
    units = db.get_units(site_id=site_id, complex_id=cx['id'])
    by_bld = {}
    for u in units:
        by_bld.setdefault(u['building_id'], []).append(u)
    n = len(buildings)
    per_row = n if n <= 4 else math.ceil(n / 2)
    for start in range(0, n, per_row):
        row_blds = buildings[start:start + per_row]
        cols = st.columns(per_row)
        for col, b in zip(cols, row_blds):
            with col:
                render_building(b, by_bld.get(b['id'], []))


complexes = db.get_complexes(site_id)
if not complexes:
    st.info("등록된 단지가 없습니다. 현장 관리 > 호실 일괄 업로드에서 데이터를 업로드하세요.")
    st.stop()

if len(complexes) > 1:
    for tab, cx in zip(st.tabs([cx['complex_name'] for cx in complexes]), complexes):
        with tab:
            render_complex(cx)
else:
    render_complex(complexes[0])

# ── 목록에서 직접 선택 (현황판 대신) ────────────────────────────────
with st.expander("🔎 동/호수로 찾기"):
    c1, c2 = st.columns(2)
    bid, _ = sidebar.select_building(site_id, key="board_bld", container=c1)
    bunits = db.get_units(site_id=site_id, building_id=bid)
    if bunits:
        u = sidebar.select_unit(bunits, key="board_unit_sel", container=c2)
        if st.button("상세 보기"):
            st.session_state['_board_unit'] = u['id']
            st.rerun()

# ── 선택 호실 상세 ─────────────────────────────────────────────────
sel_id = st.session_state.get('_board_unit')
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
