"""계좌현황 탭 — 엑셀 '계좌현황' 시트: 계좌별 입금·출금·잔액 + 호실별 원장 조회"""
import pandas as pd
import streamlit as st

import db
from ui import common as cm


def render(ctx):
    site_id = ctx['site_id']
    txs = db.get_transactions(site_id=site_id)
    if not txs:
        st.info("입출금 내역이 없습니다.")
        return
    df = pd.DataFrame([{'계좌': (t.get('account') or '(미기재)').strip(), '구분': t['type'], '금액': t['amount'],
                        '날짜': t['date']} for t in txs])
    summary = (df.pivot_table(index='계좌', columns='구분', values='금액', aggfunc='sum', fill_value=0)
               .reindex(columns=['입금', '출금'], fill_value=0))
    summary['잔액'] = summary['입금'] - summary['출금']
    summary['건수'] = df.groupby('계좌').size()
    summary['최근 거래일'] = df.groupby('계좌')['날짜'].max()
    summary = summary.sort_values('입금', ascending=False).reset_index()

    cm.section("계좌별 현황")
    cards = st.columns(min(len(summary), 4) or 1)
    for i, r in summary.head(4).iterrows():
        cards[i].metric(r['계좌'], f"{int(r['잔액']):,}원",
                        f"입금 {int(r['입금']):,} / 출금 {int(r['출금']):,}", delta_color="off")
    st.dataframe(summary, hide_index=True, placeholder="", width="stretch",
                 column_config={'입금': cm.MONEY, '출금': cm.MONEY, '잔액': cm.MONEY})

    cm.section("호실별 원장 조회")
    c = st.columns([1, 1, 3])
    bid, _ = cm.select_building(site_id, key="ac_b", container=c[0])
    units = db.get_units(site_id=site_id, building_id=bid) if bid else []
    if not units:
        return
    unit = cm.select_unit(units, key="ac_u", container=c[1])
    utx = sorted(db.get_transactions(unit_id=unit['id']), key=lambda t: t['date'])
    if not utx:
        st.caption("이 호실의 입출금 내역이 없습니다.")
        return
    bal = 0
    rows = []
    for t in utx:
        bal += t['amount'] if t['type'] == '입금' else -t['amount']
        rows.append({'날짜': t['date'], '입금자명': t.get('depositor') or '', '입금계좌': t.get('account') or '',
                     '입금항목': t.get('item') or '', '입금액': t['amount'] if t['type'] == '입금' else 0,
                     '출금액': t['amount'] if t['type'] == '출금' else 0, '잔액': bal,
                     '출금사유': t.get('out_reason') or '', '비고': t.get('notes') or ''})
    st.dataframe(pd.DataFrame(rows), hide_index=True, placeholder="", width="stretch",
                 column_config={'입금액': cm.MONEY, '출금액': cm.MONEY, '잔액': cm.MONEY})
