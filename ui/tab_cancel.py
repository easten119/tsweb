"""해지 탭 — 해지 처리 · 해지 목록 · 수정 · 해지 취소(원 계약 복구)"""
from datetime import date

import pandas as pd
import streamlit as st

import db
import templates
from ui import common as cm


def _cancel_form(ctx):
    site_id, cfg = ctx['site_id'], ctx['cfg']
    statuses = templates.status_names(cfg)
    contracts = db.get_contracts(site_id=site_id, active_only=True)
    if not contracts:
        st.caption("해지할 유효 계약이 없습니다.")
        return
    contracts.sort(key=lambda c: (str(c['building_no']), str(c['unit_no'])))
    by_id = {c['id']: c for c in contracts}
    pre = st.session_state.pop('_cancel_unit', None)
    default = next((c['id'] for c in contracts if c['unit_id'] == pre), None)
    if default:
        st.session_state['cx_ct'] = default
    cid = st.selectbox("해지할 계약", list(by_id), key="cx_ct",
                       format_func=lambda i: f"{by_id[i]['building_no']}동 {by_id[i]['unit_no']}호 · "
                                             f"{by_id[i]['customer_name']} · {by_id[i]['contract_type']}")
    ct = by_id[cid]
    txs = db.get_transactions(unit_id=ct['unit_id'])
    paid = sum(t['amount'] for t in txs if t['type'] == '입금') - sum(t['amount'] for t in txs if t['type'] == '출금')
    st.caption(f"계약일 {ct.get('contract_date') or ct.get('pre_date') or '-'} · 계약금 {cm.won(ct.get('deposit_total'))}원 · "
               f"입금 잔액 {paid:,}원")
    with st.form(f"cx_form_{cid}", clear_on_submit=True):
        r = st.columns(4)
        cdate = r[0].date_input("해지접수일", value=date.today(), format="YYYY-MM-DD")
        refund = r[1].number_input("환불금액", min_value=0, step=100000, format="%d", help=f"입금 잔액 {paid:,}원")
        bank = r[2].text_input("환불은행")
        acno = r[3].text_input("계좌번호")
        notes = st.text_input("비고 (해지 사유 등)")
        ok = st.checkbox(f"{ct['customer_name']} 님의 계약을 해지하고 호실을 공실로 전환합니다.")
        if st.form_submit_button("해지 처리", type="primary"):
            if not ok:
                st.error("확인란을 선택하세요.")
            else:
                db.cancel_contract(cid, cancel_date=str(cdate), refund_amount=int(refund), bank=bank.strip() or None,
                                   account_no=acno.strip() or None, notes=notes.strip() or None)
                cm.flash(f"{ct['building_no']}동 {ct['unit_no']}호 해지 처리 완료")
                st.rerun()
    st.caption("환불 출금은 입출금 탭에서 출금으로 기록하세요.")


def render(ctx):
    site_id, editable = ctx['site_id'], ctx['editable']
    if editable:
        with st.expander("해지 처리", icon=":material/block:",
                         expanded=bool(st.session_state.get('_cancel_unit'))):
            _cancel_form(ctx)

    cancels = db.get_cancellations(site_id=site_id)
    if not cancels:
        st.info("해지 내역이 없습니다.")
        return
    df = pd.DataFrame([{
        '해지접수일': c.get('cancel_date') or '', '동': c.get('building_no'), '호수': c.get('unit_no'),
        '타입': c.get('unit_type') or '', '계약자명': c.get('customer_name') or '(계약정보 없음)',
        '연락처': c.get('phone') or '', '이전 상태': c.get('contract_type') or '', '계약일': c.get('contract_date') or '',
        '환불금액': c.get('refund_amount') or 0, '환불은행': c.get('bank') or '', '계좌번호': c.get('account_no') or '',
        '비고': c.get('notes') or ''} for c in cancels])
    st.caption(f"해지 {len(df)}건 · 환불 합계 {int(df['환불금액'].sum()):,}원")
    event = st.dataframe(df, hide_index=True, placeholder="", width="stretch", on_select="rerun" if editable else "ignore",
                         selection_mode="single-row", column_config={'환불금액': cm.MONEY}, key="cx_df")
    st.download_button("엑셀 다운로드", icon=":material/download:", data=cm.excel_bytes({'해지': df}),
                       file_name=f"{ctx['site']['name']}_해지.xlsx", mime=cm.XLSX_MIME)
    rows = event.selection.rows if editable and hasattr(event, 'selection') else []
    if not rows:
        return
    c = cancels[rows[0]]
    st.markdown(f"<div class='ts-section'>해지 내역 — {c['building_no']}동 {c['unit_no']}호 "
                f"{c.get('customer_name') or ''}</div>", unsafe_allow_html=True)
    with st.form(f"cx_edit_{c['id']}"):
        r = st.columns(4)
        cdate = r[0].date_input("해지접수일", value=cm.to_date(c.get('cancel_date')) or date.today(), format="YYYY-MM-DD")
        refund = r[1].number_input("환불금액", value=int(c.get('refund_amount') or 0), min_value=0, step=100000,
                                   format="%d")
        bank = r[2].text_input("환불은행", value=c.get('bank') or '')
        acno = r[3].text_input("계좌번호", value=c.get('account_no') or '')
        notes = st.text_input("비고", value=c.get('notes') or '')
        if st.form_submit_button("수정 저장", type="primary"):
            db.update_cancellation(c['id'], cancel_date=str(cdate), refund_amount=int(refund),
                                   bank=bank.strip() or None, account_no=acno.strip() or None,
                                   notes=notes.strip() or None)
            cm.flash("수정 완료")
            st.rerun()
    with st.popover("해지 취소 (원 계약 복구)", icon=":material/undo:"):
        st.caption("해지 내역을 지우고 원래 계약을 다시 유효 상태로 되돌립니다. "
                   "그 사이 같은 호실에 새 계약이 있으면 취소할 수 없습니다.")
        if st.button("해지 취소 확인", type="primary", key=f"cx_undo_{c['id']}"):
            ok, msg = db.delete_cancellation(c['id'])
            cm.flash(msg, "success" if ok else "error")
            st.rerun()
