import streamlit as st
from datetime import date
import db
import sidebar

user = sidebar.page_setup("해지", "❌", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

site_id, site, _ = sidebar.select_site(user)

c1, c2 = st.columns(2)
bld_id, _ = sidebar.select_building(site_id, container=c1)
units = [u for u in db.get_units(site_id=site_id, building_id=bld_id) if u['status'] in ('가계약', '계약')]
if not units:
    c2.warning("해지 가능한 호실이 없습니다. (가계약/계약 상태 호실만 선택 가능)")
    st.stop()
unit = sidebar.select_unit(units, container=c2)

contract = db.get_active_contract(unit['id'])
if not contract:
    st.error("이 호실에 유효한 계약 기록이 없습니다. 관리자에게 '데이터 점검'을 요청하세요.")
    st.stop()

txs = db.get_transactions(unit_id=unit['id'])
paid = sum(t['amount'] for t in txs if t['type'] == '입금') - sum(t['amount'] for t in txs if t['type'] == '출금')

st.info(f"**선택 호실:** {sidebar.unit_title(unit)}　｜　{contract['contract_type']}　｜　"
        f"계약자 {contract['customer_name']} ({contract.get('phone') or '-'})　｜　계약일 {contract.get('contract_date') or '-'}　｜　"
        f"계약금 {(contract.get('deposit_total') or 0):,}원　｜　입금 잔액 {paid:,}원")

with st.form(f"form_cancel_{contract['id']}", clear_on_submit=True):
    r1c1, r1c2 = st.columns(2)
    cancel_date = r1c1.date_input("해지접수일", value=date.today())
    refund_bank = r1c2.text_input("환불은행")
    r2c1, r2c2 = st.columns(2)
    account_no = r2c1.text_input("계좌번호")
    refund_amount = r2c2.number_input("환불금액 (원)", value=0, step=100_000, min_value=0, format="%d",
                                      help=f"참고: 현재 입금 잔액 {paid:,}원")
    notes = st.text_area("비고 (해지 사유 등)", height=80)
    confirm = st.checkbox(f"{contract['customer_name']} 님의 계약을 해지하고 호실을 공실로 전환합니다.")

    if st.form_submit_button("❌ 해지 처리", type="primary", width="stretch"):
        if not confirm:
            st.error("확인 체크박스를 선택하세요.")
        else:
            try:
                db.cancel_contract(contract['id'], cancel_date=str(cancel_date), refund_amount=int(refund_amount),
                                   bank=refund_bank.strip() or None, account_no=account_no.strip() or None,
                                   notes=notes.strip() or None)
            except ValueError as e:
                st.error(str(e))
            else:
                sidebar.flash(f"✅ 해지 처리 완료: {sidebar.unit_title(unit)} — {contract['customer_name']}")
                st.rerun()

st.caption("환불 출금은 '입출금 등록'에서 출금으로 따로 기록하세요.")
