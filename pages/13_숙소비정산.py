import streamlit as st
import pandas as pd
from datetime import timedelta
import db
import calc
import sidebar

user = sidebar.page_setup("숙소비 정산", "🏠", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

c1, c2 = st.columns([2, 2])
site_id, site, _ = sidebar.select_site(user, container=c1)
exec_options = calc.nearest_execution_dates()
default_exec = calc.default_execution_date()
exec_date = c2.selectbox("집행일 (매월 5일 / 20일)", exec_options, index=exec_options.index(default_exec),
                         format_func=lambda d: d.strftime('%Y-%m-%d (%a)'))

rates = db.get_site_rates(site_id)
st.caption(f"해당지역 {rates[1]:,}원 / 타지역 {rates[2]:,}원 | 첫출근일부터 30일 단위 판정기간 중 25일 이상 출근 시 지급 | "
           "판정종료일 다음 날 이후 가장 가까운 5일·20일에 집행")

_RK, _CK = '_housing_result', '_housing_ctx'
_ctx = (site_id, str(exec_date))
if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if st.button("📊 계산", type="primary"):
    # 판정기간(30일)이 집행일 직전 최대 45일 안에 걸치므로 그 기간 출근자 + 재직자
    look_from = exec_date - timedelta(days=calc.HOUSING_LOOKBACK_DAYS)
    employees = db.get_employees_for_period(site_id, look_from, exec_date)
    att = calc.load_attendance(site_id, look_from, exec_date)
    labels = sidebar.employee_labels(employees)
    results = []
    for emp in employees:
        r = calc.calc_housing(emp['id'], exec_date, emp=emp, rates=rates, att=att)
        results.append({**r, 'emp_id': emp['id'], 'label': labels[emp['id']], 'emp': emp})
    st.session_state[_RK] = results
    st.session_state[_CK] = _ctx

results = st.session_state.get(_RK)
if results is None:
    st.info("[📊 계산]을 누르면 결과가 나옵니다.")
elif not results:
    st.info("대상 직원이 없습니다.")
else:
    saved = {r['employee_id']: r for r in db.get_settlements(site_id=site_id, settlement_type='housing',
                                                              execution_date=exec_date)}
    only_target = st.checkbox("이번 집행일 대상자만 보기", value=True)
    rows = []
    for r in results:
        if only_target and not r['is_target']:
            continue
        emp = r['emp']
        sv = saved.get(r['emp_id'])
        rows.append({
            '본부': emp.get('division') or '', '팀': emp.get('team') or '',
            '이름': r['label'] + (' (퇴직)' if emp['status'] != '재직' else ''),
            '지역구분': emp.get('housing_region'), '첫출근일': emp.get('first_work_date') or '-',
            '판정시작': str(r['period_start'] or '-'), '판정종료': str(r['period_end'] or '-'),
            '출근일수': r['work_days'], '충족(25일↑)': '○' if r['is_qualified'] else '×',
            '집행대상': '★' if r['is_target'] else r.get('reason', ''),
            '지급액(원)': r['amount'],
            '이력': ('저장됨' if sv and sv['amount'] == r['amount'] else
                   (f"저장값 {sv['amount']:,} ≠" if sv else ('미저장' if r['amount'] else ''))),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("이번 집행일 대상자가 없습니다.")
    else:
        def row_style(row):
            if row['집행대상'] == '★':
                return [f"background-color: {'#d4edda' if row['충족(25일↑)'] == '○' else '#fff3cd'}"] * len(row)
            return [''] * len(row)
        st.dataframe(df.style.apply(row_style, axis=1).format({'지급액(원)': '{:,}'}), width="stretch", hide_index=True)
        st.markdown("🟢 집행대상 + 충족 &nbsp; 🟡 집행대상이나 25일 미만")

    pay = [r for r in results if r['is_target'] and r['is_qualified'] and r['amount'] > 0]
    no_fwd = [r for r in results if r.get('reason') == '첫출근일 없음']
    m1, m2, m3 = st.columns(3)
    m1.metric("총 지급액", f"{sum(r['amount'] for r in pay):,}원")
    m2.metric("지급 대상", f"{len(pay)}명")
    m3.metric("집행대상 중 미충족", f"{sum(1 for r in results if r['is_target'] and not r['is_qualified'])}명")
    if no_fwd:
        st.warning("첫출근일이 없어 계산하지 못한 직원: " + ", ".join(r['label'] for r in no_fwd))

    st.markdown("---")
    col_dl, col_save = st.columns(2)
    col_dl.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'숙소비정산': df}),
                           file_name=f"숙소비정산_{site['name']}_{exec_date}.xlsx", mime=sidebar.XLSX_MIME,
                           width="stretch")
    if col_save.button(f"💾 정산 이력 저장 ({len(pay)}건)", width="stretch", disabled=not pay):
        db.save_settlements([dict(site_id=site_id, employee_id=r['emp_id'], settlement_type='housing',
                                  execution_date=exec_date, period_start=r['period_start'],
                                  period_end=r['period_end'], work_days=r['work_days'], amount=r['amount'])
                             for r in pay])
        sidebar.flash(f"{len(pay)}건 저장 완료 (집행일 {exec_date})")
        st.rerun()

    with st.expander("직원별 숙소비 집행 스케줄"):
        sched_rows = []
        for r in results:
            for s in calc.get_housing_schedule(r['emp_id'], periods=4, emp=r['emp'], from_date=exec_date):
                sched_rows.append({'이름': r['label'], '지역구분': r['emp'].get('housing_region'),
                                   '판정시작': s['period_start'], '판정종료': s['period_end'],
                                   '집행예정일': s['execution_date']})
        if sched_rows:
            st.dataframe(pd.DataFrame(sched_rows), width="stretch", hide_index=True)

st.markdown("---")
with st.expander("📋 숙소비 정산 이력 조회"):
    hist = db.get_settlements(site_id=site_id, settlement_type='housing')
    if hist:
        hdf = pd.DataFrame(hist)[['execution_date', 'employee_name', 'employee_team', 'period_start', 'period_end',
                                  'work_days', 'amount', 'created_at']]
        hdf.columns = ['집행일', '직원', '팀', '판정시작', '판정종료', '출근일수', '지급액(원)', '저장시각']
        st.dataframe(hdf, width="stretch", hide_index=True,
                     column_config={'지급액(원)': st.column_config.NumberColumn(format="localized")})
        st.caption(f"총 {len(hdf)}건 | 합계 {int(hdf['지급액(원)'].sum()):,}원")
    else:
        st.info("저장된 이력이 없습니다.")
