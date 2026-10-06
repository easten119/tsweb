import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

user = sidebar.page_setup("입출금 등록", "💰", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

site_id, site, _ = sidebar.select_site(user)

c1, c2 = st.columns(2)
bld_id, _ = sidebar.select_building(site_id, container=c1)
units = db.get_units(site_id=site_id, building_id=bld_id)
if not units:
    c2.warning("호실이 없습니다.")
    st.stop()
unit = sidebar.select_unit(units, container=c2)

active = db.get_active_contract(unit['id'])
st.info(f"**선택 호실:** {sidebar.unit_title(unit)}　｜　상태: {unit['status']}"
        + (f"　｜　계약자: {active['customer_name']}" if active else ""))

FIELDS = ["reg_amount_in", "reg_amount_out", "reg_depositor", "reg_customer",
          "reg_account", "reg_out_reason", "reg_notes"]

# 호실이 바뀌면 고객명 기본값을 계약자명으로
if st.session_state.get('_reg_unit') != unit['id']:
    st.session_state['_reg_unit'] = unit['id']
    st.session_state['reg_customer'] = active['customer_name'] if active else ''

st.markdown("---")
r1c1, r1c2 = st.columns(2)
tx_date = r1c1.date_input("날짜", value=date.today(), key="reg_tx_date")
r1c2.text_input("입금자명", key="reg_depositor")

r2c1, r2c2 = st.columns(2)
r2c1.text_input("고객명", key="reg_customer")
r2c2.text_input("입금계좌", key="reg_account")

r3c1, r3c2 = st.columns(2)
r3c1.text_input("입금액 (원)", key="reg_amount_in", placeholder="예: 1,000,000",
                on_change=sidebar.fmt_amount_key, args=("reg_amount_in",))
r3c2.text_input("출금액 (원)", key="reg_amount_out", placeholder="예: 500,000",
                on_change=sidebar.fmt_amount_key, args=("reg_amount_out",))

r4c1, r4c2 = st.columns(2)
r4c1.text_input("출금사유", key="reg_out_reason")
r4c2.text_input("비고", key="reg_notes")

if st.button("💾 저장", type="primary", width="stretch"):
    amount_in = sidebar.parse_amount(st.session_state.get("reg_amount_in"))
    amount_out = sidebar.parse_amount(st.session_state.get("reg_amount_out"))
    if amount_in is None or amount_out is None:
        st.error("금액에 숫자 외 문자가 포함되어 있습니다.")
    elif not amount_in and not amount_out:
        st.error("입금액 또는 출금액을 입력하세요.")
    elif amount_out and not st.session_state.get("reg_out_reason", "").strip():
        st.error("출금 시에는 출금사유를 입력하세요.")
    else:
        common = dict(
            site_id=site_id, date=str(tx_date), unit_id=unit['id'],
            depositor=st.session_state.get("reg_depositor", "").strip() or None,
            customer=st.session_state.get("reg_customer", "").strip() or None,
            account=st.session_state.get("reg_account", "").strip() or None,
            notes=st.session_state.get("reg_notes", "").strip() or None,
        )
        saved = []
        if amount_in:
            db.add_transaction(amount=amount_in, tx_type="입금", **common)
            saved.append(f"입금 {amount_in:,}원")
        if amount_out:
            db.add_transaction(amount=amount_out, tx_type="출금",
                               out_reason=st.session_state.get("reg_out_reason", "").strip(), **common)
            saved.append(f"출금 {amount_out:,}원")
        for k in FIELDS:
            st.session_state.pop(k, None)
        st.session_state.pop('_reg_unit', None)
        sidebar.flash(f"✅ 저장 완료 ({sidebar.unit_title(unit)}): {', '.join(saved)}")
        st.rerun()

# ── 이 호실의 최근 입출금 ──────────────────────────────────────────
txs = db.get_transactions(unit_id=unit['id'])
if txs:
    st.markdown("---")
    t_in = sum(t['amount'] for t in txs if t['type'] == '입금')
    t_out = sum(t['amount'] for t in txs if t['type'] == '출금')
    st.markdown(f"#### 이 호실 입출금 내역 · 입금 {t_in:,}원 / 출금 {t_out:,}원 / 잔액 {t_in - t_out:,}원")
    st.dataframe(pd.DataFrame([{
        '날짜': t['date'], '구분': t['type'], '금액': t['amount'], '입금자명': t.get('depositor') or '',
        '출금사유': t.get('out_reason') or '', '비고': t.get('notes') or ''} for t in txs[:10]]),
        width="stretch", hide_index=True,
        column_config={'금액': st.column_config.NumberColumn(format="localized")})
