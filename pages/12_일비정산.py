import streamlit as st
import pandas as pd
from datetime import date
import db
import calc
import sidebar

user = sidebar.page_setup("일비 정산", "💴", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()
st.caption("1차: 1~15일(당월 20일 집행) / 2차: 16~말일(익월 5일 집행) | 가능일수 70% 이상 + 11일 이상 → 지급 | "
           "70% 충족·11일 미만 → 다음 차수로 1회 이월")

today = date.today()
years = list(range(min(2024, today.year - 1), today.year + 2))
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
site_id, site, _ = sidebar.select_site(user, container=c1)
year = c2.selectbox("연도", years, index=years.index(today.year))
month = c3.selectbox("월", list(range(1, 13)), index=today.month - 1)
term = c4.selectbox("차수", [1, 2], format_func=lambda t: f"{t}차 ({'1~15일' if t == 1 else '16~말일'})")

daily_rate = db.get_site_rates(site_id)[0]
ps, pe = calc.term_period(year, month, term)
exec_d = calc.daily_execution_date(year, month, term)
st.caption(f"판정기간 {ps} ~ {pe} · 집행일 **{exec_d}** · 일비 단가 {daily_rate:,}원")

_RK, _CK = '_daily_result', '_daily_ctx'
_ctx = (site_id, year, month, term)
if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if st.button("📊 계산", type="primary"):
    employees = db.get_employees_for_period(site_id, ps, pe)
    labels = sidebar.employee_labels(employees)
    att = calc.load_attendance(site_id, *calc.daily_attendance_range(year, month, term))
    results = []
    for emp in employees:
        r = calc.calc_daily_allowance(emp['id'], year, month, term, daily_rate=daily_rate, att=att)
        results.append({**r, 'emp_id': emp['id'], 'label': labels[emp['id']],
                        'division': emp.get('division') or '', 'team': emp.get('team') or '',
                        'retired': emp['status'] != '재직'})
    st.session_state[_RK] = results
    st.session_state[_CK] = _ctx

results = st.session_state.get(_RK)
if results is None:
    st.info("[📊 계산]을 누르면 결과가 나옵니다.")
elif not results:
    st.info("대상 직원이 없습니다.")
else:
    saved = {r['employee_id']: r for r in db.get_settlements(site_id=site_id, settlement_type='daily_allowance',
                                                              execution_date=exec_d)}
    rows = []
    for r in results:
        sv = saved.get(r['emp_id'])
        if sv:
            mark = '저장됨' if sv['amount'] == r['amount'] else f"저장값 {sv['amount']:,} ≠"
        else:
            mark = '미저장' if r['status'] == '지급' else ''
        rows.append({
            '본부': r['division'], '팀': r['team'], '이름': r['label'] + (' (퇴직)' if r['retired'] else ''),
            '출근일수': r['work_days'], '가능일수': r['possible_days'], '기준일수': r['threshold'],
            '이월': '이월↗' if r['status'] == '이월' else (f"+{r['carry_in_days']}일 받음" if r['carry_over'] else ''),
            '상태': r['status'], '지급일수': r['pay_days'], '지급액(원)': r['amount'], '이력': mark,
        })
    df = pd.DataFrame(rows)
    COLORS = {'지급': '#d4edda', '이월': '#fff3cd', '소멸': '#f8d7da', '미충족': '#f2f2f2'}
    st.dataframe(df.style.apply(lambda row: [f"background-color: {COLORS.get(row['상태'], '')}"] * len(row), axis=1)
                 .format({'지급액(원)': '{:,}'}), width="stretch", hide_index=True)
    st.markdown("🟢 지급 &nbsp; 🟡 이월(다음 차수로) &nbsp; 🔴 소멸(2회 연속 이월 불가) &nbsp; ⬜ 미충족")

    pay = [r for r in results if r['status'] == '지급' and r['amount'] > 0]
    m1, m2, m3 = st.columns(3)
    m1.metric("총 지급액", f"{sum(r['amount'] for r in pay):,}원")
    m2.metric("지급 대상", f"{len(pay)}명")
    m3.metric("이월 / 소멸", f"{sum(r['status'] == '이월' for r in results)} / {sum(r['status'] == '소멸' for r in results)}명")

    stale = [s for eid, s in saved.items() if not any(r['emp_id'] == eid and r['status'] == '지급' for r in results)]
    if stale:
        st.warning(f"이미 저장된 이력 중 {len(stale)}건은 재계산 결과 '지급'이 아닙니다 "
                   f"({', '.join(s['employee_name'] for s in stale)}). 필요하면 정산 대장에서 삭제하세요.")

    st.markdown("---")
    col_dl, col_save = st.columns(2)
    col_dl.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'일비정산': df}),
                           file_name=f"일비정산_{site['name']}_{year}년{month}월{term}차.xlsx",
                           mime=sidebar.XLSX_MIME, width="stretch")
    if col_save.button(f"💾 정산 이력 저장 ({len(pay)}건, 집행일 {exec_d})", width="stretch", disabled=not pay):
        db.save_settlements([dict(site_id=site_id, employee_id=r['emp_id'], settlement_type='daily_allowance',
                                  execution_date=r['execution_date'], period_start=r['period_start'],
                                  period_end=r['period_end'], work_days=r['work_days'], amount=r['amount'])
                             for r in pay])
        sidebar.flash(f"{len(pay)}건 저장 완료 (집행일 {exec_d})")
        st.rerun()

st.markdown("---")
with st.expander("📋 일비 정산 이력 조회"):
    hist = db.get_settlements(site_id=site_id, settlement_type='daily_allowance')
    if hist:
        hdf = pd.DataFrame(hist)[['execution_date', 'employee_name', 'employee_team', 'period_start', 'period_end',
                                  'work_days', 'amount', 'created_at']]
        hdf.columns = ['집행일', '직원', '팀', '판정시작', '판정종료', '출근일수', '지급액(원)', '저장시각']
        st.dataframe(hdf, width="stretch", hide_index=True,
                     column_config={'지급액(원)': st.column_config.NumberColumn(format="localized")})
        st.caption(f"총 {len(hdf)}건 | 합계 {int(hdf['지급액(원)'].sum()):,}원")
    else:
        st.info("저장된 이력이 없습니다.")
