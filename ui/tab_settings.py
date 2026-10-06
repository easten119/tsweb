"""설정 탭 — 기본정보·단가 · 계약 양식 · 현황판 표시 · 호실 등록 · 엑셀 가져오기 (쓰기는 관리자)"""
import io
import re
from datetime import date

import pandas as pd
import streamlit as st

import board
import db
import importer
import templates
from ui import common as cm


def render(ctx):
    sub = st.segmented_control("설정", ["기본정보", "계약 양식", "현황판 표시", "호실 등록", "엑셀 가져오기"],
                               default="기본정보", key=f"set_sub_{ctx['site_id']}", label_visibility="collapsed")
    admin = cm.is_admin(ctx['user'])
    if not admin:
        st.caption("설정 변경은 관리자만 할 수 있습니다. (보기 전용)")
    {"계약 양식": _template, "현황판 표시": _board_display, "호실 등록": _units,
     "엑셀 가져오기": _import}.get(sub, _basic)(ctx, admin)


# ── 기본정보 ──────────────────────────────────────────────────────
def _basic(ctx, admin):
    site = db.get_site(ctx['site_id'])
    with st.form("set_basic"):
        r = st.columns(4)
        name = r[0].text_input("현장명", value=site['name'], disabled=not admin)
        region = r[1].text_input("지역", value=site['region'], disabled=not admin)
        start = r[2].date_input("시작일", value=cm.to_date(site.get('start_date')) or date.today(), disabled=not admin,
                                format="YYYY-MM-DD")
        status = r[3].selectbox("상태", ['진행중', '완료'], index=0 if site['status'] == '진행중' else 1,
                                disabled=not admin)
        r = st.columns(4)
        da = r[0].number_input("일비 단가", value=int(site.get('daily_allowance') or 10000), step=1000, min_value=0,
                               disabled=not admin)
        hl = r[1].number_input("숙소비 (해당지역)", value=int(site.get('housing_local') or 200000), step=10000,
                               min_value=0, disabled=not admin)
        ho = r[2].number_input("숙소비 (타지역)", value=int(site.get('housing_other') or 300000), step=10000,
                               min_value=0, disabled=not admin)
        st.caption("단가 변경은 이후 계산부터 적용되며, 이미 저장된 정산 이력 금액은 바뀌지 않습니다. "
                   "현장이 끝나면 상태를 '완료'로 바꾸세요 (대시보드 지표에서 빠집니다).")
        if st.form_submit_button("저장", type="primary", disabled=not admin):
            if not name.strip() or not region.strip():
                st.error("현장명과 지역을 입력하세요.")
            elif db.site_name_exists(name.strip(), exclude_id=site['id']):
                st.error("같은 이름의 현장이 이미 있습니다.")
            else:
                db.update_site(site['id'], name.strip(), region.strip(), str(start), status, int(da), int(hl), int(ho))
                cm.flash("저장 완료")
                st.rerun()


# ── 계약 양식 ─────────────────────────────────────────────────────
def _list_editor(title, values, key, disabled, help_text=None):
    cm.section(title, help_text)
    df = pd.DataFrame({'항목': values or []}, dtype=object)
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, placeholder="", width=420, key=key, disabled=disabled,
                        column_config={'항목': st.column_config.TextColumn('항목', width=360)})
    return [str(v).strip() for v in ed['항목'] if isinstance(v, str) and v.strip()]


def _template(ctx, admin):
    site, cfg = ctx['site'], ctx['cfg']
    dis = not admin
    st.caption("이 현장의 계약관리 표·현황판·입출금 항목이 이 양식을 따릅니다. "
               "항목 이름을 바꾸면 기존에 입력된 값은 새 이름으로 옮겨지지 않으니 주의하세요.")
    c = st.columns([2, 1, 3])
    preset = c[0].selectbox("프리셋", list(templates.PRESETS), key="tp_preset",
                            index=list(templates.PRESETS).index(site.get('template'))
                            if site.get('template') in templates.PRESETS else 0,
                            format_func=lambda k: templates.PRESETS[k]['label'], disabled=dis)
    with c[1].popover("프리셋으로 초기화", disabled=dis):
        st.caption("아래 항목을 모두 선택한 프리셋 기본값으로 바꿉니다.")
        if st.button("초기화", type="primary", key="tp_reset"):
            db.update_site_config(site['id'], preset, templates.dump_config(templates.preset_config(preset)))
            cm.flash("프리셋으로 초기화했습니다.")
            st.rerun()

    cm.section("호실 가격 항목", "계약관리 표와 호실 등록 양식의 가격 열")
    pdf = pd.DataFrame([{'항목명': p['label'], '저장키': p['key']} for p in cfg['price_fields']], dtype=object)
    ped = st.data_editor(pdf, num_rows="dynamic", hide_index=True, placeholder="", width=420, key="tp_price", disabled=dis,
                         column_config={'저장키': st.column_config.TextColumn('저장키', disabled=True,
                                                                           help="자동 지정 (데이터 연결용)")})
    cm.section("상태와 현황판 색", "공실은 기본 포함. 색은 #RRGGBB")
    sdf = pd.DataFrame([{'상태': s['name'], '색상': s.get('color')} for s in cfg['statuses']], dtype=object)
    sed = st.data_editor(sdf, num_rows="dynamic", hide_index=True, placeholder="", width=420, key="tp_status", disabled=dis)
    items = _list_editor("입금항목 (납부 항목)", cfg['payment_items'], "tp_items", dis,
                         "입출금에서 고르는 항목 — 계약관리 표에 항목별 납부액·납부일로 집계")
    docs = _list_editor("서류 체크", cfg['docs'], "tp_docs", dis)
    cm.section("기타 항목", "형식: 글자 / 날짜 / 숫자 / 금액 / 선택 / 체크 — 선택은 선택지를 쉼표로")
    fdf = pd.DataFrame([{'항목명': f['label'], '형식': templates.FIELD_TYPES.get(f.get('type', 'text'), '글자'),
                         '선택지': ", ".join(f.get('options') or [])} for f in cfg['fields']], dtype=object)
    fed = st.data_editor(fdf, num_rows="dynamic", hide_index=True, placeholder="", width=620, key="tp_fields", disabled=dis,
                         column_config={'형식': st.column_config.SelectboxColumn(
                             '형식', options=list(templates.FIELD_TYPES.values()), required=True)})

    if st.button("양식 저장", type="primary", disabled=dis, icon=":material/save:"):
        price_fields, used = [], set()
        for _, r in ped.iterrows():
            label = str(r['항목명'] or '').strip()
            if not label:
                continue
            key = r['저장키'] if isinstance(r['저장키'], str) and r['저장키'] else None
            if not key:
                key = next((k for k in templates.UNIT_COLUMNS if k not in used and
                            k not in {p['key'] for p in cfg['price_fields']}), None) or f"price_{len(used) + 1}"
                while key in used:
                    key += "_"
            used.add(key)
            price_fields.append({'key': key, 'label': label})
        statuses = []
        for i, r in sed.iterrows():
            name = str(r['상태'] or '').strip()
            if not name or name == '공실':
                continue
            color = str(r['색상'] or '').strip()
            if not re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
                color = templates.STATUS_PALETTE[i % len(templates.STATUS_PALETTE)]
            statuses.append({'name': name, 'color': color})
        rev = {v: k for k, v in templates.FIELD_TYPES.items()}
        fields = []
        for _, r in fed.iterrows():
            label = str(r['항목명'] or '').strip()
            if not label:
                continue
            f = {'label': label, 'type': rev.get(r['형식'], 'text')}
            if f['type'] == 'select':
                f['options'] = [o.strip() for o in str(r['선택지'] or '').split(',') if o.strip()]
            fields.append(f)
        if not statuses:
            st.error("상태를 하나 이상 입력하세요.")
        else:
            new = dict(cfg, price_fields=price_fields, statuses=statuses, payment_items=items, docs=docs, fields=fields)
            db.update_site_config(site['id'], preset, templates.dump_config(new))
            cm.flash("계약 양식 저장 완료")
            st.rerun()


# ── 현황판 표시 ───────────────────────────────────────────────────
def _board_display(ctx, admin):
    site_id, cfg = ctx['site_id'], ctx['cfg']
    blds = db.get_buildings(site_id=site_id)
    if not blds:
        st.info("등록된 동이 없습니다.")
        return
    cm.section("특수층 이름", "호실 없는 층에 이름 표시 (예: 1~2층 근린생활시설, 4층 옥상정원). 최상층보다 높은 층 번호는 "
               "맨 위(스카이라운지 등)에 표시. 이름 없는 빈 층은 ✕(피난층 등).")
    multi = len({b['complex_id'] for b in blds}) > 1
    bmap = {b['id']: b for b in blds}
    bid = st.selectbox("기준 동", list(bmap), key="bd_lbl_b", format_func=lambda i: cm.building_label(bmap[i], multi))
    cur = db.get_floor_labels(site_id).get(bid, {})
    floors = {board.parse_unit_no(u['unit_no'])[0] for u in db.get_units(site_id=site_id, building_id=bid)} - {None}
    if floors:
        empty = [f for f in range(1, max(floors) + 1) if f not in floors]
        st.caption(f"호실 층 {min(floors)}~{max(floors)}층 · 호실 없는 층: " + (", ".join(map(str, empty)) or "없음"))
    ldf = pd.DataFrame([{'층': f, '표시 이름': l} for f, l in sorted(cur.items(), reverse=True)], columns=['층', '표시 이름'])
    led = st.data_editor(ldf, num_rows="dynamic", hide_index=True, placeholder="", width=360, key=f"bd_lbl_{bid}", disabled=not admin,
                         column_config={'층': st.column_config.NumberColumn('층', min_value=1, max_value=200, format="%d")})
    all_b = st.checkbox("이 현장의 모든 동에 똑같이 적용", key="bd_lbl_all", disabled=not admin)

    cm.section("층 구간 (현황판 좌측)", "지역주택조합의 1군~8군처럼 층 범위에 이름 표시 — 비워두면 표시 안 함")
    gdf = pd.DataFrame(cfg.get('floor_groups') or [], columns=['from', 'to', 'label']).rename(
        columns={'from': '시작층', 'to': '끝층', 'label': '이름'})
    ged = st.data_editor(gdf, num_rows="dynamic", hide_index=True, placeholder="", width=360, key="bd_grp", disabled=not admin,
                         column_config={'시작층': st.column_config.NumberColumn(format="%d", min_value=1),
                                        '끝층': st.column_config.NumberColumn(format="%d", min_value=1)})
    if st.button("현황판 표시 저장", type="primary", disabled=not admin, icon=":material/save:"):
        labels = {int(r['층']): str(r['표시 이름']).strip() for _, r in led.iterrows()
                  if pd.notna(r['층']) and str(r['표시 이름'] or '').strip()}
        for b in (bmap if all_b else [bid]):
            db.save_floor_labels(b, labels)
        groups = [{'from': int(r['시작층']), 'to': int(r['끝층']), 'label': str(r['이름']).strip()}
                  for _, r in ged.iterrows()
                  if pd.notna(r['시작층']) and pd.notna(r['끝층']) and str(r['이름'] or '').strip()]
        db.update_site_config(site_id, ctx['site'].get('template'), templates.dump_config(dict(cfg, floor_groups=groups)))
        cm.flash("현황판 표시 저장 완료")
        st.rerun()


# ── 호실 등록 ─────────────────────────────────────────────────────
def _units(ctx, admin):
    site_id, cfg = ctx['site_id'], ctx['cfg']
    base = ["단지번호", "단지명", "동", "호수", "타입", "층", "라인"]
    prices = [p['label'] for p in cfg['price_fields']]
    st.caption("첫 행은 헤더. 열: " + " | ".join(base + prices) + " — 같은 동·호수는 정보만 갱신되고 계약은 유지됩니다. "
               "기존 엑셀 계약현황 전체를 옮기려면 '엑셀 가져오기'를 쓰세요.")
    tmpl = pd.DataFrame([[1, '1단지', '101', '1501', '84A', 15, '1'] + [0] * len(prices)], columns=base + prices)
    st.download_button("빈 양식", data=cm.excel_bytes({'호실목록': tmpl}), icon=":material/description:",
                       file_name="호실_등록양식.xlsx", mime=cm.XLSX_MIME)
    if not admin:
        return
    f = st.file_uploader("호실 목록 (.xlsx)", type=["xlsx"], key="un_up")
    if not f:
        return
    df = pd.read_excel(f, header=0, dtype=object).dropna(how='all')
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in ("단지번호", "동", "호수") if c not in df.columns]
    if missing:
        st.error(f"필수 열이 없습니다: {', '.join(missing)}")
        return
    rows, errors = [], []
    for i, r in df.iterrows():
        if db._clean_int(r.get('단지번호')) is None or not db._clean_text(r.get('동')) or not db._clean_text(r.get('호수')):
            errors.append(f"{i + 2}행: 단지번호·동·호수 빈 값")
            continue
        rows.append({"complex_no": r.get('단지번호'), "complex_name": r.get('단지명'), "building_no": r.get('동'),
                     "unit_no": r.get('호수'), "type_": r.get('타입'), "floor": r.get('층'), "line": r.get('라인'),
                     "prices": {p['key']: db._clean_int(r.get(p['label'])) for p in cfg['price_fields']
                                if p['label'] in df.columns}})
    st.caption(f"유효 {len(rows)}행 / 제외 {len(errors)}행")
    st.dataframe(df.head(15), hide_index=True, placeholder="", width="stretch")
    for e in errors[:50]:
        st.error(e)
    if rows and st.button("호실 반영", type="primary"):
        for r in rows:
            r['sale_price'] = r['prices'].get('sale_price')
            r['rental_price'] = r['prices'].get('rental_price')
        try:
            n_c, n_b, n_new, n_upd = db.bulk_upload_units(site_id, rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"반영 실패 (아무것도 저장되지 않음): {e}")
            return
        # 컬럼 외 가격 항목은 extra에 저장
        extra_keys = [p['key'] for p in cfg['price_fields'] if p['key'] not in templates.UNIT_COLUMNS]
        if extra_keys:
            units = {(str(u['building_no']), str(u['unit_no'])): u['id'] for u in db.get_units(site_id=site_id)}
            changes = []
            for r in rows:
                uid = units.get((db._clean_text(r['building_no']), db._clean_text(r['unit_no'])))
                vals = {k: r['prices'][k] for k in extra_keys if r['prices'].get(k) is not None}
                if uid and vals:
                    changes.append({'unit_id': uid, 'unit': vals})
            db.apply_sheet_changes(site_id, changes)
        st.session_state.pop('un_up', None)
        cm.flash(f"단지 {n_c} · 동 {n_b} · 신규 호실 {n_new} · 갱신 {n_upd}")
        st.rerun()


# ── 엑셀 가져오기 ─────────────────────────────────────────────────
def _import(ctx, admin):
    site_id, cfg = ctx['site_id'], ctx['cfg']
    st.caption("기존에 쓰던 계약현황 엑셀(main 시트, 입출금 시트)을 그대로 올리면 호실·계약·납부를 한 번에 옮깁니다. "
               "먼저 '계약 양식'을 현장에 맞게 맞춰 두세요. 같은 파일을 다시 올려도 입출금이 중복되지 않습니다. "
               "주민등록번호 열은 생년월일만 저장합니다.")
    if not admin:
        return
    f = st.file_uploader("계약현황 엑셀 (.xlsx)", type=["xlsx"], key="im_file")
    if not f:
        return
    data = f.getvalue()
    sheets = pd.ExcelFile(io.BytesIO(data)).sheet_names
    c = st.columns(2)
    main_sheet = c[0].selectbox("계약 시트 (호실 1행)", sheets, key="im_sheet",
                                index=next((i for i, s in enumerate(sheets) if s.lower() == 'main'), 0))
    tx_opts = ['(가져오지 않음)'] + sheets
    tx_sheet = c[1].selectbox("입출금 시트", tx_opts, key="im_txsheet",
                              index=next((i for i, s in enumerate(tx_opts) if '입출금' in s), 0))
    df = importer.read_sheet(data, main_sheet)
    auto = importer.auto_map(list(df.columns), cfg)
    sig = (getattr(f, 'file_id', f.name), main_sheet)
    if st.session_state.get('_im_sig') != sig:
        st.session_state['_im_sig'] = sig
        st.session_state.pop('im_map', None)
    cm.section("열 매핑", "자동으로 맞춘 결과입니다. 틀린 곳만 고치세요.")
    mdf = pd.DataFrame([{'엑셀 열': h, '가져올 항목': auto[h],
                         '예시': next((str(v) for v in df[h] if pd.notna(v) and str(v).strip()), '')[:20]}
                        for h in df.columns])
    med = st.data_editor(mdf, hide_index=True, placeholder="", width="stretch", key="im_map", height=360,
                         column_config={'엑셀 열': st.column_config.TextColumn(disabled=True),
                                        '예시': st.column_config.TextColumn(disabled=True),
                                        '가져올 항목': st.column_config.SelectboxColumn(
                                            options=importer.targets(cfg), required=True)})
    mapping = dict(zip(med['엑셀 열'], med['가져올 항목']))
    plan = importer.analyze(df, mapping, cfg, site_id)
    tx_rows = importer.parse_tx_sheet(importer.read_sheet(data, tx_sheet)) if tx_sheet != tx_opts[0] else []
    m = st.columns(5)
    m[0].metric("호실 신규 / 갱신", f"{plan['n_unit_new']} / {plan['n_unit_upd']}")
    m[1].metric("계약 신규 / 갱신", f"{plan['n_ct_new']} / {plan['n_ct_upd']}")
    m[2].metric("main 납부 → 입금", f"{plan['n_pay']}건")
    m[3].metric("입출금 시트", f"{len(tx_rows)}건")
    m[4].metric("확인 필요", f"{len(plan['errors'])}건")
    if plan.get('no_name'):
        st.info(f"상태만 있고 계약자명이 없는 행 {plan['no_name']}건은 계약자 '{importer.NO_NAME}'로 등록됩니다 "
                "(예: 소송 호실). 나중에 계약관리에서 이름을 채우세요.")
    if plan['n_pay'] and tx_rows:
        st.warning("main 시트의 납부 열과 입출금 시트를 둘 다 가져오면 같은 입금이 두 번 잡힐 수 있습니다. "
                   "입출금 시트에 모든 입금이 있다면 매핑에서 '납부액' 열을 '(사용 안 함)'으로 바꾸세요.")
    if plan['errors']:
        with st.expander(f"확인 필요 {len(plan['errors'])}건", expanded=True):
            for e in plan['errors'][:300]:
                st.write("· " + e)
    if plan['units'] and st.button("가져오기 실행", type="primary", icon=":material/upload:"):
        try:
            s = importer.apply(site_id, plan, tx_rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"가져오기 실패 (아무것도 저장되지 않음): {e}")
            return
        st.session_state.pop('im_file', None)
        cm.flash(f"가져오기 완료 — 호실 신규 {s['unit_new']}·갱신 {s['unit_upd']} / 계약 신규 {s['ct_new']}·갱신 "
                 f"{s['ct_upd']} / 납부 {s['pay']} / 입출금 {s['tx']}")
        st.rerun()
