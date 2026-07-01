import streamlit as st
from datetime import date
import db
import sidebar

st.set_page_config(page_title="입출금 등록", page_icon="💰", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("💰 입출금 등록")

if st.session_state.get("_tx_ok"):
    st.success(st.session_state.pop("_tx_ok"))

# ── 금액 입력 헬퍼 ─────────────────────────────────────────────────
def _fmt_key(key):
    """포커스 이동 시 숫자를 천단위 콤마 형식으로 변환."""
    raw = st.session_state.get(key, "")
    cleaned = str(raw).replace(",", "").replace(" ", "")
    if cleaned and cleaned.isdigit():
        st.session_state[key] = f"{int(cleaned):,}"

def parse_amount(text):
    """콤마 포함 문자열을 정수로 변환. 숫자 외 문자 포함 시 None 반환."""
    cleaned = str(text or "").replace(",", "").replace(" ", "")
    if not cleaned:
        return 0
    if not cleaned.isdigit():
        return None
    return int(cleaned)

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

st.info(
    f"**선택 호실:** {unit['complex_name']} {unit['building_no']}동 {unit['unit_no']}"
)

# ── 입력 폼 (st.form 미사용 — 실시간 콤마 포맷을 위해) ────────────────
st.markdown("---")

r1c1, r1c2 = st.columns(2)
tx_date = r1c1.date_input("날짜", value=date.today(), key="reg_tx_date")
r1c2.text_input("입금자명", key="reg_depositor")

r2c1, r2c2 = st.columns(2)
r2c1.text_input("고객명", key="reg_customer")
r2c2.text_input("입금계좌", key="reg_account")

r3c1, r3c2 = st.columns(2)
r3c1.text_input(
    "입금액 (원)",
    key="reg_amount_in",
    placeholder="예: 1,000,000",
    on_change=_fmt_key,
    args=("reg_amount_in",),
)
r3c2.text_input(
    "출금액 (원)",
    key="reg_amount_out",
    placeholder="예: 500,000",
    on_change=_fmt_key,
    args=("reg_amount_out",),
)

r4c1, r4c2 = st.columns(2)
r4c1.text_input("출금사유", key="reg_out_reason")
r4c2.text_input("비고", key="reg_notes")

if st.button("💾 저장", type="primary", use_container_width=True):
    amount_in = parse_amount(st.session_state.get("reg_amount_in", ""))
    amount_out = parse_amount(st.session_state.get("reg_amount_out", ""))

    has_error = False
    if amount_in is None:
        st.error("입금액: 숫자 외 문자가 포함되어 있습니다.")
        has_error = True
    if amount_out is None:
        st.error("출금액: 숫자 외 문자가 포함되어 있습니다.")
        has_error = True

    if not has_error:
        if (amount_in or 0) == 0 and (amount_out or 0) == 0:
            st.error("입금액 또는 출금액을 입력하세요.")
        else:
            dep = st.session_state.get("reg_depositor", "").strip() or None
            cust = st.session_state.get("reg_customer", "").strip() or None
            acc = st.session_state.get("reg_account", "").strip() or None
            rsn = st.session_state.get("reg_out_reason", "").strip()
            nts = st.session_state.get("reg_notes", "").strip()
            saved = []

            if amount_in and amount_in > 0:
                db.add_transaction(
                    site_id=site_id,
                    date=str(tx_date),
                    depositor=dep,
                    customer=cust,
                    account=acc,
                    amount=amount_in,
                    tx_type="입금",
                    notes=nts or None,
                    unit_id=unit['id'],
                )
                saved.append(f"입금 {amount_in:,}원")
            if amount_out and amount_out > 0:
                out_notes = " | ".join(filter(None, [rsn, nts]))
                db.add_transaction(
                    site_id=site_id,
                    date=str(tx_date),
                    depositor=dep,
                    customer=cust,
                    account=acc,
                    amount=amount_out,
                    tx_type="출금",
                    notes=out_notes or None,
                    unit_id=unit['id'],
                )
                saved.append(f"출금 {amount_out:,}원")

            # 폼 필드 초기화 (위젯 key 삭제 방식 — 직접 대입 시 StreamlitAPIException 발생)
            for k in ["reg_amount_in", "reg_amount_out", "reg_depositor",
                      "reg_customer", "reg_account", "reg_out_reason", "reg_notes"]:
                st.session_state.pop(k, None)

            st.session_state["_tx_ok"] = f"✅ 저장 완료: {', '.join(saved)}"
            st.rerun()
