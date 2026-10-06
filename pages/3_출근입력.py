import streamlit as st
import pandas as pd
import calendar
from datetime import date
import db
import sidebar

user = sidebar.page_setup("출근 입력", "📅", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

today = date.today()
years = list(range(min(2024, today.year - 1), today.year + 2))

c1, c2, c3 = st.columns([2, 1, 1])
site_id, site, _ = sidebar.select_site(user, container=c1)
year = c2.selectbox("연도", years, index=years.index(today.year))
month = c3.selectbox("월", list(range(1, 13)), index=today.month - 1)

last_day = calendar.monthrange(year, month)[1]
month_start, month_end = date(year, month, 1), date(year, month, last_day)
days = list(range(1, last_day + 1))

# 재직자 + 이 달에 출근 기록이 있는 퇴직자
employees = db.get_employees_for_period(site_id, month_start, month_end)
if not employees:
    st.info("등록된 직원이 없습니다. 직원 관리에서 먼저 등록하세요.")
    st.stop()

labels = sidebar.employee_labels(employees)
attendance = db.get_site_attendance(site_id, month_start, month_end)


def day_label(d):
    wd = date(year, month, d).weekday()
    return f"{d}({'토' if wd == 5 else '일'})" if wd >= 5 else str(d)


rows = []
for emp in employees:
    work = attendance.get(emp['id'], set())
    row = {'_id': emp['id'], '이름': labels[emp['id']] + (' (퇴직)' if emp['status'] != '재직' else ''),
           '본부': emp.get('division') or '', '팀': emp.get('team') or ''}
    row.update({str(d): f"{year}-{month:02d}-{d:02d}" in work for d in days})
    rows.append(row)
df = pd.DataFrame(rows)

column_config = {
    '_id': None,
    '이름': st.column_config.TextColumn('이름', disabled=True, pinned=True),
    '본부': st.column_config.TextColumn('본부', disabled=True, width='small'),
    '팀': st.column_config.TextColumn('팀', disabled=True, width='small'),
    **{str(d): st.column_config.CheckboxColumn(label=day_label(d), default=False) for d in days},
}

# 현장/연월이 바뀌면 이전 편집 상태 폐기
_editor_key = f"att_{site_id}_{year}_{month}"
if st.session_state.get("_att_last_ctx") != _editor_key:
    for k in [k for k in st.session_state if str(k).startswith("att_")]:
        del st.session_state[k]
    st.session_state["_att_last_ctx"] = _editor_key

st.caption("체크박스로 출근 여부를 입력한 뒤 저장하세요. 저장 전까지는 DB에 반영되지 않습니다.")
edited = st.data_editor(df, column_config=column_config, width="stretch", hide_index=True,
                        key=_editor_key, disabled=False, num_rows="fixed")

changed = 0
for (_, before), (_, after) in zip(df.iterrows(), edited.iterrows()):
    changed += sum(1 for d in days if bool(before[str(d)]) != bool(after[str(d)]))

col_save, col_info = st.columns([1, 4])
if changed:
    col_info.warning(f"저장하지 않은 변경 {changed}칸")
if col_save.button("💾 저장", type="primary", width="stretch", disabled=not changed):
    records = []
    for (_, before), (_, after) in zip(df.iterrows(), edited.iterrows()):
        emp_id = int(after['_id'])
        for d in days:
            if bool(before[str(d)]) != bool(after[str(d)]):
                records.append((emp_id, f"{year}-{month:02d}-{d:02d}", 1 if after[str(d)] else 0))
    db.save_attendance_records(records)
    st.session_state.pop(_editor_key, None)
    sidebar.flash(f"{year}년 {month}월 출근 기록 {len(records)}칸이 저장되었습니다.")
    st.rerun()

# ── 월 출근 요약 ───────────────────────────────────────────────────
st.markdown("---")
st.markdown("#### 출근 요약 (저장된 기록 기준)")
summary = []
for emp in employees:
    work = attendance.get(emp['id'], set())
    term1 = sum(1 for d in work if int(d[8:10]) <= 15)
    summary.append({
        '본부': emp.get('division') or '', '팀': emp.get('team') or '', '이름': labels[emp['id']],
        '1차 출근(1~15일)': term1, '2차 출근(16~말일)': len(work) - term1, '월 합계': len(work),
    })
sdf = pd.DataFrame(summary)
st.dataframe(sdf, width="stretch", hide_index=True)
st.download_button(
    "📥 출근부 엑셀 다운로드",
    data=sidebar.excel_bytes({f"{month}월출근현황": edited.drop(columns=['_id']).replace({True: 'O', False: ''}),
                              '요약': sdf}),
    file_name=f"출근부_{site['name']}_{year}{month:02d}.xlsx", mime=sidebar.XLSX_MIME)
