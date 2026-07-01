import math
import streamlit as st
import streamlit.components.v1 as components
import db
import sidebar

st.set_page_config(page_title="동호수 현황", page_icon="🏢", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("🏢 동호수 현황")

# ── 현장 선택 ────────────────────────────────────────────────────────
all_sites = db.get_all_sites()
if not all_sites:
    st.info("등록된 현장이 없습니다.")
    st.stop()

accessible = sidebar.get_accessible_sites(user, all_sites)
if not accessible:
    st.error("담당 현장이 배정되지 않았습니다. 관리자에게 문의하세요.")
    st.stop()
elif len(accessible) == 1:
    site_id = accessible[0]['id']
    st.caption(f"현장: **{accessible[0]['name']}**")
else:
    site_map = {s['name']: s['id'] for s in accessible}
    sel_site = st.selectbox("현장 선택", list(site_map.keys()), key="contract_site")
    site_id = site_map[sel_site]

# ── 상단 요약 지표 ────────────────────────────────────────────────────
summary = db.get_unit_status_summary(site_id)
total = sum(summary.values())
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("총 세대", f"{total:,}")
m2.metric("계약", f"{summary.get('계약', 0):,}")
m3.metric("가계약", f"{summary.get('가계약', 0):,}")
m4.metric("공실", f"{summary.get('공실', 0):,}")
m5.metric("해지", f"{summary.get('해지', 0):,}")

# ── 범례 ─────────────────────────────────────────────────────────────
st.markdown(
    '<div style="display:flex;gap:14px;align-items:center;margin:6px 0;font-size:13px;">'
    '<span style="display:inline-block;width:16px;height:16px;background:#FFFFFF;'
    'border:1px solid #aaa;vertical-align:middle;margin-right:3px"></span>공실&nbsp;&nbsp;'
    '<span style="display:inline-block;width:16px;height:16px;background:#4A90D9;'
    'vertical-align:middle;margin-right:3px"></span>가계약&nbsp;&nbsp;'
    '<span style="display:inline-block;width:16px;height:16px;background:#E74C3C;'
    'vertical-align:middle;margin-right:3px"></span>계약'
    '</div>',
    unsafe_allow_html=True,
)

st.divider()

# ── 선택된 호실 (URL 쿼리 파라미터) ─────────────────────────────────
sel_unit_id = st.query_params.get("unit_id")

# ═══════════════════════════════════════════════════════════════════
#  HTML 현황판 생성 로직
# ═══════════════════════════════════════════════════════════════════

STATUS_STYLE = {
    "공실":   ("#FFFFFF", "#333333"),
    "가계약": ("#4A90D9", "#FFFFFF"),
    "계약":   ("#E74C3C", "#FFFFFF"),
    "해지":   ("#FFFFFF", "#333333"),
}

CELL_W = 52
CELL_H = 28


def parse_unit_no(unit_no):
    try:
        s = str(unit_no).strip()
        if len(s) >= 3:
            return int(s[:-2]), int(s[-2:])
    except (ValueError, TypeError):
        pass
    return None, None


def _h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_building_block(bld, units, selected_uid):
    parsed = []
    for u in units:
        floor, line = parse_unit_no(u["unit_no"])
        if floor is not None:
            parsed.append({**u, "_f": floor, "_l": line})

    bld_no = _h(bld["building_no"])
    header = f'<div class="bh">{bld_no}동</div>'

    if not parsed:
        return (
            f'<div class="bb">{header}'
            f'<div style="color:#aaa;font-size:11px;text-align:center;padding:8px 0">호실 없음</div>'
            f'</div>'
        )

    max_floor = max(u["_f"] for u in parsed)
    floors = list(range(max_floor, 0, -1))  # 최고층~1층 전체
    lines  = sorted(set(u["_l"] for u in parsed))
    umap   = {(u["_f"], u["_l"]): u for u in parsed}
    floors_with_units = set(u["_f"] for u in parsed)

    rows_html = []
    for f in floors:
        cells = []
        floor_empty = f not in floors_with_units  # 이 층에 호실 데이터 자체가 없음
        for l in lines:
            if floor_empty:
                cells.append('<td class="ue"></td>')
            else:
                u = umap.get((f, l))
                if u:
                    status = u.get("status", "공실")
                    bg, fg = STATUS_STYLE.get(status, ("#FFFFFF", "#333"))
                    sel_cls = " sel" if str(u.get("id")) == str(selected_uid) else ""
                    uid_js  = str(u["id"])
                    title   = _h(f'{u["unit_no"]} ({status})')
                    label   = _h(u["unit_no"])
                    cells.append(
                        f'<td class="uc{sel_cls}"'
                        f' style="background:{bg};color:{fg}"'
                        f' onclick="sel(\'{uid_js}\')"'
                        f' title="{title}">{label}</td>'
                    )
                else:
                    cells.append('<td class="ue"></td>')
        rows_html.append(f'<tr>{"".join(cells)}</tr>')

    line_cells = "".join(f'<div class="lc">{l}</div>' for l in lines)

    type_cells = []
    for l in lines:
        lu = sorted([u for u in parsed if u["_l"] == l], key=lambda x: x["_f"], reverse=True)
        types_seen, seen_set = [], set()
        for u in lu:
            t = (u.get("type") or "").strip()
            if t and t not in seen_set:
                types_seen.append(t)
                seen_set.add(t)
        if not types_seen:
            td_content = ""
        elif len(types_seen) == 1:
            td_content = _h(types_seen[0])
        else:
            td_content = f"{_h(types_seen[0])}<br>{_h(types_seen[-1])}"
        type_cells.append(f'<div class="tc">{td_content}</div>')

    table_w = len(lines) * (CELL_W + 1) + 1

    return (
        f'<div class="bb">'
        f'{header}'
        f'<table class="ug" style="width:{table_w}px">'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table>'
        f'<div class="lr">{"".join(line_cells)}</div>'
        f'<div class="tr2">{"".join(type_cells)}</div>'
        f'</div>'
    )


def build_complex_html(buildings, units_by_bld, selected_uid):
    n = len(buildings)
    if n == 0:
        return 120, '<p style="color:#999;text-align:center">등록된 동이 없습니다.</p>'

    if n <= 4:
        row1_blds = buildings
        row2_blds = []
    else:
        n_per_row = math.ceil(n / 2)
        row1_blds = buildings[:n_per_row]
        row2_blds = buildings[n_per_row:]

    def max_floors_in_row(blds):
        mx = 0
        for b in blds:
            units = units_by_bld.get(b["id"], [])
            fset = set()
            for u in units:
                f, _ = parse_unit_no(u["unit_no"])
                if f is not None:
                    fset.add(f)
            if fset:
                # 1층부터 최고층까지 전체 기준으로 높이 계산
                mx = max(mx, max(fset))
        return max(mx, 1)

    bld_header_h = 35
    line_row_h   = 22
    type_row_h   = 38
    margin_h     = 20

    def row_height(blds):
        mf = max_floors_in_row(blds)
        return bld_header_h + mf * (CELL_H + 1) + line_row_h + type_row_h

    h1 = row_height(row1_blds)
    h2 = row_height(row2_blds) if row2_blds else 0
    total_h = h1 + h2 + (margin_h if row2_blds else 0) + 40

    def row_html(blds):
        blocks = "".join(
            build_building_block(b, units_by_bld.get(b["id"], []), selected_uid)
            for b in blds
        )
        return f'<div class="row">{blocks}</div>'

    body = row_html(row1_blds)
    if row2_blds:
        body += row_html(row2_blds)

    return total_h, body


def make_iframe_html(body_content):
    cw = CELL_W + 1

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, Arial, sans-serif;
    background: #f0f2f6;
    padding: 10px;
    overflow-x: auto;
}}
.row {{ display: flex; gap: 16px; margin-bottom: 20px; align-items: flex-start; flex-wrap: wrap; }}
.bb {{ flex-shrink: 0; }}
.bh {{
    text-align: center; font-weight: 700; font-size: 13px;
    background: #dee2e6; padding: 4px 6px; border-radius: 4px; margin-bottom: 5px;
}}
.ug {{ border-collapse: collapse; table-layout: fixed; }}
.uc {{
    width: {CELL_W}px; height: {CELL_H}px;
    border: 1px solid #ccc; text-align: center; vertical-align: middle;
    font-size: 11px; cursor: pointer; white-space: nowrap; overflow: hidden;
    user-select: none; transition: filter 0.12s;
}}
.uc:hover {{ filter: brightness(0.85); }}
.uc.sel {{ outline: 2px solid #1a1a1a; outline-offset: -2px; font-weight: 700; }}
.ue {{
    width: {CELL_W}px; height: {CELL_H}px; border: 1px solid #e0e0e0;
    background: linear-gradient(
        to bottom right,
        #F0F0F0 calc(50% - 0.5px), #ccc 50%, #F0F0F0 calc(50% + 0.5px)
    );
}}
.lr {{ display: flex; margin-top: 4px; }}
.lc {{ width: {cw}px; text-align: center; font-size: 11px; color: #555; font-weight: 600; }}
.tr2 {{ display: flex; margin-top: 2px; }}
.tc {{ width: {cw}px; text-align: center; font-size: 10px; color: #666; line-height: 1.35; }}
</style>
<script>
function sel(uid) {{
    var url = new URL(window.parent.location.href);
    url.searchParams.set('unit_id', uid);
    window.parent.location.href = url.toString();
}}
</script>
</head>
<body>
{body_content}
</body>
</html>"""


def render_complex(cx):
    buildings = db.get_buildings(site_id=site_id, complex_id=cx["id"])
    if not buildings:
        st.info("등록된 동이 없습니다.")
        return

    units_by_bld = {
        b["id"]: db.get_units(site_id=site_id, building_id=b["id"])
        for b in buildings
    }

    total_h, body = build_complex_html(buildings, units_by_bld, sel_unit_id)
    html = make_iframe_html(body)
    components.html(html, height=total_h + 20, scrolling=True)


complexes = db.get_complexes(site_id)
if not complexes:
    st.info("등록된 단지가 없습니다. 현장 관리 > 호실 일괄 업로드에서 데이터를 업로드하세요.")
    st.stop()

if len(complexes) > 1:
    tabs = st.tabs([cx["complex_name"] for cx in complexes])
    for tab, cx in zip(tabs, complexes):
        with tab:
            render_complex(cx)
else:
    render_complex(complexes[0])

# ── 호실 상세 정보 (인라인) ────────────────────────────────────────────
if sel_unit_id:
    try:
        unit = db.get_unit(int(sel_unit_id))
    except (ValueError, TypeError):
        unit = None

    if unit and unit.get("site_id") == site_id:
        st.divider()

        title_col, close_col = st.columns([9, 1])
        title_col.subheader(
            f"🔍 {unit['complex_name']} {unit['building_no']}동 {unit['unit_no']}"
        )
        if close_col.button("✕ 닫기", key="close_detail"):
            if "unit_id" in st.query_params:
                del st.query_params["unit_id"]

        contracts = db.get_contracts(unit_id=unit["id"])
        txs = db.get_transactions(unit_id=unit["id"])
        total_in = sum(t["amount"] for t in txs if t["type"] == "입금")
        total_out = sum(t["amount"] for t in txs if t["type"] == "출금")

        info_col, contract_col = st.columns(2)

        with info_col:
            st.markdown("##### 호실 정보")
            st.markdown(
                f"- 타입: **{unit.get('type') or '-'}**  \n"
                f"- 층/라인: **{unit.get('floor') or '-'}층 {unit.get('line') or '-'}라인**  \n"
                f"- 상태: **{unit.get('status', '-')}**  \n"
                f"- 분양가: **{(unit.get('sale_price') or 0):,}원**  \n"
                f"- 계약금: **{(unit.get('rental_price') or 0):,}원**"
            )

        with contract_col:
            st.markdown("##### 계약 정보")
            if contracts:
                ct = contracts[0]
                st.markdown(
                    f"- 계약자명: **{ct.get('customer_name') or '-'}**  \n"
                    f"- 연락처: **{ct.get('phone') or '-'}**  \n"
                    f"- 계약일: **{ct.get('contract_date') or '-'}**  \n"
                    f"- 계약구분: **{ct.get('contract_type') or '-'}**  \n"
                    f"- 담당팀: **{ct.get('assigned_team') or '-'}**  \n"
                    f"- 담당자: **{ct.get('assigned_staff') or '-'}**"
                )
                if ct.get("notes"):
                    st.markdown(f"- 비고: {ct['notes']}")
            else:
                st.info("계약 정보 없음")

        st.markdown("---")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("총 입금액", f"{total_in:,}원")
        sc2.metric("총 출금액", f"{total_out:,}원")
        sc3.metric("잔액", f"{(total_in - total_out):,}원")

        if txs:
            import pandas as pd
            st.markdown("##### 입출금 내역")
            rows = []
            for t in sorted(txs, key=lambda x: x["date"]):
                rows.append({
                    "날짜": t["date"],
                    "구분": t["type"],
                    "입금자명": t.get("depositor") or "",
                    "고객명": t.get("customer") or "",
                    "입금액": f"{t['amount']:,}" if t["type"] == "입금" else "",
                    "출금액": f"{t['amount']:,}" if t["type"] == "출금" else "",
                    "비고": t.get("notes") or "",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("입출금 내역 없음")
