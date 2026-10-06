"""ui/emp_upload.py — 직원·출근 엑셀 업로드 (분석 → 반영 2단계). 기존 검증 로직 그대로."""
import io
import re
from datetime import date, datetime, timedelta

import pandas as pd

import db
from ui import common as cm

REGIONS = ['해당지역', '타지역']
STATUSES = ['재직', '퇴직']

PRESENT_MARKS = {'O', '○', '◯', '1', 'Y', 'V', '✓', '출', '출근'}


def make_template(site):
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
    return cm.excel_bytes({'직원정보': example, f'{first.month}월출근현황': att, '업로드안내': guide})


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


def analyze_upload(file_bytes, default_year, accessible_sites):
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
