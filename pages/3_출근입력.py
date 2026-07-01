import streamlit as st
import pandas as pd
import calendar
from datetime import date
import db
import sidebar

st.set_page_config(page_title="출근 입력", page_icon="📅", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📅 출근 입력")

# ── 현장 / 연월 선택 ───────────────────────────────────────────────
all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_map = {s['name']: s['id'] for s in site_options}

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    selected_site_name = st.selectbox("현장 선택", list(site_map.keys()))
with col2:
    today = date.today()
    year = st.selectbox("연도", list(range(2024, 2031)), index=list(range(2024, 2031)).index(today.year))
with col3:
    month = st.selectbox("월", list(range(1, 13)), index=today.month - 1)

site_id = site_map[selected_site_name]
employees = db.get_employees(site_id)

if not employees:
    st.info("등록된 재직 직원이 없습니다.")
    st.stop()

# ── 날짜 헤더 생성 ─────────────────────────────────────────────────
last_day = calendar.monthrange(year, month)[1]
days = list(range(1, last_day + 1))

WEEKDAY_NAMES = {5: '토', 6: '일'}

def day_label(d):
    wd = date(year, month, d).weekday()
    suffix = WEEKDAY_NAMES.get(wd, '')
    return f"{d}({suffix})" if suffix else str(d)

col_labels = {d: day_label(d) for d in days}

# ── 출근 데이터 로드 ───────────────────────────────────────────────
_editor_key = f"att_{site_id}_{year}_{month}"
_ctx_track_key = "_att_last_ctx"

# 현장/연월이 바뀌면 이전 data_editor 상태를 지워 DB 데이터가 반영되도록 함
if st.session_state.get(_ctx_track_key) != _editor_key:
    for k in [k for k in list(st.session_state.keys())
              if k.startswith("att_") and k != _ctx_track_key]:
        del st.session_state[k]
    st.session_state[_ctx_track_key] = _editor_key

data = {}
for emp in employees:
    work_dates = db.get_attendance_dates(emp['id'], year, month)
    # 본부/팀을 앞 열로, 날짜키는 str로 통일 (JSON 직렬화 대응)
    row = {
        '본부': emp.get('division') or '',
        '팀': emp.get('team') or '',
    }
    row.update({str(d): (f"{year}-{month:02d}-{d:02d}" in work_dates) for d in days})
    data[emp['name']] = row

df = pd.DataFrame(data).T
df.index.name = '직원명'
df = df[['본부', '팀'] + [str(d) for d in days]]  # 열 순서 고정

# ── 표시 및 편집 ───────────────────────────────────────────────────
column_config = {
    '본부': st.column_config.TextColumn('본부', disabled=True, width='small'),
    '팀': st.column_config.TextColumn('팀', disabled=True, width='small'),
    **{
        str(d): st.column_config.CheckboxColumn(label=col_labels[d], default=False)
        for d in days
    },
}

is_readonly = (user['role'] == 'viewer')

if is_readonly:
    st.info("뷰어 권한으로는 편집할 수 없습니다.")
    st.dataframe(df, use_container_width=True, column_config=column_config)
else:
    st.caption("체크박스를 클릭해 출근 여부를 입력한 뒤 저장 버튼을 누르세요. (토·일 열: 주말)")
    edited = st.data_editor(
        df,
        column_config=column_config,
        use_container_width=True,
        key=_editor_key,
    )

    col_save, col_info = st.columns([1, 4])
    with col_save:
        if st.button("💾 저장", type="primary", use_container_width=True):
            for emp in employees:
                emp_name = emp['name']
                if emp_name not in edited.index:
                    continue
                row = edited.loc[emp_name]
                work_set = set()
                for d in days:
                    if row[str(d)]:
                        work_set.add(f"{year}-{month:02d}-{d:02d}")
                db.save_attendance_month(emp['id'], year, month, work_set)
            # 저장 후 editor 상태를 초기화해 DB 데이터가 다시 로드되도록 함
            if _editor_key in st.session_state:
                del st.session_state[_editor_key]
            st.success(f"{year}년 {month}월 출근 기록이 저장되었습니다.")
            st.rerun()

    # ── 월 출근 요약 ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 출근 요약")
    summary = []
    for emp in employees:
        work_dates = db.get_attendance_dates(emp['id'], year, month)
        total = len(work_dates)
        term1 = sum(1 for d in work_dates if int(d.split('-')[2]) <= 15)
        term2 = total - term1
        summary.append({
            '본부': emp.get('division') or '',
            '팀': emp['team'] or '',
            '이름': emp['name'],
            '1차 출근(1~15일)': term1,
            '2차 출근(16~말일)': term2,
            '월 합계': total,
        })
    if summary:
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
