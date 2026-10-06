"""ui/common.py — 화면 공통 헬퍼 (권한·선택·금액·알림·엑셀)"""
import io
from collections import Counter

import pandas as pd
import streamlit as st

import db

ROLE_LABELS = {'admin': '관리자', 'manager': '현장담당자', 'viewer': '열람'}
EDIT_ROLES = ('admin', 'manager')
MIN_PASSWORD_LEN = 8
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ── 권한 ──────────────────────────────────────────────────────────
def can_edit(user):
    return user.get('role') in EDIT_ROLES


def is_admin(user):
    return user.get('role') == 'admin'


def accessible_sites(user, sites=None):
    sites = db.get_all_sites() if sites is None else sites
    if user.get('role') == 'manager':
        allowed = set(user.get('site_ids', []))
        return [s for s in sites if s['id'] in allowed]
    return list(sites)


def password_problem(pw1, pw2):
    if not pw1:
        return "새 비밀번호를 입력하세요."
    if len(pw1) < MIN_PASSWORD_LEN:
        return f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다."
    if pw1 == db.DEFAULT_ADMIN_PASSWORD:
        return "초기 비밀번호는 사용할 수 없습니다."
    if pw1 != pw2:
        return "비밀번호가 일치하지 않습니다."
    return None


# ── 동 / 호실 ─────────────────────────────────────────────────────
def building_label(b, multi_complex):
    return f"{b['complex_name']} {b['building_no']}동" if multi_complex else f"{b['building_no']}동"


def select_building(site_id, key, label="동", container=None, include_all=False):
    buildings = db.get_buildings(site_id=site_id)
    if not buildings:
        return None, []
    multi = len({b['complex_id'] for b in buildings}) > 1
    by_id = {b['id']: b for b in buildings}
    options = ([None] if include_all else []) + list(by_id)
    bid = (container or st).selectbox(label, options, key=key,
                                      format_func=lambda i: '전체' if i is None else building_label(by_id[i], multi))
    return bid, buildings


def select_unit(units, key, label="호수", container=None, show_status=True):
    by_id = {u['id']: u for u in units}
    uid = (container or st).selectbox(
        label, list(by_id), key=key,
        format_func=lambda i: by_id[i]['unit_no'] + (f"  ({by_id[i]['status']})" if show_status else ""))
    return by_id[uid]


def unit_title(u):
    return f"{u.get('building_no') or ''}동 {u.get('unit_no') or ''}호"


def employee_labels(employees):
    """{emp_id: 표시이름} — 동명이인은 팀·연락처 끝자리로 구분."""
    counts = Counter(e['name'] for e in employees)
    labels = {}
    for e in employees:
        if counts[e['name']] > 1:
            tail = (e.get('phone') or '')[-4:]
            extra = " / ".join(x for x in [e.get('team') or '', tail and f"☎{tail}"] if x)
            labels[e['id']] = f"{e['name']} ({extra or '#' + str(e['id'])})"
        else:
            labels[e['id']] = e['name']
    if len(set(labels.values())) < len(labels):
        labels = {k: f"{v} #{k}" for k, v in labels.items()}
    return labels


# ── 금액 / 날짜 ───────────────────────────────────────────────────
def fmt_amount_key(key):
    cleaned = str(st.session_state.get(key, "")).replace(",", "").replace(" ", "")
    if cleaned.isdigit():
        st.session_state[key] = f"{int(cleaned):,}"


def parse_amount(text):
    cleaned = str(text or "").replace(",", "").replace(" ", "").replace("원", "")
    if not cleaned:
        return 0
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def won(v):
    try:
        return f"{int(v or 0):,}"
    except (TypeError, ValueError):
        return "-"


def to_date(v):
    """'YYYY-MM-DD' / date / Timestamp → date 또는 None"""
    from datetime import date, datetime
    if v is None or v == '':
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def date_str(v):
    d = to_date(v)
    return str(d) if d else None


# ── 알림 / 엑셀 ───────────────────────────────────────────────────
def flash(msg, kind="success"):
    st.session_state['_flash'] = (kind, msg)


def show_flash():
    item = st.session_state.pop('_flash', None)
    if item:
        if item[0] == 'success':
            st.toast(item[1], icon=":material/check_circle:")
        else:
            getattr(st, item[0])(item[1])


def excel_bytes(sheets):
    """{시트명: DataFrame} → xlsx bytes (열 너비 자동)"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        for name, df in sheets.items():
            sn = str(name)[:31]
            df.to_excel(writer, index=False, sheet_name=sn)
            ws = writer.sheets[sn]
            for col_cells in ws.columns:
                width = max(len(str(c.value or '')) for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max(8, width * 1.6), 40)
    return buf.getvalue()


def section(title, caption=None):
    st.markdown(f"<div class='ts-section'>{title}</div>", unsafe_allow_html=True)
    if caption:
        st.caption(caption)


MONEY = st.column_config.NumberColumn(format="localized")
