import streamlit as st
import pandas as pd
from datetime import timedelta
from collections import defaultdict
import db
import calc
import sidebar

user = sidebar.page_setup("정산 대장", "📋", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()
st.caption("집행일 기준으로 일비 + 숙소비를 통합 산출합니다. (집행일은 매월 5일 / 20일)")

allowed_ids = sidebar.accessible_site_ids(user)   # manager → 담당 현장만, admin → None

c1, c2, c3 = st.columns([2, 1, 1])
site_id, _, site_options = sidebar.select_site(user, allow_all=True, container=c1)
exec_options = calc.nearest_execution_dates()
exec_date = c2.selectbox("집행일", exec_options, index=exec_options.index(calc.default_execution_date()),
                         format_func=lambda d: d.strftime('%Y-%m-%d (%a)'))
c3.markdown("<br>", unsafe_allow_html=True)
calc_btn = c3.button("🔍 조회", type="primary", width="stretch")

d_year, d_month, d_term = calc.daily_term_for_execution(exec_date)
d_ps, d_pe = calc.term_period(d_year, d_month, d_term)
st.caption(f"일비: {d_year}년 {d_month}월 {d_term}차 ({d_ps} ~ {d_pe}) · 숙소비: {exec_date} 집행 대상")

_RK, _CK = '_settle_result', '_settle_ctx'
_ctx = (site_id, str(exec_date))
if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if calc_btn:
    targets = site_options if site_id is None else [s for s in site_options if s['id'] == site_id]
    rows = []
    for site in targets:
        sid = site['id']
        rates = db.get_site_rates(sid)
        look_from = min(calc.daily_attendance_range(d_year, d_month, d_term)[0],
                        exec_date - timedelta(days=calc.HOUSING_LOOKBACK_DAYS))
        employees = db.get_employees_for_period(sid, min(d_ps, exec_date - timedelta(days=calc.HOUSING_LOOKBACK_DAYS)),
                                                exec_date)
        att = calc.load_attendance(sid, look_from, max(d_pe, exec_date))
        labels = sidebar.employee_labels(employees)
        for emp in employees:
            dr = calc.calc_daily_allowance(emp['id'], d_year, d_month, d_term, daily_rate=rates[0], att=att)
            hr = calc.calc_housing(emp['id'], exec_date, emp=emp, rates=rates, att=att)
            daily_amt = dr['amount'] if dr['status'] == '지급' else 0
            housing_amt = hr['amount'] if (hr['is_target'] and hr['is_qualified']) else 0
            if daily_amt + housing_amt == 0:
                continue
            rows.append({'site_id': sid, 'site_name': site['name'], 'emp_id': emp['id'], 'label': labels[emp['id']],
                         'division': emp.get('division') or '', 'team': emp.get('team') or '',
                         'region': emp.get('housing_region'), 'dr': dr, 'hr': hr,
                         'daily_amt': daily_amt, 'housing_amt': housing_amt})
    st.session_state[_RK] = rows
    st.session_state[_CK] = _ctx

rows = st.session_state.get(_RK)
if rows is None:
    st.info("현장과 집행일을 선택한 뒤 [🔍 조회] 버튼을 누르세요.")
elif not rows:
    st.info("집행 대상 직원이 없습니다.")
else:
    show_site = site_id is None
    table = []
    groups = defaultdict(list)
    for r in rows:
        groups[(r['site_name'], r['division']) if show_site else r['division']].append(r)

    def line(r):
        return {'현장': r['site_name'], '본부': r['division'], '팀': r['team'], '이름': r['label'],
                '일비(지급일수)': r['dr']['pay_days'] if r['daily_amt'] else 0, '일비금액': r['daily_amt'],
                '숙소비': '○' if r['housing_amt'] else '-', '지역구분': r['region'] if r['housing_amt'] else '-',
                '숙소비금액': r['housing_amt'], '합계금액': r['daily_amt'] + r['housing_amt']}

    def subtotal(label, grp):
        return {'현장': '', '본부': label, '팀': '', '이름': '',
                '일비(지급일수)': sum(line(r)['일비(지급일수)'] for r in grp),
                '일비금액': sum(r['daily_amt'] for r in grp), '숙소비': '', '지역구분': '',
                '숙소비금액': sum(r['housing_amt'] for r in grp),
                '합계금액': sum(r['daily_amt'] + r['housing_amt'] for r in grp)}

    for key in sorted(groups, key=lambda k: k if isinstance(k, tuple) else ('', k)):
        grp = groups[key]
        table += [line(r) for r in grp]
        lbl = f"{key[0]} / {key[1] or '(미분류)'}" if isinstance(key, tuple) else (key or '(미분류)')
        table.append(subtotal(f"▶ {lbl} 소계", grp))
    table.append(subtotal('▶▶ 전체 총계', rows))

    cols = (['현장'] if show_site else []) + ['본부', '팀', '이름', '일비(지급일수)', '일비금액', '숙소비', '지역구분',
                                              '숙소비금액', '합계금액']
    tdf = pd.DataFrame(table)[cols]

    def _row_style(row):
        label = str(row.get('본부', ''))
        if '총계' in label:
            return ['font-weight: bold; background-color: #c8d8e8'] * len(row)
        if '소계' in label:
            return ['font-weight: bold; background-color: #e8e8e8'] * len(row)
        return [''] * len(row)

    st.dataframe(tdf.style.apply(_row_style, axis=1).format({'일비금액': '{:,}', '숙소비금액': '{:,}', '합계금액': '{:,}'}),
                 width="stretch", hide_index=True)

    total_daily = sum(r['daily_amt'] for r in rows)
    total_house = sum(r['housing_amt'] for r in rows)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 집행 인원", f"{len(rows)}명")
    m2.metric("일비 총액", f"{total_daily:,}원")
    m3.metric("숙소비 총액", f"{total_house:,}원")
    m4.metric("합계 총액", f"{total_daily + total_house:,}원")

    st.markdown("---")
    col_dl, col_save = st.columns(2)
    col_dl.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'정산대장': tdf}),
                           file_name=f"{exec_date}_정산대장.xlsx", mime=sidebar.XLSX_MIME, width="stretch")
    if col_save.button("💾 정산이력 일괄저장 (일비 + 숙소비)", width="stretch"):
        items = []
        for r in rows:
            if r['daily_amt']:
                dr = r['dr']
                items.append(dict(site_id=r['site_id'], employee_id=r['emp_id'], settlement_type='daily_allowance',
                                  execution_date=dr['execution_date'], period_start=dr['period_start'],
                                  period_end=dr['period_end'], work_days=dr['work_days'], amount=r['daily_amt']))
            if r['housing_amt']:
                hr = r['hr']
                items.append(dict(site_id=r['site_id'], employee_id=r['emp_id'], settlement_type='housing',
                                  execution_date=exec_date, period_start=hr['period_start'],
                                  period_end=hr['period_end'], work_days=hr['work_days'], amount=r['housing_amt']))
        db.save_settlements(items)
        nd = sum(1 for x in items if x['settlement_type'] == 'daily_allowance')
        nh = len(items) - nd
        sidebar.flash(f"저장 완료 — 일비 {nd}건 / 숙소비 {nh}건 (집행일 {exec_date})")
        st.rerun()

# ═══════════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("📋 정산 이력")
h1, h2 = st.columns(2)
hist_site_id, _, hist_sites = sidebar.select_site(user, key="hist_site_sel", label="현장 필터", allow_all=True,
                                                  container=h1)
hist = db.get_settlements(site_id=hist_site_id, site_ids=[s['id'] for s in hist_sites])

if not hist:
    st.info("저장된 이력이 없습니다.")
else:
    TYPE_KO = {'daily_allowance': '일비', 'housing': '숙소비'}
    by_date = defaultdict(list)
    for r in hist:
        by_date[r['execution_date']].append(r)
    summary = pd.DataFrame([{
        '집행일': d,
        '일비': sum(r['amount'] for r in recs if r['settlement_type'] == 'daily_allowance'),
        '숙소비': sum(r['amount'] for r in recs if r['settlement_type'] == 'housing'),
        '합계': sum(r['amount'] for r in recs), '건수': len(recs),
    } for d, recs in sorted(by_date.items(), reverse=True)])
    st.dataframe(summary, width="stretch", hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="localized") for c in ('일비', '숙소비', '합계')})
    st.markdown(f"**전체 합계 {int(summary['합계'].sum()):,}원** ({len(hist)}건)")

    sel_d = h2.selectbox("상세 볼 집행일", list(summary['집행일']))
    recs = by_date[sel_d]
    detail = pd.DataFrame([{
        '_id': r['id'], '선택': False, '현장': r['site_name'], '본부': r.get('employee_division') or '',
        '팀': r.get('employee_team') or '', '이름': r['employee_name'],
        '정산유형': TYPE_KO.get(r['settlement_type'], r['settlement_type']),
        '판정기간': f"{r['period_start']} ~ {r['period_end']}", '출근일수': r['work_days'], '지급액': r['amount'],
    } for r in recs])
    st.markdown(f"##### {sel_d} 상세 ({len(recs)}건)")
    edited = st.data_editor(
        detail, hide_index=True, width="stretch", key=f"hist_editor_{sel_d}_{hist_site_id}",
        disabled=[c for c in detail.columns if c != '선택'],
        column_config={'_id': None, '선택': st.column_config.CheckboxColumn('선택', width='small'),
                       '지급액': st.column_config.NumberColumn(format="localized")},
    )
    ids = edited.loc[edited['선택'] == True, '_id'].tolist()  # noqa: E712
    if ids:
        st.warning(f"{len(ids)}건을 삭제합니다. 이미 지급된 건이라면 삭제하지 마세요.")
        if st.button(f"🗑️ 선택 항목 삭제 ({len(ids)}건)", type="primary"):
            n = db.delete_settlements(ids, allowed_site_ids=allowed_ids)
            sidebar.flash(f"{n}건 삭제 완료")
            st.rerun()
    st.download_button("📥 이 집행일 이력 엑셀", data=sidebar.excel_bytes({str(sel_d): detail.drop(columns=['_id', '선택'])}),
                       file_name=f"정산이력_{sel_d}.xlsx", mime=sidebar.XLSX_MIME)
