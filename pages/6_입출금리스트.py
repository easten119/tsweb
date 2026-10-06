import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

user = sidebar.page_setup("입출금 리스트", "📃")
editable = sidebar.can_edit(user)
sidebar.show_flash()

site_id, site, _ = sidebar.select_site(user)

# ── 필터 ─────────────────────────────────────────────────────────
today = date.today()
fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
start_date = fc1.date_input("시작일", value=today.replace(day=1))
end_date = fc2.date_input("종료일", value=today)
bld_filter, buildings = sidebar.select_building(site_id, key="txl_bld", label="동 필터", container=fc3,
                                                include_all=True)
type_filter = fc4.selectbox("구분", ["전체", "입금", "출금"])
keyword = st.text_input("검색 (호수·입금자·고객명·비고)", placeholder="예: 1502, 홍길동")

if start_date > end_date:
    st.error("시작일이 종료일보다 늦습니다.")
    st.stop()

txs = db.get_transactions(site_id=site_id, start_date=start_date, end_date=end_date,
                          tx_type=None if type_filter == "전체" else type_filter)
if bld_filter:
    unit_ids = {u['id'] for u in db.get_units(site_id=site_id, building_id=bld_filter)}
    txs = [t for t in txs if t.get('unit_id') in unit_ids]
if keyword.strip():
    kw = keyword.strip()
    txs = [t for t in txs if any(kw in str(t.get(f) or '') for f in
                                 ('unit_no', 'depositor', 'customer', 'notes', 'out_reason', 'account'))]
txs = sorted(txs, key=lambda x: (x['date'], x['id']))

# ── 수정 폼 ──────────────────────────────────────────────────────
edit_id = st.session_state.get('edit_tx_id')
if edit_id and editable:
    tx = db.get_transaction(edit_id)
    if not tx or tx['site_id'] != site_id:
        st.session_state.pop('edit_tx_id', None)
    else:
        st.subheader("✏️ 거래 수정")
        st.caption(f"대상: {tx.get('building_no') or ''}동 {tx.get('unit_no') or ''} | ID {edit_id}")
        k = lambda name: f"edt_{name}_{edit_id}"  # noqa: E731
        if k('init') not in st.session_state:
            st.session_state[k('init')] = True
            st.session_state[k('dep')] = tx.get('depositor') or ''
            st.session_state[k('cust')] = tx.get('customer') or ''
            st.session_state[k('acc')] = tx.get('account') or ''
            st.session_state[k('amt')] = f"{tx.get('amount', 0):,}"
            st.session_state[k('type')] = tx['type']
            st.session_state[k('rsn')] = tx.get('out_reason') or ''
            st.session_state[k('nts')] = tx.get('notes') or ''

        cur_unit = db.get_unit(tx['unit_id']) if tx.get('unit_id') else None
        eu1, eu2 = st.columns(2)
        if cur_unit and k('bld') not in st.session_state:
            st.session_state[k('bld')] = cur_unit['building_id']
        e_bld, _ = sidebar.select_building(site_id, key=k('bld'), container=eu1)
        e_units = db.get_units(site_id=site_id, building_id=e_bld)
        e_ids = [u['id'] for u in e_units]
        if cur_unit and k('unit') not in st.session_state and cur_unit['id'] in e_ids:
            st.session_state[k('unit')] = cur_unit['id']
        if st.session_state.get(k('unit')) not in e_ids:
            st.session_state.pop(k('unit'), None)
        e_unit = sidebar.select_unit(e_units, key=k('unit'), container=eu2, show_status=False) if e_units else None

        ec1, ec2, ec3 = st.columns(3)
        new_date = ec1.date_input("날짜", value=date.fromisoformat(str(tx['date'])), key=k('date'))
        new_type = ec2.radio("구분", ["입금", "출금"], key=k('type'), horizontal=True)
        ec3.text_input("금액 (원)", key=k('amt'), on_change=sidebar.fmt_amount_key, args=(k('amt'),))
        ec4, ec5, ec6 = st.columns(3)
        ec4.text_input("입금자명", key=k('dep'))
        ec5.text_input("고객명", key=k('cust'))
        ec6.text_input("입금계좌", key=k('acc'))
        ec7, ec8 = st.columns(2)
        ec7.text_input("출금사유", key=k('rsn'), disabled=new_type != "출금")
        ec8.text_input("비고", key=k('nts'))

        sv, cx, _ = st.columns([1, 1, 4])
        if sv.button("💾 수정 저장", type="primary"):
            amt = sidebar.parse_amount(st.session_state.get(k('amt')))
            if not amt:
                st.error("금액을 숫자로 입력하세요.")
            else:
                db.update_transaction(
                    tx_id=edit_id, date=str(new_date), amount=amt, tx_type=new_type,
                    depositor=st.session_state[k('dep')].strip() or None,
                    customer=st.session_state[k('cust')].strip() or None,
                    account=st.session_state[k('acc')].strip() or None,
                    notes=st.session_state[k('nts')].strip() or None,
                    out_reason=(st.session_state[k('rsn')].strip() or None) if new_type == "출금" else None,
                    unit_id=e_unit['id'] if e_unit else tx.get('unit_id'),
                )
                st.session_state.pop('edit_tx_id', None)
                sidebar.flash("✅ 수정 완료")
                st.rerun()
        if cx.button("취소"):
            st.session_state.pop('edit_tx_id', None)
            st.rerun()
        st.markdown("---")

# ── 삭제 확인 ────────────────────────────────────────────────────
del_id = st.session_state.get('del_tx_id')
if del_id and editable and not edit_id:
    tx = db.get_transaction(del_id)
    if not tx or tx['site_id'] != site_id:
        st.session_state.pop('del_tx_id', None)
    else:
        st.warning(f"**삭제 확인:** {tx['date']} | {tx.get('building_no') or ''}동 {tx.get('unit_no') or ''} | "
                   f"{tx['type']} {tx['amount']:,}원")
        ok = st.checkbox("위 내역을 삭제합니다. (되돌릴 수 없음)", key="del_confirm_chk")
        d1, d2, _ = st.columns([1, 1, 4])
        if d1.button("🗑️ 삭제 확인", type="primary", disabled=not ok):
            db.delete_transaction(del_id)
            st.session_state.pop('del_tx_id', None)
            st.session_state.pop('del_confirm_chk', None)
            sidebar.flash("🗑️ 삭제 완료")
            st.rerun()
        if d2.button("취소", key="del_cancel"):
            st.session_state.pop('del_tx_id', None)
            st.rerun()
        st.markdown("---")

if not txs:
    st.info("조건에 맞는 입출금 내역이 없습니다.")
    st.stop()

rows = [{
    "날짜": t['date'], "동": f"{t['building_no']}동" if t.get('building_no') else "", "호수": t.get('unit_no') or '',
    "입금자명": t.get('depositor') or '', "고객명": t.get('customer') or '', "입금계좌": t.get('account') or '',
    "입금액": t['amount'] if t['type'] == '입금' else 0, "출금액": t['amount'] if t['type'] == '출금' else 0,
    "출금사유": t.get('out_reason') or '', "비고": t.get('notes') or '',
} for t in txs]
df = pd.DataFrame(rows)

st.markdown(f"총 **{len(txs)}**건")
event = st.dataframe(
    df, width="stretch", hide_index=True,
    on_select="rerun" if editable else "ignore", selection_mode="single-row",
    column_config={"입금액": st.column_config.NumberColumn(format="localized"),
                   "출금액": st.column_config.NumberColumn(format="localized")},
)

if editable:
    sel = event.selection.rows if hasattr(event, 'selection') else []
    if sel:
        t = txs[sel[0]]
        st.info(f"선택: {t['date']} | {t.get('building_no') or ''}동 {t.get('unit_no') or ''} | "
                f"{t['type']} {t['amount']:,}원")
        a1, a2, _ = st.columns([1, 1, 8])
        if a1.button("✏️ 수정"):
            for key in [x for x in st.session_state if str(x).startswith('edt_')]:
                del st.session_state[key]
            st.session_state['edit_tx_id'] = t['id']
            st.session_state.pop('del_tx_id', None)
            st.rerun()
        if a2.button("🗑️ 삭제"):
            st.session_state['del_tx_id'] = t['id']
            st.session_state.pop('edit_tx_id', None)
            st.rerun()
    else:
        st.caption("행을 클릭하면 수정/삭제 버튼이 나타납니다.")

st.markdown("---")
total_in = sum(r['입금액'] for r in rows)
total_out = sum(r['출금액'] for r in rows)
m1, m2, m3 = st.columns(3)
m1.metric("총 입금액", f"{total_in:,}원")
m2.metric("총 출금액", f"{total_out:,}원")
m3.metric("잔액", f"{total_in - total_out:,}원")

st.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'입출금리스트': df}),
                   file_name=f"입출금리스트_{site['name']}_{start_date}_{end_date}.xlsx", mime=sidebar.XLSX_MIME)
