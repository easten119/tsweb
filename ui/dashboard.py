"""ui/dashboard.py — 전체 현장 대시보드"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
import templates
from ui import common as cm
from ui import layout


def _site_rows(sites, unit_summary, cancel_counts, contracts):
    today = date.today()
    week_ago = str(today - timedelta(days=6))
    rows = []
    for s in sites:
        cfg = templates.load_config(s)
        summary = unit_summary.get(s['id'], {})
        total = sum(summary.values())
        names = templates.status_names(cfg)
        signed = sum(summary.get(n, 0) for n in names)
        cts = [c for c in contracts if c['site_id'] == s['id']]
        recent = sum(1 for c in cts if str(c.get('pre_date') or c.get('contract_date') or '') >= week_ago)
        rows.append({
            '_id': s['id'], '현장명': s['name'], '지역': s['region'],
            '양식': s.get('template') or '-',
            '총세대': total or None,
            '계약': summary.get('계약', 0) if total else None,
            '가계약': summary.get('가계약', 0) if total else None,
            '기타': (signed - summary.get('계약', 0) - summary.get('가계약', 0)) if total else None,
            '공실': summary.get('공실', 0) if total else None,
            '계약률': round(signed / total * 100, 1) if total else None,
            '최근7일': recent,
            '누적해지': cancel_counts.get(s['id'], 0),
            '재직': s['employee_count'],
            '시작일': s['start_date'],
        })
    return pd.DataFrame(rows)


def _site_table(df, key):
    if df.empty:
        st.info("해당 현장이 없습니다.")
        return
    event = st.dataframe(
        df, hide_index=True, placeholder="", width="stretch", key=key, on_select="rerun", selection_mode="single-row",
        column_order=[c for c in df.columns if c != '_id'],
        column_config={
            '계약률': st.column_config.ProgressColumn('계약률', format="%.1f%%", min_value=0, max_value=100),
            '기타': st.column_config.NumberColumn('기타상태', help="소송 등 현장별 추가 상태"),
            '최근7일': st.column_config.NumberColumn('최근 7일 신규', help="가계약·계약 등록일 기준"),
        })
    rows = event.selection.rows if hasattr(event, 'selection') else []
    if rows:
        layout.go('site', int(df.iloc[rows[0]]['_id']), tab='현황판')
    st.caption("행을 클릭하면 현장 화면으로 이동합니다.")


def render(user):
    st.markdown(f"<div class='ts-crumb'>{date.today():%Y년 %m월 %d일}</div><div class='ts-title'>대시보드</div>",
                unsafe_allow_html=True)
    sites = cm.accessible_sites(user)
    active = [s for s in sites if s['status'] == '진행중']
    done = [s for s in sites if s['status'] != '진행중']
    if not sites:
        st.info("등록된 현장이 없습니다." + (" 좌측 '현장 관리'에서 현장을 추가하세요." if cm.is_admin(user) else ""))
        return

    unit_summary = db.get_all_site_unit_summary()
    cancel_counts = db.get_cancel_counts_by_site()
    contracts = db.get_contracts(active_only=True)

    # 상단 지표: 진행중 현장만
    total = signed = 0
    for s in active:
        cfg = templates.load_config(s)
        summ = unit_summary.get(s['id'], {})
        total += sum(summ.values())
        signed += sum(summ.get(n, 0) for n in templates.status_names(cfg))
    month_start = str(date.today().replace(day=1))
    active_ids = {s['id'] for s in active}
    new_month = sum(1 for c in contracts if c['site_id'] in active_ids
                    and str(c.get('pre_date') or c.get('contract_date') or '') >= month_start)
    emp = sum(s['employee_count'] for s in active)
    cells = [("진행중 현장", f"{len(active)}", "개"), ("총 세대", f"{total:,}", ""), ("계약(전체 상태)", f"{signed:,}", ""),
             ("계약률", f"{signed / total * 100:.1f}" if total else "-", "%" if total else ""),
             ("이번 달 신규", f"{new_month:,}", "건"), ("재직 인원", f"{emp:,}", "명"), ("완료 현장", f"{len(done)}", "개")]
    st.markdown("<div class='ts-kpis'>" + "".join(
        f"<div class='ts-kpi'><div class='l'>{l}</div><div class='v'>{v}<small>{u}</small></div></div>"
        for l, v, u in cells) + "</div>", unsafe_allow_html=True)

    t1, t2 = st.tabs([f"진행중 현장 {len(active)}", f"완료 현장 {len(done)}"])
    with t1:
        _site_table(_site_rows(active, unit_summary, cancel_counts, contracts), "dash_active")
    with t2:
        _site_table(_site_rows(done, unit_summary, cancel_counts, contracts), "dash_done")
