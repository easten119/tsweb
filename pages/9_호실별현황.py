import streamlit as st
import pandas as pd
import db
import sidebar

st.set_page_config(page_title="호실별 현황", page_icon="🔍", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("🔍 호실별 현황")

# ── 현장 선택 ─────────────────────────────────────────────────────
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
    sel_site = st.selectbox("현장 선택", list(site_map.keys()))
    site_id = site_map[sel_site]

# ── 동/호수 선택 ──────────────────────────────────────────────────
buildings = db.get_buildings(site_id=site_id)
if not buildings:
    st.info("등록된 동이 없습니다.")
    st.stop()

c1, c2 = st.columns(2)
bld_map = {b['building_no'] + '동': b['id'] for b in buildings}
sel_bld = c1.selectbox("동 선택", list(bld_map.keys()))
bld_id = bld_map[sel_bld]

units = db.get_units(site_id=site_id, building_id=bld_id)
if not units:
    c2.warning("호실이 없습니다.")
    st.stop()

unit_map = {u['unit_no']: u for u in units}
sel_unit_no = c2.selectbox("호수 선택", list(unit_map.keys()))
unit = unit_map[sel_unit_no]

st.divider()

# ── 호실 정보 + 계약 정보 ─────────────────────────────────────────
contracts = db.get_contracts(unit_id=unit["id"])
txs = db.get_transactions(unit_id=unit["id"])
total_in = sum(t["amount"] for t in txs if t["type"] == "입금")
total_out = sum(t["amount"] for t in txs if t["type"] == "출금")

st.subheader(
    f"{unit['complex_name']} {unit['building_no']}동 {unit['unit_no']}"
)

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

# ── 입출금 요약 ──────────────────────────────────────────────────
st.markdown("---")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("총 입금액", f"{total_in:,}원")
sc2.metric("총 출금액", f"{total_out:,}원")
sc3.metric("잔액", f"{(total_in - total_out):,}원")

# ── 입출금 내역 테이블 ────────────────────────────────────────────
if txs:
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
