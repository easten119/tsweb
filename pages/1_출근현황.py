import streamlit as st
import pandas as pd
from datetime import date, timedelta
from collections import defaultdict
import db
import sidebar

st.set_page_config(page_title="출근 현황", page_icon="📊", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📊 출근 현황")

# ── 현장 선택 ─────────────────────────────────────────────────────
all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_map = {s['name']: s['id'] for s in site_options}
selected_site_name = st.selectbox("현장 선택", list(site_map.keys()))
site_id = site_map[selected_site_name]

today = date.today()
employees = db.get_employees(site_id)

# ── 금일 총 출근인원 ──────────────────────────────────────────────
st.markdown("---")
today_str = str(today)
present_ids = set()

for emp in employees:
    work_dates = db.get_attendance_dates(emp['id'], today.year, today.month)
    if today_str in work_dates:
        present_ids.add(emp['id'])

total_present = len(present_ids)
total_registered = len(employees)
attend_rate = total_present / total_registered * 100 if total_registered > 0 else 0

col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric(
    f"금일 출근  ({today.strftime('%Y-%m-%d')})",
    f"{total_present}명",
    delta=f"전체 등록 {total_registered}명",
)
col_m2.metric("출근율", f"{attend_rate:.1f}%")
col_m3.metric("미출근", f"{total_registered - total_present}명")

# ── 본부/팀별 출근 현황 ───────────────────────────────────────────
st.markdown("---")
st.markdown("#### 본부/팀별 출근 현황")
selected_date = st.date_input("📅 조회 날짜", value=today)

if selected_date == today:
    selected_present_ids = present_ids
else:
    sel_str = str(selected_date)
    selected_present_ids = set()
    for emp in employees:
        wd = db.get_attendance_dates(emp['id'], selected_date.year, selected_date.month)
        if sel_str in wd:
            selected_present_ids.add(emp['id'])

team_stats: dict = defaultdict(lambda: {'present': 0, 'total': 0})
for emp in employees:
    div = emp.get('division') or '(미분류)'
    team = emp.get('team') or '(미분류)'
    key = (div, team)
    team_stats[key]['total'] += 1
    if emp['id'] in selected_present_ids:
        team_stats[key]['present'] += 1

divisions = sorted({k[0] for k in team_stats})
rows = []

for div in divisions:
    div_keys = sorted([k for k in team_stats if k[0] == div], key=lambda x: x[1])
    for key in div_keys:
        s = team_stats[key]
        r = s['present'] / s['total'] * 100 if s['total'] > 0 else 0.0
        rows.append({
            '본부': key[0], '팀': key[1],
            '출근인원': s['present'], '등록인원': s['total'],
            '출근율(%)': round(r, 1),
        })
    dp = sum(team_stats[k]['present'] for k in div_keys)
    dt = sum(team_stats[k]['total'] for k in div_keys)
    dr = dp / dt * 100 if dt > 0 else 0.0
    rows.append({
        '본부': f'▶ {div} 소계', '팀': '',
        '출근인원': dp, '등록인원': dt,
        '출근율(%)': round(dr, 1),
    })

total_p = sum(v['present'] for v in team_stats.values())
total_t = sum(v['total'] for v in team_stats.values())
total_r = total_p / total_t * 100 if total_t > 0 else 0.0
rows.append({
    '본부': '▶▶ 전체 총계', '팀': '',
    '출근인원': total_p, '등록인원': total_t,
    '출근율(%)': round(total_r, 1),
})

if rows:
    tdf = pd.DataFrame(rows)

    def _style_row(row):
        is_total = '총계' in str(row['본부'])
        is_sub = '소계' in str(row['본부'])
        if is_total:
            return ['font-weight: bold; background-color: #c8d8e8'] * len(row)
        if is_sub:
            return ['font-weight: bold; background-color: #e8e8e8'] * len(row)
        styles = [''] * len(row)
        if row['출근율(%)'] < 70:
            styles[4] = 'color: #c0392b; font-weight: bold'
        return styles

    st.dataframe(
        tdf.style.apply(_style_row, axis=1).format({'출근율(%)': '{:.1f}%'}),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("⚠️ 출근율 70% 미만: 빨간색 강조")

# ── 최근 30일 출근 추이 ───────────────────────────────────────────
st.markdown("---")
st.markdown("#### 최근 30일 출근 추이")

start_date = today - timedelta(days=29)
daily_counts = db.get_daily_attendance_counts(site_id, start_date, today)

date_range = [start_date + timedelta(days=i) for i in range(30)]
chart_rows = []
for d in date_range:
    chart_rows.append({
        '날짜': str(d),
        '출근인원': daily_counts.get(str(d), 0),
        '주말': d.weekday() >= 5,
    })
chart_df = pd.DataFrame(chart_rows)

try:
    import plotly.graph_objects as go

    fig = go.Figure()
    chart_df['날짜_dt'] = pd.to_datetime(chart_df['날짜'])
    weekday_mask = ~chart_df['주말']
    weekend_mask = chart_df['주말']

    fig.add_trace(go.Scatter(
        x=chart_df['날짜_dt'], y=chart_df['출근인원'],
        mode='lines', line=dict(color='steelblue', width=2),
        showlegend=False, hoverinfo='skip',
    ))
    fig.add_trace(go.Scatter(
        x=chart_df[weekday_mask]['날짜_dt'], y=chart_df[weekday_mask]['출근인원'],
        mode='markers', marker=dict(color='steelblue', size=7), name='평일',
        hovertemplate='%{x|%y/%m/%d}<br>출근: %{y}명<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=chart_df[weekend_mask]['날짜_dt'], y=chart_df[weekend_mask]['출근인원'],
        mode='markers', marker=dict(color='tomato', size=7, symbol='diamond'), name='주말',
        hovertemplate='%{x|%y/%m/%d}<br>출근: %{y}명<extra></extra>',
    ))

    i = 0
    while i < len(chart_df):
        if chart_df.iloc[i]['주말']:
            j = i
            while j < len(chart_df) and chart_df.iloc[j]['주말']:
                j += 1
            fig.add_vrect(
                x0=chart_df.iloc[i]['날짜'],
                x1=chart_df.iloc[min(j, len(chart_df) - 1)]['날짜'],
                fillcolor='lightsalmon', opacity=0.15, line_width=0,
            )
            i = j
        else:
            i += 1

    fig.update_layout(
        xaxis_title='날짜', yaxis_title='출근인원', height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    fig.update_xaxes(tickformat='%y/%m/%d', tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

except ImportError:
    st.line_chart(chart_df.set_index('날짜')['출근인원'])
    st.caption("주말 색상 구분을 보려면: pip install plotly")
