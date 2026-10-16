"""실적 탭 — 엑셀 'pivot' 시트: 일자별·타입별 가계약/계약/해지 + 담당팀·담당자 실적"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from ui import common as cm


def _events(site_id):
    """(날짜, 구분, 타입, 담당팀, 담당자) 이벤트 목록 — 해지된 계약의 가계약·계약 이력도 포함."""
    ev = []
    for c in db.get_contracts(site_id=site_id):
        t = c.get('unit_type') or '-'
        who = (c.get('assigned_team') or '(미지정)', c.get('assigned_staff') or '(미지정)')
        if c.get('pre_date'):
            ev.append((c['pre_date'], '가계약', t) + who)
        if c.get('contract_date') and c.get('contract_type') != '가계약':
            ev.append((c['contract_date'], '계약', t) + who)
    for cl in db.get_cancellations(site_id=site_id):
        if cl.get('cancel_date'):
            ev.append((cl['cancel_date'], '해지', cl.get('unit_type') or '-', '', ''))
    return pd.DataFrame(ev, columns=['날짜', '구분', '타입', '담당팀', '담당자'])


def render(ctx):
    site_id = ctx['site_id']
    ev = _events(site_id)
    if ev.empty:
        st.info("가계약·계약·해지 기록이 없습니다. (계약관리에서 가계약일·계약일을 입력하면 집계됩니다)")
        return
    today = date.today()
    f = st.columns([1, 1, 4])
    start = f[0].date_input("시작일", value=today - timedelta(days=30), format="YYYY-MM-DD", key="st_s")
    end = f[1].date_input("종료일", value=today, format="YYYY-MM-DD", key="st_e")
    ev = ev[(ev['날짜'] >= str(start)) & (ev['날짜'] <= str(end))]
    if ev.empty:
        st.info("기간 내 기록이 없습니다.")
        return

    cnt = ev['구분'].value_counts()
    m = st.columns(4)
    m[0].metric("가계약", f"{cnt.get('가계약', 0)}건")
    m[1].metric("계약", f"{cnt.get('계약', 0)}건")
    m[2].metric("해지", f"{cnt.get('해지', 0)}건")
    m[3].metric("순증 (계약-해지)", f"{cnt.get('계약', 0) - cnt.get('해지', 0)}건")

    cm.section("일자별 추이")
    daily = ev.pivot_table(index='날짜', columns='구분', values='타입', aggfunc='count', fill_value=0)
    daily = daily.reindex(columns=[c for c in ['가계약', '계약', '해지'] if c in daily.columns])
    st.bar_chart(daily, height=220, stack=False)

    for kind in ('가계약', '계약', '해지'):
        sub = ev[ev['구분'] == kind]
        if sub.empty:
            continue
        cm.section(f"{kind} — 일자 × 타입")
        pv = sub.pivot_table(index='날짜', columns='타입', values='구분', aggfunc='count', fill_value=0)
        pv['합계'] = pv.sum(axis=1)
        pv.loc['총합계'] = pv.sum()
        st.dataframe(pv.sort_index(ascending=False), width="stretch")

    cm.section("담당팀·담당자 실적")
    sales = ev[ev['구분'].isin(['가계약', '계약'])]
    if not sales.empty:
        pv = sales.pivot_table(index=['담당팀', '담당자'], columns='구분', values='타입', aggfunc='count', fill_value=0)
        pv['합계'] = pv.sum(axis=1)
        st.dataframe(pv.sort_values('합계', ascending=False), width="stretch")
    st.download_button("엑셀 다운로드", icon=":material/download:",
                       data=cm.excel_bytes({'실적_원자료': ev.sort_values('날짜')}),
                       file_name=f"{ctx['site']['name']}_실적_{start}_{end}.xlsx", mime=cm.XLSX_MIME)
