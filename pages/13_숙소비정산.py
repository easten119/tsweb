import streamlit as st
import pandas as pd
import io
from datetime import date
import db
import calc
import sidebar

st.set_page_config(page_title="숙소비 정산", page_icon="🏠", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("🏠 숙소비 정산")
st.caption("해당지역 200,000원 / 타지역 300,000원 | 30일 판정기간 중 25일 이상 출근 시 지급")

all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_map = {s['name']: s['id'] for s in site_options}

col1, col2 = st.columns([2, 2])
with col1:
    selected_site_name = st.selectbox("현장 선택", list(site_map.keys()))
with col2:
    exec_date = st.date_input("집행일 (매월 5일 또는 20일)", value=date.today().replace(day=5), format="YYYY/MM/DD")

site_id = site_map[selected_site_name]

_RK = '_housing_result'
_CK = '_housing_ctx'
_ctx = (site_id, str(exec_date))

if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if st.button("📊 계산", type="primary"):
    if exec_date.day not in (5, 20):
        st.error("집행일은 매월 5일 또는 20일만 선택 가능합니다.")
        st.stop()

    employees = db.get_employees(site_id)
    if not employees:
        st.info("등록된 재직 직원이 없습니다.")
        st.stop()

    results = []
    for emp in employees:
        r = calc.calc_housing(emp['id'], exec_date, site_id=site_id)
        results.append({
            '본부': emp.get('division') or '',
            '팀': emp['team'] or '',
            '이름': emp['name'],
            '지역구분': emp['housing_region'],
            '첫출근일': emp.get('first_work_date', '-') or '-',
            '판정시작': str(r['period_start']) if r['period_start'] else '-',
            '판정종료': str(r['period_end']) if r['period_end'] else '-',
            '출근일수': r['work_days'],
            '충족(25일↑)': '○' if r['is_qualified'] else '×',
            '집행대상': '★' if r['is_target'] else '',
            '지급액(원)': r['amount'],
            '_period_start': r['period_start'],
            '_period_end': r['period_end'],
            '_is_target': r['is_target'],
            '_is_qualified': r['is_qualified'],
            '_work_days': r['work_days'],
            '_amount': r['amount'],
        })

    st.session_state[_RK] = {'employees': employees, 'results': results}
    st.session_state[_CK] = _ctx

if _RK in st.session_state:
    cached = st.session_state[_RK]
    employees = cached['employees']
    results = cached['results']

    display_cols = ['본부', '팀', '이름', '지역구분', '첫출근일', '판정시작', '판정종료', '출근일수', '충족(25일↑)', '집행대상', '지급액(원)']
    df = pd.DataFrame(results)[display_cols]

    def row_style(row):
        if row['집행대상'] == '★' and row['충족(25일↑)'] == '○':
            return ['background-color: #d4edda'] * len(row)
        elif row['집행대상'] == '★':
            return ['background-color: #fff3cd'] * len(row)
        return [''] * len(row)

    styled = df.style.apply(row_style, axis=1).format({'지급액(원)': '{:,}'})
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.markdown("🟢 집행대상 + 충족 &nbsp; 🟡 집행대상이나 미충족 &nbsp; ⬜ 이번 집행일 비대상", unsafe_allow_html=True)

    target_df = df[df['집행대상'] == '★']
    total = target_df['지급액(원)'].sum()
    st.metric("총 지급액", f"{int(total):,}원", delta=f"지급 대상 {(target_df['충족(25일↑)']=='○').sum()}명")

    st.markdown("---")
    col_dl, col_save = st.columns(2)

    with col_dl:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='숙소비정산')
        buf.seek(0)
        st.download_button(
            "📥 엑셀 다운로드", data=buf, file_name=f"숙소비정산_{exec_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_save:
        if user['role'] in ('admin', 'manager'):
            if st.button("💾 정산 이력 저장", use_container_width=True):
                saved = 0
                for r in results:
                    if r['_is_target'] and r['_is_qualified']:
                        emp = next((e for e in employees if e['name'] == r['이름']), None)
                        if emp:
                            db.save_settlement(site_id, emp['id'], 'housing', exec_date, r['_period_start'], r['_period_end'], r['_work_days'], r['_amount'])
                            saved += 1
                st.success(f"{saved}건 저장 완료")

    with st.expander("직원별 숙소비 집행 스케줄 보기"):
        for emp in employees:
            schedule = calc.get_housing_schedule(emp['id'], periods=6)
            if schedule:
                sdf = pd.DataFrame(schedule)
                sdf.columns = ['판정시작', '판정종료', '집행예정일']
                st.markdown(f"**{emp['name']} ({emp['housing_region']})**")
                st.dataframe(sdf, use_container_width=True, hide_index=True, height=220)

st.markdown("---")
with st.expander("📋 숙소비 정산 이력 조회"):
    hist_records = db.get_settlements(site_id=site_id, settlement_type='housing')
    if hist_records:
        hist_df = pd.DataFrame(hist_records)[['execution_date', 'employee_name', 'period_start', 'period_end', 'work_days', 'amount', 'created_at']]
        hist_df.columns = ['집행일', '직원', '판정시작', '판정종료', '출근일수', '지급액(원)', '저장시각']
        st.dataframe(hist_df.style.format({'지급액(원)': '{:,}'}), use_container_width=True, hide_index=True)
        st.caption(f"총 {len(hist_df)}건 | 합계 {hist_df['지급액(원)'].sum():,}원")
    else:
        st.info("저장된 이력이 없습니다.")
