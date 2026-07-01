import streamlit as st
from datetime import date
import db
import sidebar

st.set_page_config(page_title="해지", page_icon="❌", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("❌ 해지")

if st.session_state.get("_cancel_ok"):
    st.success(st.session_state.pop("_cancel_ok"))

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

# ── 동/호수 선택 (가계약/계약 상태만) ────────────────────────────
buildings = db.get_buildings(site_id=site_id)
if not buildings:
    st.info("등록된 동이 없습니다.")
    st.stop()

c1, c2 = st.columns(2)
bld_map = {b['building_no'] + '동': b['id'] for b in buildings}
sel_bld = c1.selectbox("동 선택", list(bld_map.keys()))
bld_id = bld_map[sel_bld]

units = db.get_units(site_id=site_id, building_id=bld_id)
units = [u for u in units if u.get('status') in ('가계약', '계약')]
if not units:
    c2.warning("해지 가능한 호실이 없습니다. (가계약/계약 상태 호실만 선택 가능)")
    st.stop()

unit_map = {u['unit_no']: u for u in units}
sel_unit_no = c2.selectbox("호수 선택", list(unit_map.keys()))
unit = unit_map[sel_unit_no]

st.info(
    f"**선택 호실:** {unit['complex_name']} {unit['building_no']}동 "
    f"{unit['unit_no']}　｜　현재 상태: {unit.get('status', '-')}"
)

contracts = db.get_contracts(unit_id=unit["id"])
contract_id = contracts[0]["id"] if contracts else None

# ── 입력 폼 ──────────────────────────────────────────────────────
with st.form("form_cancel", clear_on_submit=True):
    r1c1, r1c2 = st.columns(2)
    cancel_date = r1c1.date_input("해지접수일", value=date.today())
    refund_bank = r1c2.text_input("환불은행")

    r2c1, r2c2 = st.columns(2)
    account_no = r2c1.text_input("계좌번호")
    refund_amount = r2c2.number_input(
        "환불금액 (원)", value=0, step=100_000, min_value=0, format="%d"
    )

    notes = st.text_area("비고", height=80)

    if st.form_submit_button("❌ 해지 처리", type="primary", use_container_width=True):
        db.add_cancellation(
            unit_id=unit["id"],
            contract_id=contract_id,
            cancel_date=str(cancel_date),
            refund_amount=refund_amount,
            bank=refund_bank.strip() or None,
            account_no=account_no.strip() or None,
            notes=notes.strip() or None,
        )
        db.update_unit_status(unit["id"], "공실")
        st.session_state["_cancel_ok"] = (
            f"✅ 해지 처리 완료: {unit['building_no']}동 {unit['unit_no']}"
        )
        st.rerun()
