import io
import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

st.set_page_config(page_title="입출금 리스트", page_icon="📃", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📃 입출금 리스트")

# ── 금액 입력 헬퍼 ─────────────────────────────────────────────────
def _fmt_key(key):
    raw = st.session_state.get(key, "")
    cleaned = str(raw).replace(",", "").replace(" ", "")
    if cleaned and cleaned.isdigit():
        st.session_state[key] = f"{int(cleaned):,}"

def parse_amount(text):
    cleaned = str(text or "").replace(",", "").replace(" ", "")
    if not cleaned:
        return 0
    if not cleaned.isdigit():
        return None
    return int(cleaned)

def _clear_unit_key(key):
    st.session_state.pop(key, None)

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

# ── 필터 ─────────────────────────────────────────────────────────
today = date.today()
fc1, fc2, fc3 = st.columns([2, 2, 2])
start_date = fc1.date_input("시작일", value=today.replace(day=1))
end_date   = fc2.date_input("종료일", value=today)

buildings = db.get_buildings(site_id=site_id)
bld_options = ["전체"] + [b['building_no'] + "동" for b in buildings]
sel_bld_filter = fc3.selectbox("동 필터", bld_options)

# ── 데이터 조회 ───────────────────────────────────────────────────
txs_all = db.get_transactions(site_id=site_id)
txs_all = [t for t in txs_all if str(start_date) <= str(t['date']) <= str(end_date)]

if sel_bld_filter != "전체":
    bld_no = sel_bld_filter.replace("동", "")
    txs_all = [t for t in txs_all if str(t.get('building_no', '')) == bld_no]

# ── 수정 폼 ──────────────────────────────────────────────────────
edit_tx_id = st.session_state.get('edit_tx_id')
if edit_tx_id:
    tx_edit = next((t for t in txs_all if t['id'] == edit_tx_id), None)
    if tx_edit is None:
        tx_edit = db.get_transaction(edit_tx_id)

    if tx_edit:
        bno = str(tx_edit.get('building_no') or '')
        uno = str(tx_edit.get('unit_no') or '')
        dong_ho = f"{bno}동 {uno}" if bno else uno
        st.subheader("✏️ 거래 수정")
        st.caption(f"대상: {dong_ho} | ID: {edit_tx_id}")

        # 동/호수 선택
        edt_bld_key  = f"edt_bld_{edit_tx_id}"
        edt_unit_key = f"edt_unit_{edit_tx_id}"

        bld_map_edit   = {b['building_no'] + '동': b['id'] for b in buildings}
        bld_names_edit = list(bld_map_edit.keys())

        cur_unit_obj = db.get_unit(tx_edit['unit_id']) if tx_edit.get('unit_id') else None
        cur_bld_name = (cur_unit_obj['building_no'] + '동') if cur_unit_obj and cur_unit_obj.get('building_no') else None
        cur_unit_no  = cur_unit_obj.get('unit_no') if cur_unit_obj else None

        if edt_bld_key not in st.session_state:
            st.session_state[edt_bld_key] = (
                cur_bld_name if cur_bld_name in bld_names_edit
                else (bld_names_edit[0] if bld_names_edit else '')
            )

        eu1, eu2 = st.columns(2)
        sel_bld_name_edit = eu1.selectbox(
            "동 선택", bld_names_edit, key=edt_bld_key,
            on_change=_clear_unit_key, args=(edt_unit_key,),
        )
        sel_bld_id_edit = bld_map_edit[sel_bld_name_edit]

        units_for_edit   = db.get_units(site_id=site_id, building_id=sel_bld_id_edit)
        unit_no_map_edit = {u['unit_no']: u['id'] for u in units_for_edit}
        unit_nos_edit    = list(unit_no_map_edit.keys())

        if edt_unit_key not in st.session_state:
            if cur_unit_no and cur_unit_no in unit_nos_edit:
                st.session_state[edt_unit_key] = cur_unit_no
            elif unit_nos_edit:
                st.session_state[edt_unit_key] = unit_nos_edit[0]

        sel_unit_no_edit = eu2.selectbox("호수 선택", unit_nos_edit, key=edt_unit_key)
        sel_unit_id_edit = unit_no_map_edit.get(sel_unit_no_edit)

        # 세션 키
        amt_in_key  = f"edt_in_{edit_tx_id}"
        amt_out_key = f"edt_out_{edit_tx_id}"
        rsn_key     = f"edt_rsn_{edit_tx_id}"
        nts_key     = f"edt_nts_{edit_tx_id}"
        dep_key     = f"edt_dep_{edit_tx_id}"
        cust_key    = f"edt_cust_{edit_tx_id}"
        acc_key     = f"edt_acc_{edit_tx_id}"

        if amt_in_key not in st.session_state:
            st.session_state[dep_key]  = tx_edit.get('depositor') or ''
            st.session_state[cust_key] = tx_edit.get('customer') or ''
            st.session_state[acc_key]  = tx_edit.get('account') or ''
            raw_notes = tx_edit.get('notes') or ''
            if tx_edit['type'] == '입금':
                st.session_state[amt_in_key]  = f"{tx_edit.get('amount', 0):,}"
                st.session_state[amt_out_key] = ""
                st.session_state[rsn_key]     = ""
                st.session_state[nts_key]     = raw_notes
            else:
                st.session_state[amt_in_key]  = ""
                st.session_state[amt_out_key] = f"{tx_edit.get('amount', 0):,}"
                if ' | ' in raw_notes:
                    rsn, nts = raw_notes.split(' | ', 1)
                else:
                    rsn, nts = raw_notes, ''
                st.session_state[rsn_key] = rsn
                st.session_state[nts_key] = nts

        ec1, ec2 = st.columns(2)
        ec1.date_input(
            "날짜",
            value=date.fromisoformat(str(tx_edit['date'])),
            key=f"edt_date_{edit_tx_id}",
        )
        ec2.text_input("입금자명", key=dep_key)

        ec3, ec4 = st.columns(2)
        ec3.text_input("고객명",   key=cust_key)
        ec4.text_input("입금계좌", key=acc_key)

        ec5, ec6 = st.columns(2)
        ec5.text_input(
            "입금액 (원)", key=amt_in_key, placeholder="예: 1,000,000",
            on_change=_fmt_key, args=(amt_in_key,),
        )
        ec6.text_input(
            "출금액 (원)", key=amt_out_key, placeholder="예: 500,000",
            on_change=_fmt_key, args=(amt_out_key,),
        )

        ec7, ec8 = st.columns(2)
        ec7.text_input("출금사유", key=rsn_key)
        ec8.text_input("비고",     key=nts_key)

        sv_col, cx_col, _ = st.columns([1, 1, 4])
        if sv_col.button("💾 수정 저장", type="primary", key="btn_edit_save"):
            amount_in  = parse_amount(st.session_state.get(amt_in_key, ""))
            amount_out = parse_amount(st.session_state.get(amt_out_key, ""))

            has_error = False
            if amount_in is None:
                st.error("입금액: 숫자 외 문자가 포함되어 있습니다.")
                has_error = True
            if amount_out is None:
                st.error("출금액: 숫자 외 문자가 포함되어 있습니다.")
                has_error = True

            if not has_error:
                if amount_in > 0 and amount_out > 0:
                    st.error("입금액과 출금액을 동시에 입력할 수 없습니다.")
                elif amount_in == 0 and amount_out == 0:
                    st.error("입금액 또는 출금액을 입력하세요.")
                else:
                    if amount_in > 0:
                        new_type   = '입금'
                        new_amount = amount_in
                        notes_val  = st.session_state.get(nts_key, "").strip() or None
                    else:
                        new_type   = '출금'
                        new_amount = amount_out
                        rsn = st.session_state.get(rsn_key, "").strip()
                        nts = st.session_state.get(nts_key, "").strip()
                        notes_val = " | ".join(filter(None, [rsn, nts])) or None

                    new_date = st.session_state.get(
                        f"edt_date_{edit_tx_id}",
                        date.fromisoformat(str(tx_edit['date'])),
                    )
                    db.update_transaction(
                        tx_id=edit_tx_id,
                        date=str(new_date),
                        depositor=st.session_state.get(dep_key, "").strip() or None,
                        customer=st.session_state.get(cust_key, "").strip() or None,
                        account=st.session_state.get(acc_key, "").strip() or None,
                        amount=new_amount,
                        tx_type=new_type,
                        notes=notes_val,
                        unit_id=sel_unit_id_edit,
                    )
                    st.session_state.pop('edit_tx_id', None)
                    st.session_state['_list_ok'] = "✅ 수정 완료"
                    st.rerun()

        if cx_col.button("❌ 취소", key="btn_edit_cancel"):
            st.session_state.pop('edit_tx_id', None)
            st.rerun()

        st.markdown("---")
    else:
        st.warning("수정할 거래 내역을 찾을 수 없습니다.")
        st.session_state.pop('edit_tx_id', None)

# ── 삭제 확인 ────────────────────────────────────────────────────
del_tx_id = st.session_state.get('del_tx_id')
if del_tx_id and not edit_tx_id:
    tx_del = next((t for t in txs_all if t['id'] == del_tx_id), None)
    if tx_del is None:
        tx_del = db.get_transaction(del_tx_id)

    if tx_del:
        bno = str(tx_del.get('building_no') or '')
        uno = str(tx_del.get('unit_no') or '')
        dong_ho_d = f"{bno}동 {uno}" if bno else uno
        st.warning(
            f"**삭제 확인:** {tx_del['date']} | {dong_ho_d} | "
            f"{tx_del['type']} {tx_del.get('amount', 0):,}원"
        )
        confirm_del = st.checkbox("위 내역을 삭제합니다. (취소 불가)", key="del_confirm_chk")
        dc1, dc2, _ = st.columns([1, 1, 4])
        if dc1.button("🗑️ 삭제 확인", type="primary", disabled=not confirm_del, key="btn_del_ok"):
            db.delete_transaction(del_tx_id)
            st.session_state.pop('del_tx_id', None)
            st.session_state.pop('del_confirm_chk', None)
            st.session_state['_list_ok'] = "🗑️ 삭제 완료"
            st.rerun()
        if dc2.button("❌ 취소", key="btn_del_cancel"):
            st.session_state.pop('del_tx_id', None)
            st.rerun()
        st.markdown("---")
    else:
        st.session_state.pop('del_tx_id', None)

# ── 알림 ─────────────────────────────────────────────────────────
if st.session_state.get("_list_ok"):
    st.success(st.session_state.pop("_list_ok"))

if not txs_all:
    st.info("조건에 맞는 입출금 내역이 없습니다.")
    st.stop()

sorted_txs = sorted(txs_all, key=lambda x: x['date'])

# ── 테이블 (st.dataframe) ─────────────────────────────────────────
rows_display = []
for t in sorted_txs:
    bno = str(t.get('building_no') or '')
    uno = str(t.get('unit_no') or '')
    amt_in  = t['amount'] if t['type'] == '입금' else 0
    amt_out = t['amount'] if t['type'] == '출금' else 0

    notes = t.get('notes') or ''
    if t['type'] == '출금' and ' | ' in notes:
        out_reason, note_text = notes.split(' | ', 1)
    elif t['type'] == '출금':
        out_reason, note_text = notes, ''
    else:
        out_reason, note_text = '', notes

    rows_display.append({
        "날짜":    t['date'],
        "동":      bno + "동" if bno else "",
        "호수":    uno,
        "입금자명": t.get('depositor') or '',
        "고객명":  t.get('customer') or '',
        "입금계좌": t.get('account') or '',
        "입금액":  amt_in,
        "출금액":  amt_out,
        "출금사유": out_reason,
        "비고":    note_text,
    })

df_display = pd.DataFrame(rows_display)

st.markdown(f"총 **{len(sorted_txs)}**건")
event = st.dataframe(
    df_display.style.format({"입금액": "{:,}", "출금액": "{:,}"}),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── 행 선택 시 수정/삭제 버튼 ────────────────────────────────────
if user['role'] in ('admin', 'manager'):
    selected_rows = event.selection.rows if hasattr(event, 'selection') else []
    if selected_rows:
        sel_idx = selected_rows[0]
        sel_tx  = sorted_txs[sel_idx]
        bno = str(sel_tx.get('building_no') or '')
        uno = str(sel_tx.get('unit_no') or '')
        st.info(
            f"선택: {sel_tx['date']} | {bno}동 {uno} | "
            f"{sel_tx['type']} {sel_tx['amount']:,}원"
        )
        act1, act2, _ = st.columns([1, 1, 8])
        if act1.button("✏️ 수정", key="btn_sel_edit"):
            for k in list(st.session_state.keys()):
                if k.startswith('edt_'):
                    del st.session_state[k]
            st.session_state['edit_tx_id'] = sel_tx['id']
            st.session_state.pop('del_tx_id', None)
            st.rerun()
        if act2.button("🗑️ 삭제", key="btn_sel_del"):
            st.session_state['del_tx_id'] = sel_tx['id']
            st.session_state.pop('edit_tx_id', None)
            st.rerun()
    else:
        st.caption("행을 클릭하면 수정/삭제 버튼이 나타납니다.")

st.markdown("---")

# ── 요약 합계 ─────────────────────────────────────────────────────
total_in  = sum(t['amount'] for t in txs_all if t['type'] == '입금')
total_out = sum(t['amount'] for t in txs_all if t['type'] == '출금')
m1, m2, m3 = st.columns(3)
m1.metric("총 입금액", f"{total_in:,}원")
m2.metric("총 출금액", f"{total_out:,}원")
m3.metric("잔액",     f"{(total_in - total_out):,}원")

# ── 엑셀 다운로드 ─────────────────────────────────────────────────
excel_rows = []
for t in sorted_txs:
    bno = str(t.get('building_no') or '')
    uno = str(t.get('unit_no') or '')
    notes = t.get('notes') or ''
    if t['type'] == '출금' and ' | ' in notes:
        out_reason, note_text = notes.split(' | ', 1)
    elif t['type'] == '출금':
        out_reason, note_text = notes, ''
    else:
        out_reason, note_text = '', notes

    excel_rows.append({
        "날짜":    t["date"],
        "동":      bno + "동" if bno else "",
        "호수":    uno,
        "입금자명": t.get("depositor") or "",
        "고객명":  t.get("customer") or "",
        "입금계좌": t.get("account") or "",
        "입금액":  t["amount"] if t["type"] == "입금" else 0,
        "출금액":  t["amount"] if t["type"] == "출금" else 0,
        "출금사유": out_reason,
        "비고":    note_text,
    })

df_excel = pd.DataFrame(excel_rows)
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine='openpyxl') as writer:
    df_excel.to_excel(writer, index=False, sheet_name='입출금리스트')
buf.seek(0)
st.download_button(
    "📥 엑셀 다운로드",
    data=buf,
    file_name=f"입출금리스트_{start_date}_{end_date}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
