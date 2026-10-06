import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

user = sidebar.page_setup("해지 리스트", "📋")
editable = sidebar.can_edit(user)
sidebar.show_flash()

site_id, site, _ = sidebar.select_site(user)

today = date.today()
fc1, fc2, fc3 = st.columns(3)
start_date = fc1.date_input("시작일 (해지접수일)", value=date(today.year, 1, 1))
end_date = fc2.date_input("종료일 (해지접수일)", value=today)
bld_filter, _ = sidebar.select_building(site_id, key="cl_bld", label="동 필터", container=fc3, include_all=True)

cancels = [c for c in db.get_cancellations(site_id=site_id)
           if str(start_date) <= str(c.get('cancel_date') or '') <= str(end_date)]
if bld_filter:
    unit_ids = {u['id'] for u in db.get_units(site_id=site_id, building_id=bld_filter)}
    cancels = [c for c in cancels if c['unit_id'] in unit_ids]

# ── 수정 폼 ──────────────────────────────────────────────────────
edit_id = st.session_state.get('edit_cancel_id')
if edit_id and editable:
    ce = db.get_cancellation(edit_id)
    if not ce or ce['site_id'] != site_id:
        st.session_state.pop('edit_cancel_id', None)
    else:
        st.subheader("✏️ 해지 내역 수정")
        st.caption(f"대상: {ce.get('building_no')}동 {ce.get('unit_no')} | {ce.get('customer_name') or '-'}")
        k = lambda n: f"edt_c_{n}_{edit_id}"  # noqa: E731
        if k('init') not in st.session_state:
            st.session_state[k('init')] = True
            st.session_state[k('amt')] = f"{ce.get('refund_amount') or 0:,}"
            st.session_state[k('bank')] = ce.get('bank') or ''
            st.session_state[k('acno')] = ce.get('account_no') or ''
            st.session_state[k('nts')] = ce.get('notes') or ''
        e1, e2 = st.columns(2)
        new_date = e1.date_input("해지접수일", key=k('date'),
                                 value=date.fromisoformat(ce['cancel_date']) if ce.get('cancel_date') else today)
        e2.text_input("환불은행", key=k('bank'))
        e3, e4 = st.columns(2)
        e3.text_input("계좌번호", key=k('acno'))
        e4.text_input("환불금액 (원)", key=k('amt'), on_change=sidebar.fmt_amount_key, args=(k('amt'),))
        st.text_area("비고", key=k('nts'), height=80)
        s1, s2, _ = st.columns([1, 1, 4])
        if s1.button("💾 수정 저장", type="primary"):
            amt = sidebar.parse_amount(st.session_state[k('amt')])
            if amt is None:
                st.error("환불금액은 숫자로 입력하세요.")
            else:
                db.update_cancellation(edit_id, cancel_date=str(new_date), refund_amount=amt,
                                       bank=st.session_state[k('bank')].strip() or None,
                                       account_no=st.session_state[k('acno')].strip() or None,
                                       notes=st.session_state[k('nts')].strip() or None)
                st.session_state.pop('edit_cancel_id', None)
                sidebar.flash("✅ 수정 완료")
                st.rerun()
        if s2.button("취소"):
            st.session_state.pop('edit_cancel_id', None)
            st.rerun()
        st.markdown("---")

# ── 해지 취소 확인 ────────────────────────────────────────────────
undo_id = st.session_state.get('undo_cancel_id')
if undo_id and editable and not edit_id:
    cd = db.get_cancellation(undo_id)
    if not cd or cd['site_id'] != site_id:
        st.session_state.pop('undo_cancel_id', None)
    else:
        st.warning(f"**해지 취소:** {cd.get('cancel_date')} | {cd.get('building_no')}동 {cd.get('unit_no')} | "
                   f"{cd.get('customer_name') or '-'}  \n해지 내역을 지우고 원래 계약을 다시 유효 상태로 되돌립니다.")
        ok = st.checkbox("해지를 취소합니다.", key="undo_chk")
        u1, u2, _ = st.columns([1, 1, 4])
        if u1.button("↩️ 해지 취소 확인", type="primary", disabled=not ok):
            success, msg = db.delete_cancellation(undo_id)
            st.session_state.pop('undo_cancel_id', None)
            st.session_state.pop('undo_chk', None)
            sidebar.flash(msg, "success" if success else "error")
            st.rerun()
        if u2.button("닫기"):
            st.session_state.pop('undo_cancel_id', None)
            st.rerun()
        st.markdown("---")

if not cancels:
    st.info("조건에 맞는 해지 내역이 없습니다.")
    st.stop()

df = pd.DataFrame([{
    "동": f"{c.get('building_no')}동", "호수": c.get('unit_no') or '', "타입": c.get('unit_type') or '',
    "해지접수일": c.get('cancel_date') or '', "계약자명": c.get('customer_name') or '(계약정보 없음)',
    "연락처": c.get('phone') or '', "계약일": c.get('contract_date') or '', "환불은행": c.get('bank') or '',
    "계좌번호": c.get('account_no') or '', "환불금액": c.get('refund_amount') or 0, "비고": c.get('notes') or '',
} for c in cancels])

st.markdown(f"총 **{len(df)}**건")
event = st.dataframe(df, width="stretch", hide_index=True,
                     on_select="rerun" if editable else "ignore", selection_mode="single-row",
                     column_config={"환불금액": st.column_config.NumberColumn(format="localized")})

if editable:
    sel = event.selection.rows if hasattr(event, 'selection') else []
    if sel:
        c = cancels[sel[0]]
        st.info(f"선택: {c.get('cancel_date')} | {c.get('building_no')}동 {c.get('unit_no')} | "
                f"{c.get('customer_name') or '-'}")
        a1, a2, _ = st.columns([1, 1.4, 6])
        if a1.button("✏️ 수정"):
            for key in [x for x in st.session_state if str(x).startswith('edt_c_')]:
                del st.session_state[key]
            st.session_state['edit_cancel_id'] = c['id']
            st.session_state.pop('undo_cancel_id', None)
            st.rerun()
        if a2.button("↩️ 해지 취소"):
            st.session_state['undo_cancel_id'] = c['id']
            st.session_state.pop('edit_cancel_id', None)
            st.rerun()
    else:
        st.caption("행을 클릭하면 수정 / 해지 취소 버튼이 나타납니다.")

st.markdown("---")
m1, m2 = st.columns(2)
m1.metric("총 해지 건수", f"{len(df)}건")
m2.metric("총 환불액", f"{int(df['환불금액'].sum()):,}원")

st.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'해지리스트': df}),
                   file_name=f"해지리스트_{site['name']}_{start_date}_{end_date}.xlsx", mime=sidebar.XLSX_MIME)
