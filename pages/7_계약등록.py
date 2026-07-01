import streamlit as st
from datetime import date
import db
import sidebar

st.set_page_config(page_title="계약 등록", page_icon="✏️", layout="wide")

sidebar.require_login()

user = st.session_state.user
if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)
st.title("✏️ 계약 등록")

if st.session_state.get("_contract_ok"):
    st.success(st.session_state.pop("_contract_ok"))

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

# ── 직원 목록 (본부/팀 연동용, 현장 결정 후 즉시 로드) ────────────
employees = db.get_employees(site_id)
divisions = sorted(set(e.get('division') or '' for e in employees if e.get('division')))

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

# ── 기존 계약 조회 ─────────────────────────────────────────────────
existing_contracts = db.get_contracts(unit_id=unit['id'])
existing = existing_contracts[0] if existing_contracts else None
has_contract = existing is not None and unit.get('status') in ('가계약', '계약')

# ── 호실 변경 시 세션 초기화 + 본부/팀 pre-populate ──────────────
unit_key = f"{site_id}_{bld_id}_{unit['id']}"
if st.session_state.get('_contract_unit_key') != unit_key:
    st.session_state['_contract_unit_key'] = unit_key
    st.session_state['edit_mode'] = False
    if has_contract and existing:
        _ext = existing.get('assigned_team') or ''
        _emp = next((e for e in employees if e.get('team') == _ext), None)
        _exd = (_emp.get('division') or '') if _emp else ''
        st.session_state['contract_division'] = _exd
        st.session_state['contract_team'] = _ext
    else:
        st.session_state['contract_division'] = ''
        st.session_state['contract_team'] = ''

is_edit_mode = st.session_state.get('edit_mode', False)
is_disabled = has_contract and not is_edit_mode

# ── 상태 표시 ─────────────────────────────────────────────────────
status_label = {
    "공실": "🟢 공실", "가계약": "🔵 가계약",
    "계약": "🔴 계약", "해지": "⚫ 해지"
}.get(unit.get("status"), unit.get("status", "-"))
st.info(
    f"**선택 호실:** {unit['complex_name']} {unit['building_no']}동 "
    f"{unit['unit_no']}　｜　현재 상태: {status_label}"
)

if has_contract and not is_edit_mode:
    st.button(
        "✏️ 수정",
        on_click=lambda: st.session_state.update({'edit_mode': True}),
    )

# ── 담당본부 / 담당팀 연동 선택 (폼 외부 — 담당자 필터링용) ─────
div_options = [""] + divisions
# 세션 값이 옵션에 없으면 초기화 (직원 구성 변경 대비)
if st.session_state.get('contract_division', '') not in div_options:
    st.session_state['contract_division'] = ''

div_col, team_col, _ = st.columns(3)
assigned_division = div_col.selectbox(
    "담당본부", div_options,
    disabled=is_disabled, key="contract_division",
)

if assigned_division:
    teams_in_div = sorted(set(
        e['team'] for e in employees
        if e.get('division') == assigned_division and e.get('team')
    ))
else:
    teams_in_div = sorted(set(e['team'] for e in employees if e.get('team')))

team_options = [""] + teams_in_div
# 현재 저장된 팀이 필터된 목록에 없으면 초기화
if st.session_state.get('contract_team', '') not in team_options:
    st.session_state['contract_team'] = ''

assigned_team = team_col.selectbox(
    "담당팀", team_options,
    disabled=is_disabled, key="contract_team",
)

if assigned_team:
    staff_list = [e['name'] for e in employees if e.get('team') == assigned_team]
elif assigned_division:
    staff_list = [e['name'] for e in employees if e.get('division') == assigned_division]
else:
    staff_list = [e['name'] for e in employees]

# ── 기본값 설정 ───────────────────────────────────────────────────
if has_contract and existing:
    def_type = existing.get('contract_type', '가계약')
    _cd = existing.get('contract_date')
    def_date = date.fromisoformat(_cd) if _cd else date.today()
    def_name  = existing.get('customer_name', '') or ''
    def_phone = existing.get('phone', '') or ''
    def_addr  = existing.get('address', '') or ''
    def_staff = existing.get('assigned_staff', '') or ''
    def_notes = existing.get('notes', '') or ''
    def_sale  = int(unit.get('sale_price') or 0)
    def_dep   = int(existing.get('deposit_total') or 0)
else:
    def_type  = '가계약'
    def_date  = date.today()
    def_name = def_phone = def_addr = def_staff = def_notes = ''
    def_sale  = int(unit.get('sale_price') or 0)
    def_dep   = int(unit.get('rental_price') or 0)

# ── 입력 폼 ──────────────────────────────────────────────────────
with st.form("form_contract"):
    r1c1, r1c2 = st.columns(2)
    type_options = ["가계약", "계약"]
    type_idx = type_options.index(def_type) if def_type in type_options else 0
    contract_type = r1c1.radio(
        "계약구분", type_options, index=type_idx, horizontal=True, disabled=is_disabled,
    )
    contract_date = r1c2.date_input("계약일자", value=def_date, disabled=is_disabled)

    r2c1, r2c2 = st.columns(2)
    customer_name = r2c1.text_input("계약자명 *", value=def_name, disabled=is_disabled)
    phone = r2c2.text_input("연락처", value=def_phone, disabled=is_disabled)

    address = st.text_input("주소", value=def_addr, disabled=is_disabled)

    r3c1, r3c2 = st.columns(2)
    staff_options = [""] + staff_list
    staff_idx = staff_options.index(def_staff) if def_staff in staff_options else 0
    assigned_staff = r3c1.selectbox(
        "담당자", staff_options, index=staff_idx, disabled=is_disabled,
    )
    notes = r3c2.text_input("비고", value=def_notes, disabled=is_disabled)

    r4c1, r4c2 = st.columns(2)
    sale_price = r4c1.number_input(
        "분양가 (원)", value=def_sale, step=1_000_000, min_value=0, format="%d", disabled=is_disabled,
    )
    deposit_price = r4c2.number_input(
        "계약금 (원)", value=def_dep, step=100_000, min_value=0, format="%d", disabled=is_disabled,
    )

    # ── 제출 버튼 (모드에 따라 다르게 표시) ─────────────────────
    if has_contract and not is_edit_mode:
        st.form_submit_button(
            "✏️ 위의 수정 버튼을 눌러 편집하세요",
            disabled=True, use_container_width=True,
        )
        submitted = False
    elif has_contract:
        submitted = st.form_submit_button("💾 수정 저장", type="primary", use_container_width=True)
    else:
        submitted = st.form_submit_button("💾 신규 저장", type="primary", use_container_width=True)

    if submitted:
        if not customer_name.strip():
            st.error("계약자명을 입력하세요.")
        elif has_contract and existing:
            db.update_contract(
                existing['id'],
                customer_name=customer_name.strip(),
                phone=phone.strip() or None,
                address=address.strip() or None,
                contract_type=contract_type,
                contract_date=str(contract_date),
                deposit_total=deposit_price,
                assigned_team=assigned_team or None,
                assigned_staff=assigned_staff or None,
                notes=notes.strip() or None,
            )
            st.session_state['edit_mode'] = False
            st.session_state["_contract_ok"] = (
                f"✅ 계약 수정 완료: {unit['building_no']}동 {unit['unit_no']} — {customer_name.strip()}"
            )
            st.rerun()
        else:
            db.add_contract(
                unit_id=unit["id"],
                site_id=site_id,
                customer_name=customer_name.strip(),
                phone=phone.strip() or None,
                address=address.strip() or None,
                contract_type=contract_type,
                contract_date=str(contract_date),
                deposit_total=deposit_price,
                assigned_team=assigned_team or None,
                assigned_staff=assigned_staff or None,
                notes=notes.strip() or None,
            )
            st.session_state["_contract_ok"] = (
                f"✅ 계약 등록 완료: {unit['building_no']}동 {unit['unit_no']} — {customer_name.strip()}"
            )
            st.rerun()
