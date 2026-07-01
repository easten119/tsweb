import streamlit as st
import pandas as pd
import io
from datetime import date
from collections import defaultdict
import db
import calc
import sidebar

st.set_page_config(page_title="정산 대장", page_icon="📋", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] == 'viewer':
    st.error("접근 권한이 없습니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("📋 정산 대장")
st.caption("집행일 기준으로 일비 + 숙소비를 통합 산출합니다.")


def _daily_term(exec_date: date):
    if exec_date.day <= 5:
        if exec_date.month == 1:
            return exec_date.year - 1, 12, 2
        return exec_date.year, exec_date.month - 1, 2
    else:
        return exec_date.year, exec_date.month, 1


def _build_display(rows, show_site):
    group_key = (lambda r: (r['현장'], r['본부'])) if show_site else (lambda r: r['본부'])
    groups = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)

    display_rows = []
    for key in sorted(groups.keys(), key=lambda x: x if isinstance(x, str) else (x[0], x[1])):
        grp = groups[key]
        for r in grp:
            display_rows.append(r.copy())
        div_label = key if isinstance(key, str) else f"{key[0]} / {key[1]}"
        display_rows.append({
            '현장': '', '본부': f'▶ {div_label} 소계', '팀': '', '이름': '',
            '일비(출근일수)': sum(r['일비(출근일수)'] for r in grp),
            '일비금액': sum(r['일비금액'] for r in grp),
            '숙소비여부': '', '지역구분': '',
            '숙소비금액': sum(r['숙소비금액'] for r in grp),
            '합계금액': sum(r['합계금액'] for r in grp),
        })

    display_rows.append({
        '현장': '', '본부': '▶▶ 전체 총계', '팀': '', '이름': '',
        '일비(출근일수)': sum(r['일비(출근일수)'] for r in rows),
        '일비금액': sum(r['일비금액'] for r in rows),
        '숙소비여부': '', '지역구분': '',
        '숙소비금액': sum(r['숙소비금액'] for r in rows),
        '합계금액': sum(r['합계금액'] for r in rows),
    })
    return pd.DataFrame(display_rows)


def _row_style(row):
    label = str(row.get('본부', ''))
    if '총계' in label:
        return ['font-weight: bold; background-color: #c8d8e8'] * len(row)
    if '소계' in label:
        return ['font-weight: bold; background-color: #e8e8e8'] * len(row)
    return [''] * len(row)


all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_name_list = ['전체'] + [s['name'] for s in site_options]
site_map = {s['name']: s['id'] for s in site_options}

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    selected_site = st.selectbox("현장 선택", site_name_list)
with col2:
    exec_date = st.date_input("집행일", value=date.today(), format="YYYY/MM/DD")
with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    calc_btn = st.button("🔍 조회", type="primary", use_container_width=True)

_RK = '_settle_result'
_CK = '_settle_ctx'
_ctx = (selected_site, str(exec_date))

if st.session_state.get(_CK) != _ctx:
    st.session_state.pop(_RK, None)

if calc_btn:
    d_year, d_month, d_term = _daily_term(exec_date)
    target_sites = site_options if selected_site == '전체' else [s for s in site_options if s['name'] == selected_site]

    rows = []
    save_items = []

    for site in target_sites:
        sid = site['id']
        employees = db.get_employees(sid)
        for emp in employees:
            eid = emp['id']
            dr = calc.calc_daily_allowance(eid, d_year, d_month, d_term, site_id=sid)
            if dr['status'] == '지급':
                daily_days, daily_amt = dr['pay_days'], dr['amount']
                daily_exec, daily_ps, daily_pe = dr['execution_date'], dr['period_start'], dr['period_end']
            else:
                daily_days, daily_amt = 0, 0
                daily_exec = daily_ps = daily_pe = None

            hr = calc.calc_housing(eid, exec_date, site_id=sid)
            if hr['is_target'] and hr['is_qualified']:
                housing_yn, housing_amt = '○', hr['amount']
            else:
                housing_yn, housing_amt = '-', 0

            total_amt = daily_amt + housing_amt
            if total_amt == 0:
                continue

            rows.append({
                '현장': site['name'], '본부': emp.get('division') or '', '팀': emp.get('team') or '',
                '이름': emp['name'], '일비(출근일수)': daily_days, '일비금액': daily_amt,
                '숙소비여부': housing_yn, '지역구분': emp.get('housing_region', '-') if housing_yn == '○' else '-',
                '숙소비금액': housing_amt, '합계금액': total_amt,
            })
            save_items.append({
                'site_id': sid, 'emp_id': eid, 'emp_name': emp['name'],
                'daily_status': dr['status'], 'daily_exec': daily_exec,
                'daily_ps': daily_ps, 'daily_pe': daily_pe, 'daily_days': dr['work_days'], 'daily_amt': daily_amt,
                'housing_target': hr['is_target'] and hr['is_qualified'],
                'housing_ps': hr['period_start'], 'housing_pe': hr['period_end'],
                'housing_days': hr['work_days'], 'housing_amt': housing_amt,
            })

    st.session_state[_RK] = {'rows': rows, 'save_items': save_items, 'exec_date': exec_date,
                              'site': selected_site, 'd_year': d_year, 'd_month': d_month, 'd_term': d_term}
    st.session_state[_CK] = _ctx

if _RK not in st.session_state:
    st.info("현장과 집행일을 선택한 뒤 [🔍 조회] 버튼을 누르세요.")
else:
    cached = st.session_state[_RK]
    rows = cached['rows']
    exec_date_c = cached['exec_date']
    site_c = cached['site']
    d_year, d_month, d_term = cached['d_year'], cached['d_month'], cached['d_term']
    save_items = cached['save_items']

    if not rows:
        st.info("집행 대상 직원이 없습니다.")
    else:
        st.caption(f"일비 기준: {d_year}년 {d_month}월 {d_term}차 | 숙소비 기준: {exec_date_c} 집행일 대상자")

        show_site = (site_c == '전체')
        tdf = _build_display(rows, show_site)
        display_cols = (['현장'] if show_site else []) + ['본부', '팀', '이름', '일비(출근일수)', '일비금액', '숙소비여부', '지역구분', '숙소비금액', '합계금액']
        tdf = tdf[display_cols]
        FMT_COLS = {'일비금액': '{:,}', '숙소비금액': '{:,}', '합계금액': '{:,}'}

        st.dataframe(tdf.style.apply(_row_style, axis=1).format(FMT_COLS), use_container_width=True, hide_index=True)

        st.markdown("---")
        total_pax = len(rows)
        total_daily = sum(r['일비금액'] for r in rows)
        total_house = sum(r['숙소비금액'] for r in rows)
        total_all = total_daily + total_house
        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("총 집행 인원", f"{total_pax}명")
        cm2.metric("일비 총액", f"{total_daily:,}원")
        cm3.metric("숙소비 총액", f"{total_house:,}원")
        cm4.metric("합계 총액", f"{total_all:,}원")

        st.markdown("---")
        col_dl, col_save = st.columns(2)
        with col_dl:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                tdf.to_excel(writer, index=False, sheet_name='정산대장')
            buf.seek(0)
            st.download_button("📥 엑셀 다운로드", data=buf, file_name=f"{exec_date_c}_{site_c}_정산대장.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

        with col_save:
            if user['role'] in ('admin', 'manager'):
                if st.button("💾 정산이력 일괄저장 (일비 + 숙소비)", use_container_width=True):
                    saved_daily = saved_house = 0
                    for item in save_items:
                        if item['daily_status'] == '지급' and item['daily_amt'] > 0:
                            db.save_settlement(item['site_id'], item['emp_id'], 'daily_allowance', item['daily_exec'], item['daily_ps'], item['daily_pe'], item['daily_days'], item['daily_amt'])
                            saved_daily += 1
                        if item['housing_target'] and item['housing_amt'] > 0:
                            db.save_settlement(item['site_id'], item['emp_id'], 'housing', exec_date_c, item['housing_ps'], item['housing_pe'], item['housing_days'], item['housing_amt'])
                            saved_house += 1
                    st.success(f"저장 완료 — 일비 {saved_daily}건 / 숙소비 {saved_house}건")

st.markdown("---")
st.subheader("📋 정산 이력")
_TYPE_KO = {'daily_allowance': '일비', 'housing': '숙소비'}
can_delete = user['role'] in ('admin', 'manager')

hist_site = st.selectbox("현장 필터", ['전체'] + [s['name'] for s in site_options], key="hist_site_sel")
hist_site_id = site_map.get(hist_site) if hist_site != '전체' else None
hist_records = db.get_settlements(site_id=hist_site_id, limit=2000)

if not hist_records:
    st.info("저장된 이력이 없습니다.")
else:
    by_date = defaultdict(list)
    for r in hist_records:
        by_date[r['execution_date']].append(r)

    for exec_d in sorted(by_date.keys(), reverse=True):
        recs = by_date[exec_d]
        d_sum = sum(r['amount'] for r in recs if r['settlement_type'] == 'daily_allowance')
        h_sum = sum(r['amount'] for r in recs if r['settlement_type'] == 'housing')
        t_sum = d_sum + h_sum
        label = f"{exec_d}  │  일비 {d_sum:,}원  │  숙소비 {h_sum:,}원  │  합계 {t_sum:,}원  │  {len(recs)}건"

        with st.expander(label):
            detail_rows = [{
                '_id': r['id'], '선택': False, '현장': r['site_name'],
                '본부': r.get('employee_division') or '', '팀': r.get('employee_team') or '',
                '이름': r['employee_name'], '정산유형': _TYPE_KO.get(r['settlement_type'], r['settlement_type']),
                '출근일수': r['work_days'], '지급액': r['amount'],
            } for r in recs]

            detail_df = pd.DataFrame(detail_rows)

            if can_delete:
                edited = st.data_editor(
                    detail_df,
                    column_config={
                        '_id': None,
                        '선택': st.column_config.CheckboxColumn('선택', default=False, width='small'),
                        '현장': st.column_config.TextColumn('현장', disabled=True),
                        '본부': st.column_config.TextColumn('본부', disabled=True),
                        '팀': st.column_config.TextColumn('팀', disabled=True),
                        '이름': st.column_config.TextColumn('이름', disabled=True),
                        '정산유형': st.column_config.TextColumn('정산유형', disabled=True),
                        '출근일수': st.column_config.NumberColumn('출근일수', disabled=True),
                        '지급액': st.column_config.NumberColumn('지급액', disabled=True, format='%d'),
                    },
                    hide_index=True, use_container_width=True, key=f"editor_{exec_d}",
                )
                selected_ids = edited.loc[edited['선택'] == True, '_id'].tolist()
                n_sel = len(selected_ids)
                if n_sel > 0:
                    st.warning(f"{n_sel}건을 삭제합니다.")
                    if st.button(f"🗑️ 선택 항목 삭제 ({n_sel}건)", key=f"del_btn_{exec_d}", type="primary"):
                        db.delete_settlements(selected_ids)
                        st.success(f"{n_sel}건 삭제 완료")
                        st.rerun()
            else:
                st.dataframe(detail_df.drop(columns=['_id', '선택']).style.format({'지급액': '{:,}'}), use_container_width=True, hide_index=True)

    grand = sum(r['amount'] for r in hist_records)
    st.markdown(f"**전체 합계 총액: {grand:,}원**  ({len(hist_records)}건)")
