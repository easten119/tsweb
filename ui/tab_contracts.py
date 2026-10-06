"""
계약관리 탭 — 엑셀 main 시트처럼 호실 1행 = 호실정보 + 유효계약 + 납부집계.
열 구성은 현장 계약 양식(가격 항목·상태·기타 항목·입금항목·서류)을 따른다.
'표 편집'을 켜면 표에서 바로 고치고 한 번에 저장한다.
"""
from datetime import date

import pandas as pd
import streamlit as st

import db
import templates
from ui import common as cm
from ui import unit_card

CONTRACT_COLS = {  # 표 열 이름 → contracts 컬럼
    '계약자명': 'customer_name', '생년월일': 'birth_date', '연락처': 'phone', '가계약일': 'pre_date',
    '계약예정일': 'planned_date', '계약일': 'contract_date', '담당팀': 'assigned_team', '담당자': 'assigned_staff',
    '계약금': 'deposit_total', '주소': 'address', '비고1': 'notes', '비고2': 'notes2',
}
DATE_COLS = ('생년월일', '가계약일', '계약예정일', '계약일')


def _price(u, key):
    return (u.get(key) if key in templates.UNIT_COLUMNS else u['extra_d'].get(key)) or 0


def build_frame(units, cfg):
    rows = []
    for u in units:
        ct = u['contract'] or {}
        ex = (ct.get('extra_d') or {}) if ct else {}
        fv, dv = ex.get('fields', {}), ex.get('docs', {})
        r = {'_uid': u['id'], '동': u['building_no'], '호수': u['unit_no'], '타입': u.get('type') or ''}
        for p in cfg['price_fields']:
            r[p['label']] = _price(u, p['key'])
        r['상태'] = u['status']
        for f in cfg['fields']:
            v = fv.get(f['label'])
            r[f['label']] = cm.to_date(v) if f.get('type') == 'date' else (bool(v) if f.get('type') == 'check' else v)
        for col, key in CONTRACT_COLS.items():
            v = ct.get(key)
            r[col] = cm.to_date(v) if col in DATE_COLS else v
        r['입금총액'] = u['paid_in'] - u['paid_out']
        for item in cfg['payment_items']:
            amt, first = u['items'].get(item, (None, None))
            r[item] = amt
            r[f"{item} 납부일"] = cm.to_date(first)
        for d in cfg['docs']:
            r[d] = bool(dv.get(d))
        rows.append(r)
    df = pd.DataFrame(rows)
    for c in DATE_COLS + tuple(f['label'] for f in cfg['fields'] if f.get('type') == 'date') + \
            tuple(f"{i} 납부일" for i in cfg['payment_items']):
        if c in df:
            df[c] = df[c].astype(object)
    return df


def _texts(series):
    return {v for v in series if isinstance(v, str) and v}


def column_config(cfg, employees, editable, df=None):
    statuses = ['공실'] + templates.status_names(cfg)
    if df is not None:   # 표에 이미 있는 값(예: 양식에 없는 상태, 퇴사자 담당자)도 선택지에 포함
        statuses += sorted(_texts(df['상태']) - set(statuses))
    teams = sorted({e['team'] for e in employees if e.get('team')} | (_texts(df['담당팀']) if df is not None else set()))
    staff = sorted({e['name'] for e in employees} | (_texts(df['담당자']) if df is not None else set()))
    conf = {
        '_uid': None,
        '동': st.column_config.TextColumn('동', disabled=True, width=50, pinned=True),
        '호수': st.column_config.TextColumn('호수', disabled=True, width=60, pinned=True),
        '타입': st.column_config.TextColumn('타입', width=55),
        '상태': st.column_config.SelectboxColumn('상태', options=statuses, required=True, width=70),
        '계약자명': st.column_config.TextColumn('계약자명', width=80),
        '생년월일': st.column_config.DateColumn('생년월일', format="YYYY-MM-DD", min_value=date(1920, 1, 1)),
        '가계약일': st.column_config.DateColumn('가계약일', format="YYYY-MM-DD"),
        '계약예정일': st.column_config.DateColumn('계약예정일', format="YYYY-MM-DD"),
        '계약일': st.column_config.DateColumn('계약일', format="YYYY-MM-DD"),
        '담당팀': st.column_config.SelectboxColumn('담당팀', options=teams) if teams else
        st.column_config.TextColumn('담당팀'),
        '담당자': st.column_config.SelectboxColumn('담당자', options=staff) if staff else
        st.column_config.TextColumn('담당자'),
        '계약금': st.column_config.NumberColumn('계약금', format="localized", min_value=0),
        '입금총액': st.column_config.NumberColumn('입금총액', format="localized", disabled=True,
                                              help="입출금 탭의 입금 - 출금 합계"),
    }
    for p in cfg['price_fields']:
        conf[p['label']] = st.column_config.NumberColumn(p['label'], format="localized", min_value=0)
    for f in cfg['fields']:
        t, lab = f.get('type'), f['label']
        if t == 'date':
            conf[lab] = st.column_config.DateColumn(lab, format="YYYY-MM-DD")
        elif t in ('number', 'money'):
            conf[lab] = st.column_config.NumberColumn(lab, format="localized" if t == 'money' else None)
        elif t == 'select':
            opts = list(f.get('options') or [])
            if df is not None and lab in df:
                opts += sorted(_texts(df[lab]) - set(opts))
            conf[lab] = st.column_config.SelectboxColumn(lab, options=opts)
        elif t == 'check':
            conf[lab] = st.column_config.CheckboxColumn(lab)
        else:
            conf[lab] = st.column_config.TextColumn(lab)
    for item in cfg['payment_items']:
        conf[item] = st.column_config.NumberColumn(item, format="localized", disabled=True,
                                                   help="입출금에서 이 입금항목으로 들어온 금액")
        conf[f"{item} 납부일"] = st.column_config.DateColumn(f"{item} 납부일", format="YYYY-MM-DD", disabled=True)
    for d in cfg['docs']:
        conf[d] = st.column_config.CheckboxColumn(d, width=60)
    return conf


def _norm(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, date)):
        return cm.date_str(v)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return v.strip() or None
    return v


def diff_changes(before, after, cfg, units_by_id):
    """편집 전/후 표 비교 → (changes, errors)"""
    changes, errors = [], []
    price_keys = {p['label']: p['key'] for p in cfg['price_fields']}
    contract_cols = list(CONTRACT_COLS) + ['상태'] + [f['label'] for f in cfg['fields']] + list(cfg['docs'])
    b_idx = before.set_index('_uid')
    for _, row in after.iterrows():
        uid = int(row['_uid'])
        old = b_idx.loc[uid]
        diff = [c for c in after.columns if c != '_uid' and _norm(old[c]) != _norm(row[c])]
        if not diff:
            continue
        u = units_by_id[uid]
        label = f"{u['building_no']}동 {u['unit_no']}호"
        ch = {'unit_id': uid}
        unit_vals = {price_keys[c]: int(_norm(row[c]) or 0) for c in diff if c in price_keys}
        if '타입' in diff:
            unit_vals['type'] = _norm(row['타입'])
        if unit_vals:
            ch['unit'] = unit_vals
        if any(c in contract_cols for c in diff):
            status = _norm(row['상태']) or '공실'
            name = _norm(row['계약자명'])
            has_ct = u['contract'] is not None
            if status == '공실':
                errors.append(f"{label}: 상태를 '공실'로 바꾸려면 해지 탭에서 해지 처리하세요." if has_ct
                              else f"{label}: 계약을 등록하려면 상태(가계약·계약 등)를 고르세요.")
                continue
            if not name:
                errors.append(f"{label}: 계약자명이 없습니다.")
                continue
            data = {key: _norm(row[col]) for col, key in CONTRACT_COLS.items()}
            data['deposit_total'] = int(data['deposit_total'] or 0)
            data['contract_type'] = status
            ex = dict((u['contract'] or {}).get('extra_d') or {})
            ex['fields'] = {f['label']: _norm(row[f['label']]) for f in cfg['fields']
                            if _norm(row[f['label']]) not in (None, False)}
            ex['docs'] = {d: True for d in cfg['docs'] if bool(row[d])}
            data['extra'] = ex
            ch['contract'] = data
        changes.append(ch)
    return changes, errors


def render(ctx):
    site_id, cfg, editable = ctx['site_id'], ctx['cfg'], ctx['editable']
    units = db.get_site_sheet(site_id)
    if not units:
        st.info("등록된 호실이 없습니다. 설정 탭 > 호실 등록에서 호실 목록을 올리세요.")
        return
    employees = db.get_employees(site_id)
    df_all = build_frame(units, cfg)

    # ── 필터 ──
    f = st.columns([1, 1.6, 1, 1, 2, 1.1])
    blds = ["전체"] + sorted(df_all['동'].unique(), key=lambda x: (len(str(x)), str(x)))
    bf = f[0].selectbox("동", blds, key=f"ct_b_{site_id}")
    sf = f[1].multiselect("상태", ['공실'] + templates.status_names(cfg), key=f"ct_s_{site_id}",
                          placeholder="전체")
    tf = f[2].selectbox("타입", ["전체"] + sorted({t for t in df_all['타입'] if isinstance(t, str) and t}),
                        key=f"ct_t_{site_id}")
    teams = ["전체"] + sorted({t for t in df_all['담당팀'] if isinstance(t, str) and t})
    mf = f[3].selectbox("담당팀", teams, key=f"ct_m_{site_id}")
    kw = f[4].text_input("검색", placeholder="호수·계약자·연락처·담당자·비고", key=f"ct_q_{site_id}")
    edit_mode = f[5].toggle("표 편집", key=f"ct_edit_{site_id}", disabled=not editable,
                            help=None if editable else "열람 권한은 편집할 수 없습니다.")

    df = df_all
    if bf != "전체":
        df = df[df['동'] == bf]
    if sf:
        df = df[df['상태'].isin(sf)]
    if tf != "전체":
        df = df[df['타입'] == tf]
    if mf != "전체":
        df = df[df['담당팀'] == mf]
    if kw.strip():
        k = kw.strip()
        mask = pd.Series(False, index=df.index)
        for col in ('호수', '계약자명', '연락처', '담당자', '비고1', '비고2', '주소'):
            mask |= df[col].astype(str).str.contains(k, na=False, regex=False)
        df = df[mask]

    statuses = templates.status_names(cfg)
    st.caption(f"{len(df):,}개 호실 표시 / 전체 {len(df_all):,}개 · "
               + " · ".join(f"{s} {int((df['상태'] == s).sum())}" for s in ['공실'] + statuses)
               + f" · 입금총액 {int(df['입금총액'].sum()):,}원")

    conf = column_config(cfg, employees, editable, df_all)
    if edit_mode:
        st.info("표에서 바로 고친 뒤 [변경 저장]을 누르세요. 상태·계약자명을 입력하면 신규 계약이 등록됩니다. "
                "해지는 해지 탭에서 처리합니다. 회색 열(입금 집계)은 입출금 탭에서 바뀝니다.")
        edited = st.data_editor(df, column_config=conf, hide_index=True, placeholder="", width="stretch", height=560,
                                key=f"ct_editor_{site_id}_{bf}_{tf}_{mf}_{'-'.join(sf)}_{kw}", num_rows="fixed")
        changes, errors = diff_changes(df, edited, cfg, {u['id']: u for u in units})
        b1, b2 = st.columns([1, 5])
        if b1.button(f"변경 저장 ({len(changes)})", type="primary", disabled=not changes or bool(errors),
                     icon=":material/save:"):
            try:
                n_new, n_upd, n_unit = db.apply_sheet_changes(site_id, changes)
            except ValueError as e:
                st.error(str(e))
            else:
                cm.flash(f"저장 완료 — 신규 계약 {n_new} · 계약 수정 {n_upd} · 호실정보 {n_unit}")
                st.rerun()
        for e in errors:
            b2.error(e)
    else:
        event = st.dataframe(df, column_config=conf, hide_index=True, placeholder="", width="stretch", height=560,
                             on_select="rerun", selection_mode="single-row", key=f"ct_view_{site_id}")
        rows = event.selection.rows if hasattr(event, 'selection') else []
        if rows:
            uid = int(df.iloc[rows[0]]['_uid'])
            if st.session_state.get(unit_card.STATE_KEY) != uid:
                unit_card.open_card(uid)
        st.download_button("엑셀 다운로드", icon=":material/download:",
                           data=cm.excel_bytes({'계약관리': df.drop(columns=['_uid'])}),
                           file_name=f"{ctx['site']['name']}_계약관리_{date.today():%y%m%d}.xlsx", mime=cm.XLSX_MIME)
        sel = st.session_state.get(unit_card.STATE_KEY)
        if sel:
            unit_card.render(ctx, sel)
        else:
            st.caption("행을 클릭하면 아래에 호실 카드(계약정보·납부현황·입출금·이력)가 열립니다.")
