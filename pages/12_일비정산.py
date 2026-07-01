import streamlit as st
import pandas as pd
import io
import calendar
from datetime import date
import db
import calc
import sidebar

st.set_page_config(page_title="일비 정산", page_icon="💴", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("💴 일비 정산")
st.caption("1차: 1~15일 / 2차: 16~말일 | 기준: 가능일수 70% 이상 + 11일 이상 → 지급 | 미달시 이월(1회)")

all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_map = {s['name']: s['id'] for s in site_options}

col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
with col1:
    selected_site_name = st.selectbox("현장 선택", list(site_map.keys()))
with col2:
    today = date.today()
    year = st.selectbox("연도", list(range(2024, 2031)), index=list(range(2024, 2031)).index(today.year))
with col3:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)
with col4:
    term = st.selectbox("차수", [1, 2])

site_id = site_map[selected_site_name]

_RK = '_daily_result'
_CK = '_daily_ctx'
_ctx = (site_id, year, month, term)

if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if st.button("📊 계산", type="primary"):
    employees = db.get_employees(site_id)
    if not employees:
        st.info("등록된 재직 직원이 없습니다.")
        st.stop()

    results = []
    for emp in employees:
        r = calc.calc_daily_allowance(emp['id'], year, month, term, site_id=site_id)
        results.append({
            '본부': emp.get('division') or '',
            '팀': emp['team'] or '',
            '이름': emp['name'],
            '출근일수': r['work_days'],
            '가능일수': r['possible_days'],
            '기준일수': r['threshold'],
            '충족': '○' if r['work_days'] >= r['threshold'] else '×',
            '이월여부': '이월↗' if r['status'] == '이월' else ('(이월↙)' if r['carry_over'] else ''),
            '상태': r['status'],
            '지급일수': r['pay_days'],
            '지급액(원)': r['amount'],
        })

    st.session_state[_RK] = {'employees': employees, 'results': results}
    st.session_state[_CK] = _ctx

if _RK in st.session_state:
    cached = st.session_state[_RK]
    employees = cached['employees']
    results = cached['results']
    df = pd.DataFrame(results)

    STATUS_COLORS = {
        '지급': '#d4edda', '이월': '#fff3cd', '소멸': '#f8d7da', '미충족': '#f2f2f2',
    }

    def row_style(row):
        color = STATUS_COLORS.get(row['상태'], '')
        return [f'background-color: {color}'] * len(row)

    styled = df.style.apply(row_style, axis=1).format({'지급액(원)': '{:,}'})
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.markdown("🟢 지급 &nbsp; 🟡 이월(다음차수로 이월) &nbsp; 🔴 소멸(2회 연속 이월 불가) &nbsp; ⬜ 미충족", unsafe_allow_html=True)

    total = df['지급액(원)'].sum()
    st.metric("총 지급액", f"{int(total):,}원", delta=f"대상 {(df['상태']=='지급').sum()}명")

    st.markdown("---")
    col_dl, col_save = st.columns(2)

    with col_dl:
        excel_df = df[['본부', '팀', '이름', '출근일수', '가능일수', '기준일수', '충족', '이월여부', '지급일수', '지급액(원)']].copy()
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False, sheet_name='일비정산')
        buf.seek(0)
        st.download_button(
            "📥 엑셀 다운로드", data=buf,
            file_name=f"일비정산_{year}년{month}월{term}차.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with col_save:
        if user['role'] in ('admin', 'manager'):
            if st.button("💾 정산 이력 저장", use_container_width=True):
                exec_date = date(year, month, 15 if term == 1 else calendar.monthrange(year, month)[1])
                if term == 1:
                    ps, pe = date(year, month, 1), date(year, month, 15)
                else:
                    ps = date(year, month, 16)
                    pe = date(year, month, calendar.monthrange(year, month)[1])
                pay_map = {r['이름']: r for r in results if r['상태'] == '지급' and r['지급액(원)'] > 0}
                saved = 0
                for emp in employees:
                    match = pay_map.get(emp['name'])
                    if match:
                        db.save_settlement(site_id, emp['id'], 'daily_allowance', exec_date, ps, pe, match['출근일수'], match['지급액(원)'])
                        saved += 1
                st.success(f"{saved}건 저장 완료")

st.markdown("---")
with st.expander("📋 일비 정산 이력 조회"):
    hist_records = db.get_settlements(site_id=site_id, settlement_type='daily_allowance')
    if hist_records:
        hist_df = pd.DataFrame(hist_records)[['execution_date', 'employee_name', 'period_start', 'period_end', 'work_days', 'amount', 'created_at']]
        hist_df.columns = ['집행일', '직원', '판정시작', '판정종료', '출근일수', '지급액(원)', '저장시각']
        st.dataframe(hist_df.style.format({'지급액(원)': '{:,}'}), use_container_width=True, hide_index=True)
        st.caption(f"총 {len(hist_df)}건 | 합계 {hist_df['지급액(원)'].sum():,}원")
    else:
        st.info("저장된 이력이 없습니다.")
