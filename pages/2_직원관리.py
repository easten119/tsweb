import io
import re
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import db
import sidebar

user = sidebar.page_setup("직원 관리", "👷", roles=sidebar.EDIT_ROLES)
sidebar.show_flash()

site_id, site, accessible_sites = sidebar.select_site(user)

REGIONS = ['해당지역', '타지역']
STATUSES = ['재직', '퇴직']

# ── 직원 목록 ──────────────────────────────────────────────────────
fc1, fc2 = st.columns([1, 3])
show_retired = fc1.checkbox("퇴직자 포함")
keyword = fc2.text_input("검색 (이름·팀·연락처)", placeholder="예: 홍길동, 1팀, 1234", label_visibility="collapsed")
employees = db.get_employees(site_id, include_retired=show_retired)
labels = sidebar.employee_labels(db.get_employees(site_id, include_retired=True))

if keyword.strip():
    kw = keyword.strip()
    employees = [e for e in employees if any(kw in (e.get(f) or '') for f in ('name', 'team', 'division', 'phone'))]

if employees:
    df = pd.DataFrame([{
        '이름': labels.get(e['id'], e['name']), '본부': e.get('division') or '', '팀': e.get('team') or '',
        '연락처': e.get('phone') or '', '첫출근일': e.get('first_work_date') or '',
        '지역구분': e.get('housing_region') or '', '상태': e.get('status') or '', '비고': e.get('notes') or '',
    } for e in employees])
    st.dataframe(df.style.map(lambda v: 'color: gray' if v == '퇴직' else '', subset=['상태']),
                 width="stretch", hide_index=True)
    no_fwd = [e for e in employees if not e.get('first_work_date') and e['status'] == '재직']
    if no_fwd:
        st.warning(f"첫출근일이 없는 재직자 {len(no_fwd)}명 — 숙소비가 계산되지 않습니다: "
                   + ", ".join(labels[e['id']] for e in no_fwd))
else:
    st.info("조건에 맞는 직원이 없습니다.")

st.markdown("---")
tab_add, tab_edit, tab_upload = st.tabs(["➕ 직원 추가", "✏️ 직원 수정 / 퇴직 처리", "📤 엑셀 일괄 업로드"])

# ═══════════════════════════════════════════════════════════════════
with tab_add:
    with st.form("form_add_emp", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("이름 *")
        division = c2.text_input("본부")
        c3, c4 = st.columns(2)
        team = c3.text_input("팀명 (예: 1팀)")
        phone = c4.text_input("연락처", placeholder="010-0000-0000")
        c5, c6 = st.columns(2)
        first_work_date = c5.date_input("첫출근일", value=date.today())
        housing_region = c6.selectbox("지역구분", REGIONS)
        notes = st.text_input("비고")
        allow_dup = st.checkbox("같은 이름의 직원이 있어도 추가 (동명이인)")
        if st.form_submit_button("추가", type="primary"):
            nm = name.strip()
            if not nm:
                st.error("이름을 입력하세요.")
            elif db.find_employees(site_id, nm) and not allow_dup:
                st.error(f"'{nm}' 직원이 이미 있습니다. 동명이인이면 체크박스를 선택하고, 구분을 위해 연락처를 꼭 입력하세요.")
            else:
                db.add_employee(site_id, nm, division.strip() or None, team.strip() or None,
                                phone.strip() or None, str(first_work_date), housing_region,
                                notes=notes.strip() or None)
                sidebar.flash(f"'{nm}' 직원 추가 완료.")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════
with tab_edit:
    all_emps = db.get_employees(site_id, include_retired=True)
    if not all_emps:
        st.info("직원이 없습니다.")
    else:
        emp_ids = [e['id'] for e in all_emps]
        by_id = {e['id']: e for e in all_emps}
        sel_id = st.selectbox("수정할 직원 선택", emp_ids, key="edit_emp_sel",
                              format_func=lambda i: f"{labels[i]} · {by_id[i].get('team') or '-'}"
                                                    + (" (퇴직)" if by_id[i]['status'] == '퇴직' else ""))
        emp = by_id[sel_id]

        with st.form(f"form_edit_emp_{sel_id}"):
            c1, c2 = st.columns(2)
            name = c1.text_input("이름 *", value=emp['name'])
            division = c2.text_input("본부", value=emp.get('division') or '')
            c3, c4 = st.columns(2)
            team = c3.text_input("팀명", value=emp.get('team') or '')
            phone = c4.text_input("연락처", value=emp.get('phone') or '')
            c5, c6, c7 = st.columns(3)
            try:
                fwd = date.fromisoformat(emp['first_work_date'][:10]) if emp.get('first_work_date') else None
            except ValueError:
                fwd = None
            first_work_date = c5.date_input("첫출근일", value=fwd)
            housing_region = c6.selectbox("지역구분", REGIONS,
                                          index=REGIONS.index(emp['housing_region']) if emp['housing_region'] in REGIONS else 0)
            status = c7.selectbox("재직 상태", STATUSES, index=0 if emp['status'] == '재직' else 1)
            notes = st.text_input("비고", value=emp.get('notes') or '')

            if st.form_submit_button("저장", type="primary"):
                if not name.strip():
                    st.error("이름을 입력하세요.")
                else:
                    db.update_employee(emp['id'], name.strip(), division.strip() or None, team.strip() or None,
                                       phone.strip() or None, str(first_work_date) if first_work_date else None,
                                       housing_region, status, notes.strip() or None)
                    sidebar.flash("저장 완료.")
                    st.rerun()

        st.markdown("---")
        n_hist = db.count_employee_settlements(emp['id'])
        if n_hist:
            st.caption(f"🔒 정산 이력 {n_hist}건이 있어 삭제할 수 없습니다. 그만둔 직원은 '퇴직'으로 처리하세요.")
        else:
            confirm_del = st.checkbox(f"'{labels[emp['id']]}' 직원을 삭제합니다 (출근 기록 포함, 되돌릴 수 없음)",
                                      key=f"confirm_del_{emp['id']}")
            if st.button("🗑️ 삭제 확인", type="primary", disabled=not confirm_del, key="del_emp_btn"):
                ok, msg = db.delete_employee(emp['id'])
                sidebar.flash(msg, "success" if ok else "error")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════
#  엑셀 일괄 업로드 — ① 파일 분석(미리보기) → ② 반영 버튼
# ═══════════════════════════════════════════════════════════════════

PRESENT_MARKS = {'O', '○', '◯', '1', 'Y', 'V', '✓', '출', '출근'}


def make_template():
    emp_cols = ['현장명', '본부', '팀', '이름', '연락처', '첫출근일', '지역구분', '상태', '비고']
    example = pd.DataFrame([[site['name'], '1본부', '1팀', '홍길동', '010-0000-0000',
                             date.today().strftime('%Y-%m-%d'), '해당지역', '재직', '']], columns=emp_cols)
    first = date.today().replace(day=1)
    days = [(first + timedelta(days=i)) for i in range(31) if (first + timedelta(days=i)).month == first.month]
    att = pd.DataFrame([[site['name'], '1본부', '1팀', '홍길동'] + ['O' if d.weekday() < 5 else '' for d in days]],
                       columns=['현장명', '본부', '팀', '이름'] + [d.strftime('%Y-%m-%d') for d in days])
    guide = pd.DataFrame({'안내': [
        "직원정보 시트: 현장명·이름은 필수. 지역구분은 해당지역/타지역, 상태는 재직/퇴직.",
        "출근현황 시트: 시트명에 '출근'을 넣고, 날짜 헤더는 YYYY-MM-DD. 출근은 O, 미출근은 빈칸.",
        "출근은 시트에 있는 날짜만 덮어씁니다 (없는 날짜의 기존 기록은 그대로).",
        "같은 현장에 동명이인이 있으면 직원정보 시트의 연락처로 구분합니다.",
        "예시 행(홍길동)은 지우고 사용하세요.",
    ]})
    return sidebar.excel_bytes({'직원정보': example, f'{first.month}월출근현황': att, '업로드안내': guide})


def _s(val):
    if val is None:
        return None
    try:
        if val != val:  # NaN
            return None
    except Exception:
        pass
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    v = str(val).strip()
    return None if v in ('', 'nan', 'NaT', 'None') else v


def _parse_date(raw, default_year=None):
    """셀/헤더 값 → date 또는 None"""
    if raw is None:
        return None
    if isinstance(raw, (datetime, pd.Timestamp)):
        return raw.date() if not pd.isna(raw) else None
    if isinstance(raw, date):
        return raw
    s = _s(raw)
    if not s:
        return None
    part = s.split(' ')[0].split('T')[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(part, fmt).date()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})", part)
    if m and default_year:
        try:
            return date(default_year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    try:
        serial = float(s)
        if 20000 < serial < 80000:
            return date(1899, 12, 30) + timedelta(days=int(serial))
    except ValueError:
        pass
    return None


def _norm_phone(p):
    return re.sub(r'\D', '', p or '')


def _read_table(file_bytes, sheet):
    """헤더 행('이름' 셀이 있는 행)을 찾아 (헤더 리스트, 데이터 행 리스트) 반환."""
    raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None, dtype=object)
    for hi in range(min(6, len(raw))):
        vals = [_s(v) for v in raw.iloc[hi].tolist()]
        if '이름' in vals:
            return raw.iloc[hi].tolist(), raw.iloc[hi + 1:].values.tolist()
    return None, []


def analyze_upload(file_bytes, default_year):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    sheets = xls.sheet_names
    emp_sheets = [s for s in sheets if '직원' in s]
    att_sheets = [s for s in sheets if '출근' in s]
    errors, warnings = [], []
    site_map = {s['name']: s['id'] for s in accessible_sites}
    all_site_names = {s['name'] for s in db.get_all_sites()}

    # 현재 DB 직원 (접근 가능한 현장만)
    db_emps = {}
    for sid in site_map.values():
        for e in db.get_employees(sid, include_retired=True):
            db_emps.setdefault((sid, e['name']), []).append(e)

    def match_emp(sid, name, phone, row_label):
        cands = db_emps.get((sid, name), [])
        if len(cands) <= 1:
            return cands[0] if cands else None
        if phone:
            hit = [e for e in cands if _norm_phone(e.get('phone')) == _norm_phone(phone)]
            if len(hit) == 1:
                return hit[0]
        errors.append(f"{row_label}: '{name}' 동명이인 {len(cands)}명 — 연락처로 구분할 수 없어 건너뜀")
        return False

    # ── 직원정보 ──
    emp_plan = []   # dict(action, emp_id, fields)
    file_keys = {}  # (sid, name) → [(phone, plan_index)]
    for sheet in emp_sheets:
        header, rows = _read_table(file_bytes, sheet)
        if header is None:
            errors.append(f"[{sheet}] '이름' 헤더를 찾지 못했습니다.")
            continue
        h = [_s(x) for x in header]
        idx = {k: (h.index(k) if k in h else None) for k in
               ['현장명', '본부', '팀', '이름', '연락처', '첫출근일', '지역구분', '상태', '비고']}
        if idx['현장명'] is None:
            errors.append(f"[{sheet}] '현장명' 열이 없습니다.")
            continue

        def g(row, k):
            return row[idx[k]] if idx[k] is not None and idx[k] < len(row) else None

        for i, row in enumerate(rows, start=2):
            label = f"[{sheet}] {i}행"
            site_name, name = _s(g(row, '현장명')), _s(g(row, '이름'))
            if not site_name and not name:
                continue
            if not name:
                errors.append(f"{label}: 이름 없음")
                continue
            if site_name not in site_map:
                errors.append(f"{label}: 현장 '{site_name}' " +
                              ("— 담당 현장이 아님" if site_name in all_site_names else "없음"))
                continue
            sid = site_map[site_name]
            phone = _s(g(row, '연락처'))
            fwd_raw = g(row, '첫출근일')
            fwd = _parse_date(fwd_raw)
            if _s(fwd_raw) and not fwd:
                warnings.append(f"{label} ({name}): 첫출근일 '{fwd_raw}' 형식 인식 불가 → 기존값 유지")
            region = _s(g(row, '지역구분'))
            if region and region not in REGIONS:
                warnings.append(f"{label} ({name}): 지역구분 '{region}' → 해당지역/타지역만 가능, 기존값 유지")
                region = None
            status = _s(g(row, '상태'))
            if status and status not in STATUSES:
                warnings.append(f"{label} ({name}): 상태 '{status}' → 재직/퇴직만 가능, 기존값 유지")
                status = None
            fields = dict(site_id=sid, name=name, division=_s(g(row, '본부')), team=_s(g(row, '팀')),
                          phone=phone, first_work_date=str(fwd) if fwd else None, housing_region=region,
                          status=status, notes=_s(g(row, '비고')), sort_order=i)
            existing = match_emp(sid, name, phone, label)
            if existing is False:
                continue
            emp_plan.append({'action': 'update' if existing else 'insert',
                             'emp_id': existing['id'] if existing else None, 'fields': fields, 'label': label})
            file_keys.setdefault((sid, name), []).append((phone, len(emp_plan) - 1))

    # ── 출근현황 ──
    att_plan = []   # dict(plan_index or emp_id, dates{date: present})
    months = set()
    for sheet in att_sheets:
        header, rows = _read_table(file_bytes, sheet)
        if header is None:
            errors.append(f"[{sheet}] '이름' 헤더를 찾지 못했습니다.")
            continue
        h = [_s(x) for x in header]
        try:
            i_site, i_name = h.index('현장명'), h.index('이름')
        except ValueError:
            errors.append(f"[{sheet}] '현장명'/'이름' 열이 없습니다.")
            continue
        i_phone = h.index('연락처') if '연락처' in h else None
        date_cols = []
        for ci, hv in enumerate(header):
            if ci in (i_site, i_name, i_phone):
                continue
            d = _parse_date(hv, default_year)
            if d:
                date_cols.append((ci, d))
        if not date_cols:
            warnings.append(f"[{sheet}] 날짜 열을 찾지 못해 건너뜀")
            continue
        for i, row in enumerate(rows, start=2):
            label = f"[{sheet}] {i}행"
            site_name, name = _s(row[i_site]), _s(row[i_name])
            if not site_name or not name:
                continue
            if site_name not in site_map:
                errors.append(f"{label}: 현장 '{site_name}' 접근 불가/없음")
                continue
            sid = site_map[site_name]
            phone = _s(row[i_phone]) if i_phone is not None else None
            target = None
            in_file = file_keys.get((sid, name), [])
            if len(in_file) == 1 or (in_file and phone):
                pick = [p for p in in_file if not phone or _norm_phone(p[0]) == _norm_phone(phone)]
                if len(pick) == 1:
                    target = ('plan', pick[0][1])
            if target is None:
                existing = match_emp(sid, name, phone, label)
                if existing is False:
                    continue
                if not existing:
                    errors.append(f"{label}: '{name}' 직원 미등록 (직원정보 시트에도 없음)")
                    continue
                target = ('emp', existing['id'])
            dates = {}
            for ci, d in date_cols:
                v = _s(row[ci]) if ci < len(row) else None
                dates[str(d)] = 1 if (v and v.upper() in PRESENT_MARKS) else 0
                months.add((d.year, d.month))
            att_plan.append({'target': target, 'dates': dates, 'label': f"{label} {name}"})

    # 기존 출근 기록과 달라지는 칸 (재업로드로 화면 수정분이 되돌아가는 것을 미리 알림)
    to_absent = to_present = 0
    if att_plan:
        all_dates = [d for x in att_plan for d in x['dates']]
        lo, hi = min(all_dates), max(all_dates)
        current = {}
        for sid in site_map.values():
            current.update(db.get_site_attendance(sid, lo, hi))
        for x in att_plan:
            kind, ref = x['target']
            eid = ref if kind == 'emp' else emp_plan[ref]['emp_id']   # 신규 직원은 None
            if not eid:
                continue
            cur = current.get(eid, set())
            for d, p in x['dates'].items():
                if p and d not in cur:
                    to_present += 1
                elif not p and d in cur:
                    to_absent += 1

    return {'emp_plan': emp_plan, 'att_plan': att_plan, 'errors': errors, 'warnings': warnings,
            'months': sorted(months), 'emp_sheets': emp_sheets, 'att_sheets': att_sheets,
            'to_present': to_present, 'to_absent': to_absent}


def apply_upload(plan):
    return db.apply_employee_upload(plan['emp_plan'], plan['att_plan'])


with tab_upload:
    st.markdown("##### 엑셀 일괄 업로드")
    st.caption(
        "**직원정보 시트** (시트명에 '직원'): 현장명 | 본부 | 팀 | 이름 | 연락처 | 첫출근일 | 지역구분 | 상태 | 비고  \n"
        "**출근현황 시트** (시트명에 '출근'): 현장명 | 본부 | 팀 | 이름 | 2026-04-01 | 2026-04-02 | …  (출근 **O**, 미출근 빈칸)  \n"
        "시트에 있는 날짜만 덮어쓰며, 담당 현장 데이터만 반영됩니다."
    )
    st.download_button("📄 빈 업로드 양식 받기", data=make_template(),
                       file_name="직원_출근_업로드양식.xlsx", mime=sidebar.XLSX_MIME)

    upload_year = st.number_input("날짜 헤더에 연도가 없을 때(MM/DD) 사용할 연도", min_value=2020, max_value=2040,
                                  value=date.today().year, step=1, key="upload_year")
    uploaded_file = st.file_uploader("xlsx 파일 선택", type=["xlsx"], key="emp_upload")

    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        sig = (uploaded_file.file_id if hasattr(uploaded_file, 'file_id') else uploaded_file.name, int(upload_year))
        if st.session_state.get('_emp_upload_sig') != sig:
            try:
                st.session_state['_emp_upload_plan'] = analyze_upload(file_bytes, int(upload_year))
            except Exception as e:
                st.session_state['_emp_upload_plan'] = None
                st.error(f"파일 분석 오류: {e}")
            st.session_state['_emp_upload_sig'] = sig
        plan = st.session_state.get('_emp_upload_plan')

        if plan:
            n_ins = sum(1 for x in plan['emp_plan'] if x['action'] == 'insert')
            n_upd = len(plan['emp_plan']) - n_ins
            n_cells = sum(len(x['dates']) for x in plan['att_plan'])
            n_present = sum(sum(x['dates'].values()) for x in plan['att_plan'])
            st.markdown("**분석 결과 (아직 반영 전)**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("신규 직원", f"{n_ins}명")
            m2.metric("정보 갱신", f"{n_upd}명")
            m3.metric("출근 기록", f"{len(plan['att_plan'])}명분", f"{n_cells}칸 (출근 {n_present})", delta_color="off")
            m4.metric("오류", f"{len(plan['errors'])}건")
            st.caption(f"직원 시트: {', '.join(plan['emp_sheets']) or '없음'} · 출근 시트: "
                       f"{', '.join(plan['att_sheets']) or '없음'} · 대상 월: "
                       f"{', '.join(f'{y}-{m:02d}' for y, m in plan['months']) or '-'}")
            if plan.get('to_absent'):
                st.warning(f"⚠️ 현재 '출근'인 {plan['to_absent']}칸이 이 파일 기준 '미출근'으로 바뀝니다. "
                           "업로드 후 화면에서 고친 기록이 있다면 되돌아갈 수 있으니 확인하세요.")
            if plan.get('to_present'):
                st.caption(f"새로 '출근'으로 기록되는 칸: {plan['to_present']}칸")
            if plan['emp_plan']:
                with st.expander("직원 반영 내역 보기"):
                    st.dataframe(pd.DataFrame([{
                        '구분': '신규' if x['action'] == 'insert' else '갱신', '위치': x['label'],
                        '이름': x['fields']['name'], '팀': x['fields']['team'], '연락처': x['fields']['phone'],
                        '첫출근일': x['fields']['first_work_date'], '지역구분': x['fields']['housing_region'],
                        '상태': x['fields']['status']} for x in plan['emp_plan']]), width="stretch", hide_index=True)
            for title, items, fn in (("오류 (반영되지 않음)", plan['errors'], st.error),
                                     ("주의", plan['warnings'], st.warning)):
                if items:
                    with st.expander(f"{title} {len(items)}건", expanded=title.startswith("오류")):
                        for msg in items[:300]:
                            fn(msg)

            if plan['emp_plan'] or plan['att_plan']:
                if st.button("✅ 업로드 반영", type="primary"):
                    ins, upd, cells = apply_upload(plan)
                    st.session_state.pop('_emp_upload_plan', None)
                    st.session_state.pop('_emp_upload_sig', None)
                    st.session_state.pop('emp_upload', None)
                    sidebar.flash(f"반영 완료 — 신규 {ins}명, 갱신 {upd}명, 출근 {cells}칸")
                    st.rerun()
