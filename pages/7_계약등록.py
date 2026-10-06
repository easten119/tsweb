import streamlit as st
from datetime import date
import db
import sidebar

user = sidebar.page_setup("계약 등록", "✏️", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

site_id, site, _ = sidebar.select_site(user)
employees = db.get_employees(site_id)

c1, c2 = st.columns(2)
bld_id, _ = sidebar.select_building(site_id, container=c1)
units = db.get_units(site_id=site_id, building_id=bld_id)
if not units:
    c2.warning("호실이 없습니다.")
    st.stop()
unit = sidebar.select_unit(units, container=c2)

existing = db.get_active_contract(unit['id'])
has_contract = existing is not None

# ── 호실이 바뀌면 편집 상태 초기화 + 담당 본부/팀 채우기 ─────────────
if st.session_state.get('_contract_unit') != unit['id']:
    st.session_state['_contract_unit'] = unit['id']
    st.session_state['contract_edit_mode'] = False
    team = (existing or {}).get('assigned_team') or ''
    emp = next((e for e in employees if e.get('team') == team), None)
    st.session_state['contract_division'] = (emp.get('division') or '') if emp else ''
    st.session_state['contract_team'] = team

is_edit_mode = st.session_state.get('contract_edit_mode', False)
is_disabled = has_contract and not is_edit_mode

status_label = {"공실": "🟢 공실", "가계약": "🔵 가계약", "계약": "🔴 계약"}.get(unit['status'], unit['status'])
st.info(f"**선택 호실:** {sidebar.unit_title(unit)}　｜　현재 상태: {status_label}"
        + (f"　｜　계약자: {existing['customer_name']}" if existing else ""))

if has_contract and not is_edit_mode:
    b1, b2, _ = st.columns([1, 2, 5])
    b1.button("✏️ 수정", on_click=lambda: st.session_state.update({'contract_edit_mode': True}))
    b2.page_link("pages/10_해지.py", label="❌ 이 계약 해지하러 가기")

# ── 담당본부 / 담당팀 (폼 밖 — 담당자 목록 필터용) ─────────────────
divisions = sorted({e['division'] for e in employees if e.get('division')})
div_options = [""] + divisions
if st.session_state.get('contract_division', '') not in div_options:
    st.session_state['contract_division'] = ''
d_col, t_col, _ = st.columns(3)
assigned_division = d_col.selectbox("담당본부", div_options, disabled=is_disabled, key="contract_division")
teams = sorted({e['team'] for e in employees if e.get('team') and
                (not assigned_division or e.get('division') == assigned_division)})
team_options = [""] + teams
if st.session_state.get('contract_team', '') not in team_options:
    # 저장된 팀이 현재 직원 구성에 없더라도 기존 값은 보여준다
    saved = st.session_state.get('contract_team', '')
    if saved and has_contract:
        team_options.append(saved)
    else:
        st.session_state['contract_team'] = ''
assigned_team = t_col.selectbox("담당팀", team_options, disabled=is_disabled, key="contract_team")

if assigned_team:
    staff_list = [e['name'] for e in employees if e.get('team') == assigned_team]
elif assigned_division:
    staff_list = [e['name'] for e in employees if e.get('division') == assigned_division]
else:
    staff_list = [e['name'] for e in employees]
staff_list = sorted(set(staff_list))

# ── 기본값 ───────────────────────────────────────────────────────
ex = existing or {}
def_type = ex.get('contract_type', '가계약')
try:
    def_date = date.fromisoformat(ex['contract_date']) if ex.get('contract_date') else date.today()
except ValueError:
    def_date = date.today()
def_staff = ex.get('assigned_staff') or ''
staff_options = [""] + staff_list + ([def_staff] if def_staff and def_staff not in staff_list else [])

with st.form(f"form_contract_{unit['id']}_{is_edit_mode}"):
    r1c1, r1c2 = st.columns(2)
    type_options = ["가계약", "계약"]
    contract_type = r1c1.radio("계약구분", type_options, horizontal=True, disabled=is_disabled,
                               index=type_options.index(def_type) if def_type in type_options else 0)
    contract_date = r1c2.date_input("계약일자", value=def_date, disabled=is_disabled)

    r2c1, r2c2 = st.columns(2)
    customer_name = r2c1.text_input("계약자명 *", value=ex.get('customer_name') or '', disabled=is_disabled)
    phone = r2c2.text_input("연락처", value=ex.get('phone') or '', disabled=is_disabled)
    address = st.text_input("주소", value=ex.get('address') or '', disabled=is_disabled)

    r3c1, r3c2 = st.columns(2)
    assigned_staff = r3c1.selectbox("담당자", staff_options, index=staff_options.index(def_staff),
                                    disabled=is_disabled)
    notes = r3c2.text_input("비고", value=ex.get('notes') or '', disabled=is_disabled)

    r4c1, r4c2 = st.columns(2)
    sale_price = r4c1.number_input("분양가 (원) — 호실 분양가로 저장됩니다", value=int(unit.get('sale_price') or 0),
                                   step=1_000_000, min_value=0, format="%d", disabled=is_disabled)
    deposit_price = r4c2.number_input("계약금 (원)", min_value=0, step=100_000, format="%d", disabled=is_disabled,
                                      value=int(ex.get('deposit_total') or unit.get('rental_price') or 0))

    if is_disabled:
        st.form_submit_button("✏️ 위의 수정 버튼을 눌러 편집하세요", disabled=True, width="stretch")
        submitted = False
    else:
        submitted = st.form_submit_button("💾 수정 저장" if has_contract else "💾 신규 저장",
                                          type="primary", width="stretch")

    if submitted:
        payload = dict(
            customer_name=customer_name.strip(), phone=phone.strip() or None, address=address.strip() or None,
            contract_type=contract_type, contract_date=str(contract_date), deposit_total=int(deposit_price),
            assigned_team=assigned_team or None, assigned_staff=assigned_staff or None,
            notes=notes.strip() or None, sale_price=int(sale_price),
        )
        if not payload['customer_name']:
            st.error("계약자명을 입력하세요.")
        elif has_contract:
            db.update_contract(existing['id'], **payload)
            st.session_state['contract_edit_mode'] = False
            sidebar.flash(f"✅ 계약 수정 완료: {sidebar.unit_title(unit)} — {payload['customer_name']}")
            st.rerun()
        else:
            try:
                db.add_contract(unit_id=unit['id'], site_id=site_id, **payload)
            except ValueError as e:
                st.error(str(e))
            else:
                sidebar.flash(f"✅ 계약 등록 완료: {sidebar.unit_title(unit)} — {payload['customer_name']}")
                st.rerun()

if has_contract and is_edit_mode:
    c_cancel, _ = st.columns([1, 5])
    if c_cancel.button("편집 취소"):
        st.session_state['contract_edit_mode'] = False
        st.rerun()
    with st.expander("🗑️ 잘못 등록한 계약 삭제 (해지가 아닌 경우만)"):
        st.caption("실제 해지는 '해지' 메뉴를 사용하세요. 삭제하면 계약 기록이 남지 않습니다.")
        ok = st.checkbox("이 계약을 삭제하고 호실을 공실로 되돌립니다.", key=f"del_ct_{existing['id']}")
        if st.button("삭제", type="primary", disabled=not ok):
            db.delete_contract(existing['id'])
            st.session_state['contract_edit_mode'] = False
            sidebar.flash("계약이 삭제되었습니다.")
            st.rerun()
