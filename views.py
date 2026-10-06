"""views.py — 여러 페이지에서 함께 쓰는 화면 조각"""
import pandas as pd
import streamlit as st
import db
import sidebar


def render_unit_detail(unit, show_title=True):
    """호실 정보 + 유효 계약 + 계약/해지 이력 + 입출금 내역."""
    if show_title:
        st.subheader(f"🔍 {sidebar.unit_title(unit)}")

    active = db.get_active_contract(unit['id'])
    contracts = db.get_contracts(unit_id=unit['id'])
    cancels = db.get_cancellations(unit_id=unit['id'])
    txs = db.get_transactions(unit_id=unit['id'])
    total_in = sum(t['amount'] for t in txs if t['type'] == '입금')
    total_out = sum(t['amount'] for t in txs if t['type'] == '출금')

    info_col, contract_col = st.columns(2)
    with info_col:
        st.markdown("##### 호실 정보")
        st.markdown(
            f"- 타입: **{unit.get('type') or '-'}**  \n"
            f"- 층/라인: **{unit.get('floor') or '-'}층 {unit.get('line') or '-'}라인**  \n"
            f"- 상태: **{unit.get('status', '-')}**  \n"
            f"- 분양가: **{(unit.get('sale_price') or 0):,}원**  \n"
            f"- 계약금(기준): **{(unit.get('rental_price') or 0):,}원**"
        )
    with contract_col:
        st.markdown("##### 현재 계약")
        if active:
            st.markdown(
                f"- 계약자명: **{active.get('customer_name') or '-'}**  \n"
                f"- 연락처: **{active.get('phone') or '-'}**  \n"
                f"- 계약일: **{active.get('contract_date') or '-'}**  \n"
                f"- 계약구분: **{active.get('contract_type') or '-'}**  \n"
                f"- 담당: **{active.get('assigned_team') or '-'} / {active.get('assigned_staff') or '-'}**  \n"
                f"- 계약금: **{(active.get('deposit_total') or 0):,}원**"
            )
            if active.get('notes'):
                st.markdown(f"- 비고: {active['notes']}")
        else:
            st.info("유효한 계약 없음 (공실)")

    st.markdown("---")
    deposit = (active or {}).get('deposit_total') or 0
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("총 입금액", f"{total_in:,}원")
    s2.metric("총 출금액", f"{total_out:,}원")
    s3.metric("잔액", f"{total_in - total_out:,}원")
    if active and deposit:
        s4.metric("계약금 대비 미납", f"{max(deposit - (total_in - total_out), 0):,}원")

    if txs:
        st.markdown("##### 입출금 내역")
        st.dataframe(pd.DataFrame([{
            "날짜": t["date"], "구분": t["type"],
            "입금자명": t.get("depositor") or "", "고객명": t.get("customer") or "",
            "입금액": t['amount'] if t["type"] == "입금" else None,
            "출금액": t['amount'] if t["type"] == "출금" else None,
            "출금사유": t.get("out_reason") or "", "비고": t.get("notes") or "",
        } for t in sorted(txs, key=lambda x: x["date"])]), width="stretch", hide_index=True,
            column_config={"입금액": st.column_config.NumberColumn(format="localized"),
                           "출금액": st.column_config.NumberColumn(format="localized")})
    else:
        st.caption("입출금 내역 없음")

    if len(contracts) > 1 or cancels:
        with st.expander(f"계약·해지 이력 (계약 {len(contracts)}건 / 해지 {len(cancels)}건)"):
            if contracts:
                st.dataframe(pd.DataFrame([{
                    '상태': c.get('status'), '계약구분': c.get('contract_type'), '계약자': c.get('customer_name'),
                    '계약일': c.get('contract_date'), '해지일': c.get('cancelled_at') or '',
                    '계약금': c.get('deposit_total') or 0,
                } for c in contracts]), width="stretch", hide_index=True)
            if cancels:
                st.dataframe(pd.DataFrame([{
                    '해지접수일': c.get('cancel_date'), '계약자': c.get('customer_name') or '(계약정보 없음)',
                    '환불금액': c.get('refund_amount') or 0, '환불은행': c.get('bank') or '',
                    '비고': c.get('notes') or '',
                } for c in cancels]), width="stretch", hide_index=True)
