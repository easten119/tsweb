"""입출금 탭 — 엑셀 '입출금' 시트: 등록(입금항목 태그) · 목록 · 수정/삭제"""
from datetime import date

import pandas as pd
import streamlit as st

import db
from ui import common as cm
from ui import money


def _register(ctx):
    site_id, cfg = ctx['site_id'], ctx['cfg']
    with st.expander("입출금 등록", expanded=False, icon=":material/add:"):
        c = st.columns(2)
        bid, _ = cm.select_building(site_id, key="tx_bld", container=c[0])
        units = db.get_units(site_id=site_id, building_id=bid) if bid else []
        if not units:
            st.caption("호실이 없습니다.")
            return
        unit = cm.select_unit(units, key="tx_unit", container=c[1])
        ct = db.get_active_contract(unit['id'])
        n = money.round_of('_txr')          # 저장 후 입력칸을 비우기 위한 회차
        name = (ct or {}).get('customer_name') or ''
        r = st.columns([1.1, 0.8, 1.3, 1.6])
        d = r[0].date_input("날짜", value=date.today(), format="YYYY-MM-DD", key=f"txr_d_{n}")
        ttype = r[1].selectbox("구분", ["입금", "출금"], key=f"txr_t_{n}")
        item = r[2].selectbox("입금항목", [''] + cfg['payment_items'], key=f"txr_i_{n}")
        with r[3]:
            amt = money.money_input("금액 (원)", key=f"txr_a_{n}_{unit['id']}")
        r = st.columns(4)
        dep = r[0].text_input("입금자명", value=name, key=f"txr_dep_{n}_{unit['id']}")
        cust = r[1].text_input("고객명", value=name, key=f"txr_c_{n}_{unit['id']}")
        acc = r[2].text_input("입금계좌", placeholder="예: 태성, 무궁화신탁", key=f"txr_acc_{n}")
        rsn = r[3].text_input("출금사유", key=f"txr_r_{n}")
        nts = st.text_input("비고", key=f"txr_n_{n}")
        if st.button("저장", type="primary", key=f"txr_save_{n}", icon=":material/save:"):
            if not amt:
                st.error("금액을 입력하세요.")
            elif ttype == '출금' and not rsn.strip():
                st.error("출금 시에는 출금사유를 입력하세요.")
            else:
                db.add_transaction(site_id, str(d), depositor=dep.strip() or None, customer=cust.strip() or None,
                                   account=acc.strip() or None, amount=amt, tx_type=ttype,
                                   notes=nts.strip() or None, unit_id=unit['id'], item=item or None,
                                   out_reason=(rsn.strip() or None) if ttype == '출금' else None)
                money.next_round('_txr')
                cm.flash(f"{unit['building_no']}동 {unit['unit_no']}호 {ttype} {amt:,}원 저장")
                st.rerun()


def _edit(ctx, tx):
    cfg = ctx['cfg']
    st.markdown(f"<div class='ts-section'>거래 수정 — {tx.get('building_no') or ''}동 {tx.get('unit_no') or ''}호</div>",
                unsafe_allow_html=True)
    items = [''] + cfg['payment_items'] + ([tx['item']] if tx.get('item') and tx['item'] not in cfg['payment_items'] else [])
    k = f"txe_{tx['id']}"
    r = st.columns([1.1, 0.8, 1.3, 1.6])
    d = r[0].date_input("날짜", value=cm.to_date(tx['date']) or date.today(), format="YYYY-MM-DD", key=f"{k}_d")
    ttype = r[1].selectbox("구분", ["입금", "출금"], index=0 if tx['type'] == '입금' else 1, key=f"{k}_t")
    item = r[2].selectbox("입금항목", items, index=items.index(tx.get('item') or ''), key=f"{k}_i")
    with r[3]:
        amt = money.money_input("금액 (원)", key=f"{k}_a", value=tx['amount'])
    r = st.columns(4)
    dep = r[0].text_input("입금자명", value=tx.get('depositor') or '', key=f"{k}_dep")
    cust = r[1].text_input("고객명", value=tx.get('customer') or '', key=f"{k}_c")
    acc = r[2].text_input("입금계좌", value=tx.get('account') or '', key=f"{k}_acc")
    rsn = r[3].text_input("출금사유", value=tx.get('out_reason') or '', key=f"{k}_r")
    nts = st.text_input("비고", value=tx.get('notes') or '', key=f"{k}_n")
    s1, s2, _ = st.columns([1, 1, 5])
    if s1.button("수정 저장", type="primary", key=f"{k}_save"):
        if not amt:
            st.error("금액을 입력하세요.")
            return
        db.update_transaction(tx['id'], str(d), depositor=dep.strip() or None, customer=cust.strip() or None,
                              account=acc.strip() or None, amount=amt, tx_type=ttype, notes=nts.strip() or None,
                              unit_id=tx.get('unit_id'), item=item or None,
                              out_reason=(rsn.strip() or None) if ttype == '출금' else None)
        cm.flash("수정 완료")
        st.rerun()
    with s2.popover("삭제"):
        st.caption(f"{tx['date']} {tx['type']} {tx['amount']:,}원을 삭제합니다. 되돌릴 수 없습니다.")
        if st.button("삭제 확인", type="primary", key=f"{k}_del"):
            db.delete_transaction(tx['id'])
            cm.flash("삭제 완료")
            st.rerun()


def render(ctx):
    site_id, cfg, editable = ctx['site_id'], ctx['cfg'], ctx['editable']
    if editable:
        _register(ctx)

    today = date.today()
    f = st.columns([1, 1, 1, 0.9, 1.2, 2])
    start = f[0].date_input("시작일", value=date(today.year, 1, 1), format="YYYY-MM-DD", key="txl_s")
    end = f[1].date_input("종료일", value=today, format="YYYY-MM-DD", key="txl_e")
    bid, _ = cm.select_building(site_id, key="txl_b", container=f[2], include_all=True)
    ttype = f[3].selectbox("구분", ["전체", "입금", "출금"], key="txl_t")
    item = f[4].selectbox("입금항목", ["전체"] + cfg['payment_items'] + ["(미지정)"], key="txl_i")
    kw = f[5].text_input("검색", placeholder="호수·입금자·고객명·계좌·비고", key="txl_q")

    txs = db.get_transactions(site_id=site_id, start_date=start, end_date=end,
                              tx_type=None if ttype == "전체" else ttype)
    if bid:
        uids = {u['id'] for u in db.get_units(site_id=site_id, building_id=bid)}
        txs = [t for t in txs if t.get('unit_id') in uids]
    if item != "전체":
        txs = [t for t in txs if (t.get('item') or "(미지정)") == item]
    if kw.strip():
        k = kw.strip()
        txs = [t for t in txs if any(k in str(t.get(c) or '') for c in
                                     ('unit_no', 'depositor', 'customer', 'account', 'notes', 'out_reason'))]
    txs = sorted(txs, key=lambda t: (t['date'], t['id']))
    if not txs:
        st.info("조건에 맞는 입출금 내역이 없습니다.")
        return

    df = pd.DataFrame([{
        '날짜': t['date'], '동': t.get('building_no') or '', '호수': t.get('unit_no') or '',
        '입금자명': t.get('depositor') or '', '고객명': t.get('customer') or '', '입금계좌': t.get('account') or '',
        '입금항목': t.get('item') or '',
        '입금액': t['amount'] if t['type'] == '입금' else 0, '출금액': t['amount'] if t['type'] == '출금' else 0,
        '출금사유': t.get('out_reason') or '', '비고': t.get('notes') or ''} for t in txs])
    tin, tout = int(df['입금액'].sum()), int(df['출금액'].sum())
    st.caption(f"{len(df):,}건 · 입금 {tin:,}원 · 출금 {tout:,}원 · 잔액 {tin - tout:,}원")
    event = st.dataframe(df, hide_index=True, placeholder="", width="stretch", height=480,
                         on_select="rerun" if editable else "ignore", selection_mode="single-row",
                         column_config={'입금액': cm.MONEY, '출금액': cm.MONEY}, key="txl_df")
    st.download_button("엑셀 다운로드", icon=":material/download:", data=cm.excel_bytes({'입출금': df}),
                       file_name=f"{ctx['site']['name']}_입출금_{start}_{end}.xlsx", mime=cm.XLSX_MIME)
    rows = event.selection.rows if editable and hasattr(event, 'selection') else []
    if rows:
        _edit(ctx, db.get_transaction(txs[rows[0]]['id']))
    elif editable:
        st.caption("행을 클릭하면 수정·삭제할 수 있습니다.")
