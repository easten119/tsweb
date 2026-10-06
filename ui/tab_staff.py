"""직원·근태 탭 — 출근현황 · 출근입력 · 직원관리 (이 현장 직원만)"""
import calendar
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import db
from ui import common as cm
from ui import emp_upload

REGIONS = emp_upload.REGIONS
STATUSES = emp_upload.STATUSES


def render(ctx):
    sub = st.segmented_control("직원·근태", ["출근현황", "출근입력", "직원관리"], default="출근현황",
                               key=f"staff_sub_{ctx['site_id']}", label_visibility="collapsed")
    if sub == "출근입력":
        _attendance_input(ctx)
    elif sub == "직원관리":
        _employees(ctx)
    else:
        _attendance_status(ctx)


# ── 출근현황 ──────────────────────────────────────────────────────
def _attendance_status(ctx):
    site_id = ctx['site_id']
    employees = db.get_employees(site_id)
    emp_ids = {e['id'] for e in employees}
    today = date.today()
    sel_date = st.date_input("조회 날짜", value=today, max_value=today, format="YYYY-MM-DD", key="as_date")
    present = set(db.get_site_attendance(site_id, sel_date, sel_date)) & emp_ids
    n, p = len(employees), len(present)
    m = st.columns(4)
    m[0].metric("재직", f"{n}명")
    m[1].metric("출근", f"{p}명")
    m[2].metric("미출근", f"{n - p}명")
    m[3].metric("출근율", f"{p / n * 100:.1f}%" if n else "-")

    stats = defaultdict(lambda: [0, 0])
    for e in employees:
        k = (e.get('division') or '(미분류)', e.get('team') or '(미분류)')
        stats[k][1] += 1
        stats[k][0] += e['id'] in present
    rows = []
    for div in sorted({k[0] for k in stats}):
        keys = sorted(k for k in stats if k[0] == div)
        for k in keys:
            rows.append({'본부': div, '팀': k[1], '출근': stats[k][0], '재직': stats[k][1],
                         '출근율(%)': round(stats[k][0] / stats[k][1] * 100, 1)})
        dp, dt = sum(stats[k][0] for k in keys), sum(stats[k][1] for k in keys)
        rows.append({'본부': f'{div} 소계', '팀': '', '출근': dp, '재직': dt, '출근율(%)': round(dp / dt * 100, 1)})
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df.style.apply(lambda r: ['font-weight:bold;background:#EEF1F5'] * len(r)
                                    if '소계' in str(r['본부']) else [''] * len(r), axis=1)
                     .format({'출근율(%)': '{:.1f}'}), hide_index=True, placeholder="", width="stretch")
    absent = [e for e in employees if e['id'] not in present]
    if absent:
        with st.expander(f"미출근자 {len(absent)}명"):
            labels = cm.employee_labels(employees)
            st.dataframe(pd.DataFrame([{'본부': e.get('division') or '', '팀': e.get('team') or '',
                                        '이름': labels[e['id']], '연락처': e.get('phone') or ''} for e in absent]),
                         hide_index=True, placeholder="", width="stretch")
    start = today - timedelta(days=29)
    counts = db.get_daily_attendance_counts(site_id, start, today)
    chart = pd.DataFrame({'출근인원': [counts.get(str(start + timedelta(days=i)), 0) for i in range(30)]},
                         index=pd.to_datetime([start + timedelta(days=i) for i in range(30)]))
    cm.section("최근 30일 출근 인원")
    st.bar_chart(chart, height=200)


# ── 출근입력 ──────────────────────────────────────────────────────
def _attendance_input(ctx):
    site_id, site = ctx['site_id'], ctx['site']
    today = date.today()
    years = list(range(min(2024, today.year - 1), today.year + 2))
    c = st.columns([1, 1, 4])
    year = c[0].selectbox("연도", years, index=years.index(today.year), key="ai_y")
    month = c[1].selectbox("월", list(range(1, 13)), index=today.month - 1, key="ai_m")
    last = calendar.monthrange(year, month)[1]
    ms, me = date(year, month, 1), date(year, month, last)
    days = list(range(1, last + 1))
    employees = db.get_employees_for_period(site_id, ms, me)
    if not employees:
        st.info("등록된 직원이 없습니다. 직원관리에서 먼저 등록하세요.")
        return
    labels = cm.employee_labels(employees)
    att = db.get_site_attendance(site_id, ms, me)

    def day_label(d):
        wd = date(year, month, d).weekday()
        return f"{d}({'토' if wd == 5 else '일'})" if wd >= 5 else str(d)

    rows = []
    for e in employees:
        work = att.get(e['id'], set())
        r = {'_id': e['id'], '이름': labels[e['id']] + (' (퇴직)' if e['status'] != '재직' else ''),
             '본부': e.get('division') or '', '팀': e.get('team') or ''}
        r.update({str(d): f"{year}-{month:02d}-{d:02d}" in work for d in days})
        rows.append(r)
    df = pd.DataFrame(rows)
    conf = {'_id': None, '이름': st.column_config.TextColumn('이름', disabled=True, pinned=True),
            '본부': st.column_config.TextColumn('본부', disabled=True, width=60),
            '팀': st.column_config.TextColumn('팀', disabled=True, width=55),
            **{str(d): st.column_config.CheckboxColumn(day_label(d), default=False, width=38) for d in days}}
    key = f"att_{site_id}_{year}_{month}"
    if st.session_state.get("_att_ctx") != key:
        for k in [k for k in st.session_state if str(k).startswith("att_")]:
            del st.session_state[k]
        st.session_state["_att_ctx"] = key
    edited = st.data_editor(df, column_config=conf, hide_index=True, placeholder="", width="stretch", key=key, num_rows="fixed",
                            disabled=not ctx['editable'])
    records = []
    for (_, b), (_, a) in zip(df.iterrows(), edited.iterrows()):
        for d in days:
            if bool(b[str(d)]) != bool(a[str(d)]):
                records.append((int(a['_id']), f"{year}-{month:02d}-{d:02d}", 1 if a[str(d)] else 0))
    c = st.columns([1, 4])
    if c[0].button(f"저장 ({len(records)}칸)", type="primary", disabled=not records, icon=":material/save:"):
        db.save_attendance_records(records)
        st.session_state.pop(key, None)
        cm.flash(f"{year}년 {month}월 출근 {len(records)}칸 저장")
        st.rerun()
    if records:
        c[1].warning("저장하지 않은 변경이 있습니다.")

    summary = []
    for e in employees:
        work = att.get(e['id'], set())
        t1 = sum(1 for d in work if int(d[8:10]) <= 15)
        summary.append({'본부': e.get('division') or '', '팀': e.get('team') or '', '이름': labels[e['id']],
                        '1차(1~15일)': t1, '2차(16~말일)': len(work) - t1, '월 합계': len(work)})
    sdf = pd.DataFrame(summary)
    with st.expander("월 출근 요약 (저장된 기록 기준)"):
        st.dataframe(sdf, hide_index=True, placeholder="", width="stretch")
    st.download_button("출근부 엑셀", icon=":material/download:",
                       data=cm.excel_bytes({f"{month}월출근현황": edited.drop(columns=['_id'])
                                           .replace({True: 'O', False: ''}), '요약': sdf}),
                       file_name=f"출근부_{site['name']}_{year}{month:02d}.xlsx", mime=cm.XLSX_MIME)


# ── 직원관리 ──────────────────────────────────────────────────────
def _employees(ctx):
    site_id, site = ctx['site_id'], ctx['site']
    all_emps = db.get_employees(site_id, include_retired=True)
    labels = cm.employee_labels(all_emps)
    c = st.columns([1, 3])
    show_retired = c[0].checkbox("퇴직자 포함", key="em_ret")
    kw = c[1].text_input("검색", placeholder="이름·팀·연락처", label_visibility="collapsed", key="em_q")
    emps = [e for e in all_emps if show_retired or e['status'] == '재직']
    if kw.strip():
        emps = [e for e in emps if any(kw.strip() in (e.get(f) or '') for f in ('name', 'team', 'division', 'phone'))]
    df = pd.DataFrame([{'_id': e['id'], '이름': labels[e['id']], '본부': e.get('division') or '', '팀': e.get('team') or '',
                        '연락처': e.get('phone') or '', '첫출근일': e.get('first_work_date') or '',
                        '지역구분': e.get('housing_region') or '', '상태': e['status'], '비고': e.get('notes') or ''}
                       for e in emps])
    if df.empty:
        st.info("직원이 없습니다.")
        event = None
    else:
        event = st.dataframe(df, hide_index=True, placeholder="", width="stretch", height=380, on_select="rerun",
                             selection_mode="single-row", column_config={'_id': None}, key="em_df")
        st.caption(f"{len(df)}명 · 행을 클릭하면 수정할 수 있습니다.")
    no_fwd = [e for e in all_emps if e['status'] == '재직' and not e.get('first_work_date')]
    if no_fwd:
        st.warning("첫출근일이 없는 재직자 (숙소비 계산 불가): " + ", ".join(labels[e['id']] for e in no_fwd))

    rows = event.selection.rows if event is not None and hasattr(event, 'selection') else []
    if rows:
        _edit_employee(db.get_employee(int(df.iloc[rows[0]]['_id'])), labels)

    t_add, t_up = st.tabs(["직원 추가", "엑셀 일괄 업로드"])
    with t_add:
        with st.form("em_add", clear_on_submit=True):
            r = st.columns(4)
            name = r[0].text_input("이름 *")
            div = r[1].text_input("본부")
            team = r[2].text_input("팀")
            phone = r[3].text_input("연락처")
            r = st.columns(4)
            fwd = r[0].date_input("첫출근일", value=date.today(), format="YYYY-MM-DD")
            region = r[1].selectbox("지역구분", REGIONS)
            notes = r[2].text_input("비고")
            dup = r[3].checkbox("동명이인이어도 추가")
            if st.form_submit_button("추가", type="primary"):
                nm = name.strip()
                if not nm:
                    st.error("이름을 입력하세요.")
                elif db.find_employees(site_id, nm) and not dup:
                    st.error(f"'{nm}' 직원이 이미 있습니다. 동명이인이면 체크하고 연락처를 꼭 입력하세요.")
                else:
                    db.add_employee(site_id, nm, div.strip() or None, team.strip() or None, phone.strip() or None,
                                    str(fwd), region, notes=notes.strip() or None)
                    cm.flash(f"'{nm}' 추가 완료")
                    st.rerun()
    with t_up:
        _upload(ctx)


def _edit_employee(emp, labels):
    cm.section(f"직원 수정 — {labels[emp['id']]}")
    with st.form(f"em_edit_{emp['id']}"):
        r = st.columns(4)
        name = r[0].text_input("이름 *", value=emp['name'])
        div = r[1].text_input("본부", value=emp.get('division') or '')
        team = r[2].text_input("팀", value=emp.get('team') or '')
        phone = r[3].text_input("연락처", value=emp.get('phone') or '')
        r = st.columns(4)
        fwd = r[0].date_input("첫출근일", value=cm.to_date(emp.get('first_work_date')), format="YYYY-MM-DD")
        region = r[1].selectbox("지역구분", REGIONS,
                                index=REGIONS.index(emp['housing_region']) if emp['housing_region'] in REGIONS else 0)
        status = r[2].selectbox("재직 상태", STATUSES, index=0 if emp['status'] == '재직' else 1)
        notes = r[3].text_input("비고", value=emp.get('notes') or '')
        if st.form_submit_button("저장", type="primary"):
            if not name.strip():
                st.error("이름을 입력하세요.")
            else:
                db.update_employee(emp['id'], name.strip(), div.strip() or None, team.strip() or None,
                                   phone.strip() or None, cm.date_str(fwd), region, status, notes.strip() or None)
                cm.flash("저장 완료")
                st.rerun()
    n_hist = db.count_employee_settlements(emp['id'])
    if n_hist:
        st.caption(f"정산 이력 {n_hist}건이 있어 삭제할 수 없습니다. 그만둔 직원은 '퇴직'으로 처리하세요.")
    else:
        with st.popover("직원 삭제"):
            st.caption("출근 기록도 함께 삭제되며 되돌릴 수 없습니다.")
            if st.button("삭제 확인", type="primary", key=f"em_del_{emp['id']}"):
                ok, msg = db.delete_employee(emp['id'])
                cm.flash(msg, "success" if ok else "error")
                st.rerun()


def _upload(ctx):
    site = ctx['site']
    st.caption("직원정보 시트(시트명에 '직원'): 현장명 | 본부 | 팀 | 이름 | 연락처 | 첫출근일 | 지역구분 | 상태 | 비고  ·  "
               "출근현황 시트(시트명에 '출근'): 현장명 | 본부 | 팀 | 이름 | 날짜(YYYY-MM-DD)… (출근 O)")
    st.download_button("빈 업로드 양식", data=emp_upload.make_template(site), icon=":material/description:",
                       file_name="직원_출근_업로드양식.xlsx", mime=cm.XLSX_MIME)
    year = st.number_input("헤더에 연도가 없을 때(MM/DD) 사용할 연도", 2020, 2040, date.today().year, key="em_up_y")
    f = st.file_uploader("xlsx 파일", type=["xlsx"], key="em_up_f")
    if not f:
        return
    sig = (getattr(f, 'file_id', f.name), int(year))
    if st.session_state.get('_em_up_sig') != sig:
        try:
            st.session_state['_em_up_plan'] = emp_upload.analyze_upload(f.getvalue(), int(year), [site])
        except Exception as e:  # noqa: BLE001 — 엑셀 파싱 오류를 그대로 보여준다
            st.session_state['_em_up_plan'] = None
            st.error(f"파일 분석 오류: {e}")
        st.session_state['_em_up_sig'] = sig
    plan = st.session_state.get('_em_up_plan')
    if not plan:
        return
    ins = sum(1 for x in plan['emp_plan'] if x['action'] == 'insert')
    m = st.columns(4)
    m[0].metric("신규 직원", f"{ins}명")
    m[1].metric("정보 갱신", f"{len(plan['emp_plan']) - ins}명")
    m[2].metric("출근 기록", f"{sum(len(x['dates']) for x in plan['att_plan'])}칸")
    m[3].metric("오류", f"{len(plan['errors'])}건")
    if plan.get('to_absent'):
        st.warning(f"현재 '출근'인 {plan['to_absent']}칸이 이 파일 기준 '미출근'으로 바뀝니다. 화면에서 고친 기록이 되돌아갈 수 있습니다.")
    for title, items, fn in (("오류 (반영 안 됨)", plan['errors'], st.error), ("주의", plan['warnings'], st.warning)):
        if items:
            with st.expander(f"{title} {len(items)}건", expanded=title.startswith("오류")):
                for msg in items[:300]:
                    fn(msg)
    if (plan['emp_plan'] or plan['att_plan']) and st.button("업로드 반영", type="primary"):
        a, b, c = emp_upload.apply_upload(plan)
        for k in ('_em_up_plan', '_em_up_sig', 'em_up_f'):
            st.session_state.pop(k, None)
        cm.flash(f"반영 완료 — 신규 {a}명, 갱신 {b}명, 출근 {c}칸")
        st.rerun()
