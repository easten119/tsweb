import streamlit as st
import pandas as pd
from datetime import date, timedelta
from collections import defaultdict
import db
import sidebar

user = sidebar.page_setup("출근 현황", "📊", roles=sidebar.EDIT_ROLES)

site_id, site, _ = sidebar.select_site(user)
employees = db.get_employees(site_id)
today = date.today()

# ── 금일 출근 ─────────────────────────────────────────────────────
st.markdown("---")
today_present = db.get_site_attendance(site_id, today, today)
emp_ids = {e['id'] for e in employees}
present_ids = set(today_present) & emp_ids
total_registered = len(employees)
total_present = len(present_ids)
attend_rate = total_present / total_registered * 100 if total_registered else 0

m1, m2, m3 = st.columns(3)
m1.metric(f"금일 출근  ({today:%Y-%m-%d})", f"{total_present}명", delta=f"재직 {total_registered}명",
          delta_color="off")
m2.metric("출근율", f"{attend_rate:.1f}%")
m3.metric("미출근", f"{total_registered - total_present}명")

# ── 본부/팀별 출근 현황 ───────────────────────────────────────────
st.markdown("---")
st.markdown("#### 본부/팀별 출근 현황")
selected_date = st.date_input("📅 조회 날짜", value=today, max_value=today)

if selected_date == today:
    sel_present = present_ids
else:
    sel_present = set(db.get_site_attendance(site_id, selected_date, selected_date)) & emp_ids

team_stats = defaultdict(lambda: {'present': 0, 'total': 0})
for emp in employees:
    key = (emp.get('division') or '(미분류)', emp.get('team') or '(미분류)')
    team_stats[key]['total'] += 1
    if emp['id'] in sel_present:
        team_stats[key]['present'] += 1


def _rate(p, t):
    return round(p / t * 100, 1) if t else 0.0


rows = []
for div in sorted({k[0] for k in team_stats}):
    keys = sorted([k for k in team_stats if k[0] == div], key=lambda x: x[1])
    for k in keys:
        s = team_stats[k]
        rows.append({'본부': k[0], '팀': k[1], '출근인원': s['present'], '등록인원': s['total'],
                     '출근율(%)': _rate(s['present'], s['total'])})
    dp = sum(team_stats[k]['present'] for k in keys)
    dt = sum(team_stats[k]['total'] for k in keys)
    rows.append({'본부': f'▶ {div} 소계', '팀': '', '출근인원': dp, '등록인원': dt, '출근율(%)': _rate(dp, dt)})

tp = sum(v['present'] for v in team_stats.values())
tt = sum(v['total'] for v in team_stats.values())
rows.append({'본부': '▶▶ 전체 총계', '팀': '', '출근인원': tp, '등록인원': tt, '출근율(%)': _rate(tp, tt)})

tdf = pd.DataFrame(rows)


def _style_row(row):
    label = str(row['본부'])
    if '총계' in label:
        return ['font-weight: bold; background-color: #c8d8e8'] * len(row)
    if '소계' in label:
        return ['font-weight: bold; background-color: #e8e8e8'] * len(row)
    styles = [''] * len(row)
    if row['출근율(%)'] < 70:
        styles[4] = 'color: #c0392b; font-weight: bold'
    return styles


st.dataframe(tdf.style.apply(_style_row, axis=1).format({'출근율(%)': '{:.1f}%'}),
             width="stretch", hide_index=True)
st.caption("⚠️ 출근율 70% 미만: 빨간색 강조")

# 미출근자 명단
absent = [e for e in employees if e['id'] not in sel_present]
if absent:
    with st.expander(f"미출근자 명단 ({len(absent)}명, {selected_date})"):
        labels = sidebar.employee_labels(employees)
        st.dataframe(pd.DataFrame([{'본부': e.get('division') or '', '팀': e.get('team') or '',
                                    '이름': labels[e['id']], '연락처': e.get('phone') or ''} for e in absent]),
                     width="stretch", hide_index=True)

# ── 최근 30일 출근 추이 ───────────────────────────────────────────
st.markdown("---")
st.markdown("#### 최근 30일 출근 추이")

start_date = today - timedelta(days=29)
daily_counts = db.get_daily_attendance_counts(site_id, start_date, today)
chart_df = pd.DataFrame([
    {'날짜': pd.Timestamp(d), '출근인원': daily_counts.get(str(d), 0), '주말': d.weekday() >= 5}
    for d in (start_date + timedelta(days=i) for i in range(30))
])

try:
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=chart_df['날짜'], y=chart_df['출근인원'], mode='lines',
                             line=dict(color='steelblue', width=2), showlegend=False, hoverinfo='skip'))
    for mask, name, color, symbol in ((~chart_df['주말'], '평일', 'steelblue', 'circle'),
                                      (chart_df['주말'], '주말', 'tomato', 'diamond')):
        fig.add_trace(go.Scatter(
            x=chart_df[mask]['날짜'], y=chart_df[mask]['출근인원'], mode='markers', name=name,
            marker=dict(color=color, size=7, symbol=symbol),
            hovertemplate='%{x|%y/%m/%d}<br>출근: %{y}명<extra></extra>'))
    for d in chart_df[chart_df['주말']]['날짜']:
        fig.add_vrect(x0=d - pd.Timedelta(hours=12), x1=d + pd.Timedelta(hours=12),
                      fillcolor='lightsalmon', opacity=0.15, line_width=0)
    fig.update_layout(xaxis_title='날짜', yaxis_title='출근인원', height=320,
                      margin=dict(l=0, r=0, t=10, b=0),
                      legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
    fig.update_xaxes(tickformat='%y/%m/%d', tickangle=-45)
    st.plotly_chart(fig, width="stretch")
except ImportError:
    st.line_chart(chart_df.set_index('날짜')['출근인원'])
