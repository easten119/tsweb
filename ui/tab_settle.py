"""
정산 탭 — 일비 · 숙소비 · 정산대장 · 이력 (이 현장)
지급 규정은 calc.py 그대로 (일비: 70%+11일, 1회 이월 / 숙소비: 30일 판정 25일, 5일·20일 집행).
"""
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import calc
import db
from ui import common as cm


def render(ctx):
    sub = st.segmented_control("정산", ["정산대장", "일비", "숙소비", "정산 이력"], default="정산대장",
                               key=f"settle_sub_{ctx['site_id']}", label_visibility="collapsed")
    {"일비": _daily, "숙소비": _housing, "정산 이력": _history}.get(sub, _ledger)(ctx)


def _exec_select(key, container=None):
    opts = calc.nearest_execution_dates()
    return (container or st).selectbox("집행일 (5일 / 20일)", opts, index=opts.index(calc.default_execution_date()),
                                       key=key, format_func=lambda d: d.strftime('%Y-%m-%d (%a)'))


def _items(rows):
    return [dict(site_id=r['site_id'], employee_id=r['employee_id'], settlement_type=r['type'],
                 execution_date=r['exec'], period_start=r['ps'], period_end=r['pe'],
                 work_days=r['work_days'], amount=r['amount']) for r in rows]


# ── 일비 ──────────────────────────────────────────────────────────
def _daily(ctx):
    site_id = ctx['site_id']
    rate = db.get_site_rates(site_id)[0]
    today = date.today()
    years = list(range(min(2024, today.year - 1), today.year + 2))
    c = st.columns([1, 1, 1.4, 3])
    year = c[0].selectbox("연도", years, index=years.index(today.year), key="dy_y")
    month = c[1].selectbox("월", list(range(1, 13)), index=today.month - 1, key="dy_m")
    term = c[2].selectbox("차수", [1, 2], key="dy_t", format_func=lambda t: f"{t}차 ({'1~15일' if t == 1 else '16~말일'})")
    ps, pe = calc.term_period(year, month, term)
    ex = calc.daily_execution_date(year, month, term)
    st.caption(f"판정기간 {ps} ~ {pe} · 집행일 {ex} · 단가 {rate:,}원 · 가능일수 70% 이상 + 11일 이상 지급, "
               "70% 충족·11일 미만은 다음 차수로 1회 이월")
    emps = db.get_employees_for_period(site_id, ps, pe)
    labels = cm.employee_labels(emps)
    att = calc.load_attendance(site_id, *calc.daily_attendance_range(year, month, term))
    saved = {r['employee_id']: r for r in db.get_settlements(site_id=site_id, settlement_type='daily_allowance',
                                                              execution_date=ex)}
    res, rows = [], []
    for e in emps:
        r = calc.calc_daily_allowance(e['id'], year, month, term, daily_rate=rate, att=att)
        res.append((e, r))
        sv = saved.get(e['id'])
        rows.append({'본부': e.get('division') or '', '팀': e.get('team') or '',
                     '이름': labels[e['id']] + (' (퇴직)' if e['status'] != '재직' else ''),
                     '출근': r['work_days'], '가능': r['possible_days'], '기준': r['threshold'],
                     '이월': '이월↗' if r['status'] == '이월' else (f"+{r['carry_in_days']}일" if r['carry_over'] else ''),
                     '상태': r['status'], '지급일수': r['pay_days'], '지급액': r['amount'],
                     '이력': ('저장됨' if sv and sv['amount'] == r['amount'] else
                            (f"저장값 {sv['amount']:,}" if sv else ('미저장' if r['amount'] else '')))})
    if not rows:
        st.info("대상 직원이 없습니다.")
        return
    df = pd.DataFrame(rows)
    colors = {'지급': '#E7F4EA', '이월': '#FFF6DA', '소멸': '#FBE3E3', '미충족': '#F3F4F6'}
    st.dataframe(df.style.apply(lambda r: [f"background-color:{colors.get(r['상태'], '')}"] * len(r), axis=1)
                 .format({'지급액': '{:,}'}), hide_index=True, placeholder="", width="stretch")
    pay = [(e, r) for e, r in res if r['status'] == '지급' and r['amount'] > 0]
    m = st.columns(3)
    m[0].metric("지급 대상", f"{len(pay)}명")
    m[1].metric("총 지급액", f"{sum(r['amount'] for _, r in pay):,}원")
    m[2].metric("이월 / 소멸", f"{sum(r['status'] == '이월' for _, r in res)} / {sum(r['status'] == '소멸' for _, r in res)}")
    c = st.columns([1.4, 1, 4])
    if c[0].button(f"정산 이력 저장 ({len(pay)}건)", type="primary", disabled=not pay, icon=":material/save:"):
        db.save_settlements(_items([dict(site_id=site_id, employee_id=e['id'], type='daily_allowance', exec=ex,
                                         ps=r['period_start'], pe=r['period_end'], work_days=r['work_days'],
                                         amount=r['amount']) for e, r in pay]))
        cm.flash(f"일비 {len(pay)}건 저장 (집행일 {ex})")
        st.rerun()
    c[1].download_button("엑셀", data=cm.excel_bytes({'일비': df}), icon=":material/download:",
                         file_name=f"일비_{ctx['site']['name']}_{year}{month:02d}_{term}차.xlsx", mime=cm.XLSX_MIME)


# ── 숙소비 ────────────────────────────────────────────────────────
def _housing(ctx):
    site_id = ctx['site_id']
    c = st.columns([1.4, 4])
    ex = _exec_select("hs_ex", c[0])
    rates = db.get_site_rates(site_id)
    st.caption(f"해당지역 {rates[1]:,}원 / 타지역 {rates[2]:,}원 · 첫출근일부터 30일 단위 판정, 25일 이상 출근 시 지급")
    look = ex - timedelta(days=calc.HOUSING_LOOKBACK_DAYS)
    emps = db.get_employees_for_period(site_id, look, ex)
    labels = cm.employee_labels(emps)
    att = calc.load_attendance(site_id, look, ex)
    saved = {r['employee_id']: r for r in db.get_settlements(site_id=site_id, settlement_type='housing',
                                                              execution_date=ex)}
    res, rows = [], []
    for e in emps:
        r = calc.calc_housing(e['id'], ex, emp=e, rates=rates, att=att)
        res.append((e, r))
        if not r['is_target']:
            continue
        sv = saved.get(e['id'])
        rows.append({'본부': e.get('division') or '', '팀': e.get('team') or '', '이름': labels[e['id']],
                     '지역구분': e.get('housing_region'), '판정기간': f"{r['period_start']} ~ {r['period_end']}",
                     '출근': r['work_days'], '충족': '○' if r['is_qualified'] else '×', '지급액': r['amount'],
                     '이력': ('저장됨' if sv and sv['amount'] == r['amount'] else
                            (f"저장값 {sv['amount']:,}" if sv else ('미저장' if r['amount'] else '')))})
    no_fwd = [labels[e['id']] for e, r in res if r.get('reason') == '첫출근일 없음']
    if no_fwd:
        st.warning("첫출근일이 없어 계산하지 못한 직원: " + ", ".join(no_fwd))
    if not rows:
        st.info("이번 집행일 대상자가 없습니다.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df.style.apply(lambda r: [f"background-color:{'#E7F4EA' if r['충족'] == '○' else '#FFF6DA'}"] * len(r),
                                axis=1).format({'지급액': '{:,}'}), hide_index=True, placeholder="", width="stretch")
    pay = [(e, r) for e, r in res if r['is_target'] and r['is_qualified'] and r['amount'] > 0]
    m = st.columns(3)
    m[0].metric("지급 대상", f"{len(pay)}명")
    m[1].metric("총 지급액", f"{sum(r['amount'] for _, r in pay):,}원")
    m[2].metric("대상 중 미충족", f"{sum(1 for _, r in res if r['is_target'] and not r['is_qualified'])}명")
    c = st.columns([1.4, 1, 4])
    if c[0].button(f"정산 이력 저장 ({len(pay)}건)", type="primary", disabled=not pay, icon=":material/save:"):
        db.save_settlements(_items([dict(site_id=site_id, employee_id=e['id'], type='housing', exec=ex,
                                         ps=r['period_start'], pe=r['period_end'], work_days=r['work_days'],
                                         amount=r['amount']) for e, r in pay]))
        cm.flash(f"숙소비 {len(pay)}건 저장 (집행일 {ex})")
        st.rerun()
    c[1].download_button("엑셀", data=cm.excel_bytes({'숙소비': df}), icon=":material/download:",
                         file_name=f"숙소비_{ctx['site']['name']}_{ex}.xlsx", mime=cm.XLSX_MIME)


# ── 정산대장 ──────────────────────────────────────────────────────
def _ledger(ctx):
    site_id = ctx['site_id']
    c = st.columns([1.4, 4])
    ex = _exec_select("lg_ex", c[0])
    dy, dm, dt = calc.daily_term_for_execution(ex)
    dps, dpe = calc.term_period(dy, dm, dt)
    st.caption(f"집행일 {ex} — 일비: {dy}년 {dm}월 {dt}차 ({dps} ~ {dpe}) · 숙소비: 이 집행일 대상자")
    rates = db.get_site_rates(site_id)
    look = min(calc.daily_attendance_range(dy, dm, dt)[0], ex - timedelta(days=calc.HOUSING_LOOKBACK_DAYS))
    emps = db.get_employees_for_period(site_id, min(dps, ex - timedelta(days=calc.HOUSING_LOOKBACK_DAYS)), ex)
    labels = cm.employee_labels(emps)
    att = calc.load_attendance(site_id, look, max(dpe, ex))
    rows, items = [], []
    for e in emps:
        d = calc.calc_daily_allowance(e['id'], dy, dm, dt, daily_rate=rates[0], att=att)
        h = calc.calc_housing(e['id'], ex, emp=e, rates=rates, att=att)
        da = d['amount'] if d['status'] == '지급' else 0
        ha = h['amount'] if (h['is_target'] and h['is_qualified']) else 0
        if not da and not ha:
            continue
        rows.append({'본부': e.get('division') or '(미분류)', '팀': e.get('team') or '', '이름': labels[e['id']],
                     '일비일수': d['pay_days'] if da else 0, '일비': da, '숙소비': ha,
                     '지역구분': e.get('housing_region') if ha else '', '합계': da + ha})
        if da:
            items.append(dict(site_id=site_id, employee_id=e['id'], type='daily_allowance', exec=d['execution_date'],
                              ps=d['period_start'], pe=d['period_end'], work_days=d['work_days'], amount=da))
        if ha:
            items.append(dict(site_id=site_id, employee_id=e['id'], type='housing', exec=ex,
                              ps=h['period_start'], pe=h['period_end'], work_days=h['work_days'], amount=ha))
    if not rows:
        st.info("이 집행일 지급 대상이 없습니다.")
        return
    df = pd.DataFrame(rows)
    table = []
    for div, g in df.groupby('본부', sort=True):
        table += g.to_dict('records')
        table.append({'본부': f'{div} 소계', '팀': '', '이름': '', '일비일수': int(g['일비일수'].sum()),
                      '일비': int(g['일비'].sum()), '숙소비': int(g['숙소비'].sum()), '지역구분': '', '합계': int(g['합계'].sum())})
    table.append({'본부': '전체 합계', '팀': '', '이름': '', '일비일수': int(df['일비일수'].sum()), '일비': int(df['일비'].sum()),
                  '숙소비': int(df['숙소비'].sum()), '지역구분': '', '합계': int(df['합계'].sum())})
    tdf = pd.DataFrame(table)
    st.dataframe(tdf.style.apply(lambda r: ['font-weight:bold;background:#EEF1F5'] * len(r)
                                 if ('소계' in str(r['본부']) or '합계' in str(r['본부'])) else [''] * len(r), axis=1)
                 .format({'일비': '{:,}', '숙소비': '{:,}', '합계': '{:,}'}), hide_index=True, placeholder="", width="stretch")
    m = st.columns(4)
    m[0].metric("집행 인원", f"{len(df)}명")
    m[1].metric("일비", f"{int(df['일비'].sum()):,}원")
    m[2].metric("숙소비", f"{int(df['숙소비'].sum()):,}원")
    m[3].metric("합계", f"{int(df['합계'].sum()):,}원")
    c = st.columns([1.6, 1, 4])
    if c[0].button(f"정산이력 일괄저장 ({len(items)}건)", type="primary", icon=":material/save:"):
        db.save_settlements(_items(items))
        cm.flash(f"저장 완료 — {len(items)}건 (집행일 {ex})")
        st.rerun()
    c[1].download_button("엑셀", data=cm.excel_bytes({'정산대장': tdf}), icon=":material/download:",
                         file_name=f"정산대장_{ctx['site']['name']}_{ex}.xlsx", mime=cm.XLSX_MIME)


# ── 이력 ──────────────────────────────────────────────────────────
def _history(ctx):
    site_id = ctx['site_id']
    hist = db.get_settlements(site_id=site_id)
    if not hist:
        st.info("저장된 정산 이력이 없습니다.")
        return
    by = defaultdict(list)
    for r in hist:
        by[r['execution_date']].append(r)
    summ = pd.DataFrame([{'집행일': d,
                          '일비': sum(r['amount'] for r in rs if r['settlement_type'] == 'daily_allowance'),
                          '숙소비': sum(r['amount'] for r in rs if r['settlement_type'] == 'housing'),
                          '합계': sum(r['amount'] for r in rs), '건수': len(rs)} for d, rs in sorted(by.items(), reverse=True)])
    st.dataframe(summ, hide_index=True, placeholder="", width="stretch",
                 column_config={'일비': cm.MONEY, '숙소비': cm.MONEY, '합계': cm.MONEY})
    sel = st.selectbox("상세 볼 집행일", list(summ['집행일']), key="sh_d")
    recs = by[sel]
    det = pd.DataFrame([{'_id': r['id'], '선택': False, '본부': r.get('employee_division') or '',
                         '팀': r.get('employee_team') or '', '이름': r['employee_name'],
                         '유형': '일비' if r['settlement_type'] == 'daily_allowance' else '숙소비',
                         '판정기간': f"{r['period_start']} ~ {r['period_end']}", '출근일수': r['work_days'],
                         '지급액': r['amount']} for r in recs])
    ed = st.data_editor(det, hide_index=True, placeholder="", width="stretch", key=f"sh_ed_{sel}",
                        disabled=[c for c in det.columns if c != '선택'],
                        column_config={'_id': None, '선택': st.column_config.CheckboxColumn('선택', width=50),
                                       '지급액': cm.MONEY})
    ids = ed.loc[ed['선택'] == True, '_id'].tolist()  # noqa: E712
    if ids:
        st.warning(f"{len(ids)}건을 삭제합니다. 이미 지급한 건이면 삭제하지 마세요.")
        if st.button(f"선택 {len(ids)}건 삭제", type="primary"):
            n = db.delete_settlements(ids, allowed_site_ids=[site_id])
            cm.flash(f"{n}건 삭제")
            st.rerun()
