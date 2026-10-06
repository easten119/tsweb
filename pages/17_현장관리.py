import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar
import board

user = sidebar.page_setup("현장 관리", "📍", roles=('admin',))
sidebar.show_flash()

sites = db.get_all_sites()
if sites:
    df = pd.DataFrame([{
        'ID': s['id'], '현장명': s['name'], '지역': s['region'], '시작일': s['start_date'], '상태': s['status'],
        '재직 인원': s['employee_count'], '일비 단가': s.get('daily_allowance'),
        '해당지역 숙소비': s.get('housing_local'), '타지역 숙소비': s.get('housing_other'),
    } for s in sites])
    st.dataframe(df.style.map(lambda v: 'color: green' if v == '진행중' else 'color: gray', subset=['상태']),
                 width="stretch", hide_index=True,
                 column_config={c: st.column_config.NumberColumn(format="localized")
                                for c in ('일비 단가', '해당지역 숙소비', '타지역 숙소비')})
else:
    st.info("등록된 현장이 없습니다.")

st.markdown("---")
tab_add, tab_edit, tab_del, tab_upload, tab_floor = st.tabs(
    ["➕ 현장 추가", "✏️ 현장 수정", "🗑️ 현장 삭제", "📤 호실 일괄 업로드", "🏢 층 표시 설정"])

with tab_add:
    with st.form("form_add_site", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("현장명 *")
        region = c2.text_input("지역 *")
        c3, c4 = st.columns(2)
        start_date = c3.date_input("시작일", value=date.today())
        status = c4.selectbox("상태", ['진행중', '완료'])
        c5, c6, c7 = st.columns(3)
        daily_allowance = c5.number_input("일비 단가 (원)", value=10000, step=1000, min_value=0)
        housing_local = c6.number_input("해당지역 숙소비 (원)", value=200000, step=10000, min_value=0)
        housing_other = c7.number_input("타지역 숙소비 (원)", value=300000, step=10000, min_value=0)
        if st.form_submit_button("추가", type="primary"):
            if not name.strip() or not region.strip():
                st.error("현장명과 지역을 입력하세요.")
            elif db.site_name_exists(name.strip()):
                st.error("같은 이름의 현장이 이미 있습니다. (엑셀 업로드가 현장명으로 구분하므로 중복 불가)")
            else:
                db.add_site(name.strip(), region.strip(), str(start_date), status,
                            int(daily_allowance), int(housing_local), int(housing_other))
                sidebar.flash(f"현장 '{name.strip()}' 추가 완료.")
                st.rerun()

with tab_edit:
    if not sites:
        st.info("수정할 현장이 없습니다.")
    else:
        by_id = {s['id']: s for s in sites}
        sid = st.selectbox("수정할 현장 선택", list(by_id), key="edit_sel", format_func=lambda i: by_id[i]['name'])
        site = db.get_site(sid)
        with st.form(f"form_edit_site_{sid}"):
            c1, c2 = st.columns(2)
            name = c1.text_input("현장명 *", value=site['name'])
            region = c2.text_input("지역 *", value=site['region'])
            c3, c4 = st.columns(2)
            sd = date.fromisoformat(site['start_date']) if site.get('start_date') else date.today()
            start_date = c3.date_input("시작일", value=sd)
            status = c4.selectbox("상태", ['진행중', '완료'], index=0 if site['status'] == '진행중' else 1)
            c5, c6, c7 = st.columns(3)
            daily_allowance = c5.number_input("일비 단가 (원)", value=int(site.get('daily_allowance') or 10000), step=1000, min_value=0)
            housing_local = c6.number_input("해당지역 숙소비 (원)", value=int(site.get('housing_local') or 200000), step=10000, min_value=0)
            housing_other = c7.number_input("타지역 숙소비 (원)", value=int(site.get('housing_other') or 300000), step=10000, min_value=0)
            st.caption("단가를 바꾸면 이후 계산부터 적용됩니다. 이미 저장된 정산 이력 금액은 바뀌지 않습니다.")
            if st.form_submit_button("수정 저장", type="primary"):
                if not name.strip() or not region.strip():
                    st.error("현장명과 지역을 입력하세요.")
                elif db.site_name_exists(name.strip(), exclude_id=sid):
                    st.error("같은 이름의 현장이 이미 있습니다.")
                else:
                    db.update_site(sid, name.strip(), region.strip(), str(start_date), status,
                                   int(daily_allowance), int(housing_local), int(housing_other))
                    sidebar.flash("수정 완료.")
                    st.rerun()

with tab_del:
    if not sites:
        st.info("삭제할 현장이 없습니다.")
    else:
        by_id = {s['id']: s for s in sites}
        sid = st.selectbox("삭제할 현장 선택", list(by_id), key="del_sel", format_func=lambda i: by_id[i]['name'])
        st.warning("직원·호실·입출금·정산 이력이 하나도 없는 현장만 삭제됩니다. 운영이 끝난 현장은 '완료'로 바꾸세요.")
        ok = st.checkbox(f"'{by_id[sid]['name']}' 현장을 삭제합니다.", key=f"del_site_chk_{sid}")
        if st.button("삭제 확인", type="primary", disabled=not ok):
            success, msg = db.delete_site(sid)
            sidebar.flash(msg, "success" if success else "error")
            st.rerun()

COLS = ["단지번호", "단지명", "동", "호수", "타입", "층", "라인", "분양가", "계약금"]

with tab_upload:
    st.markdown("##### 호실 일괄 업로드")
    st.caption("엑셀 첫 행은 헤더, 열 순서 고정: " + " | ".join(COLS) + "  \n같은 단지·동·호수는 정보만 갱신되고 계약 상태는 유지됩니다.")
    template = pd.DataFrame([[1, '1단지', '101', '1501', '84A', 15, '1', 500000000, 50000000]], columns=COLS)
    st.download_button("📄 빈 업로드 양식 받기", data=sidebar.excel_bytes({'호실목록': template}),
                       file_name="호실_업로드양식.xlsx", mime=sidebar.XLSX_MIME)
    if not sites:
        st.info("현장을 먼저 추가하세요.")
    else:
        by_id = {s['id']: s for s in sites}
        up_sid = st.selectbox("현장 선택", list(by_id), key="upload_site", format_func=lambda i: by_id[i]['name'])
        uploaded = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"], key="unit_upload")
        if uploaded is not None:
            try:
                df_up = pd.read_excel(uploaded, header=0, dtype=object)
            except Exception as e:
                st.error(f"파일 읽기 오류: {e}")
                st.stop()
            if len(df_up.columns) < 4:
                st.error("열이 부족합니다. 최소 단지번호·단지명·동·호수가 필요합니다.")
                st.stop()
            df_up = df_up.iloc[:, :len(COLS)]
            df_up.columns = COLS[:len(df_up.columns)]
            for c in COLS:
                if c not in df_up.columns:
                    df_up[c] = None
            df_up = df_up.dropna(how='all')

            rows, errors = [], []
            for i, r in df_up.iterrows():
                if db._clean_int(r['단지번호']) is None or not db._clean_text(r['동']) or not db._clean_text(r['호수']):
                    errors.append(f"{i + 2}행: 단지번호·동·호수 중 빈 값 → 제외")
                    continue
                rows.append({"complex_no": r['단지번호'], "complex_name": r['단지명'], "building_no": r['동'],
                             "unit_no": r['호수'], "type_": r['타입'], "floor": r['층'], "line": r['라인'],
                             "sale_price": r['분양가'], "rental_price": r['계약금']})
            preview = pd.DataFrame([{
                '단지': db._clean_text(x['complex_name']), '동': db._clean_text(x['building_no']),
                '호수': db._clean_text(x['unit_no']), '타입': db._clean_text(x['type_']),
                '층': db._clean_int(x['floor']), '분양가': db._clean_int(x['sale_price'], 0),
                '계약금': db._clean_int(x['rental_price'], 0)} for x in rows])
            st.markdown(f"**미리보기** — 유효 {len(rows)}행 / 제외 {len(errors)}행")
            st.dataframe(preview.head(20), width="stretch", hide_index=True)
            bad_no = [x for x in preview['호수'] if not (str(x).isdigit() and len(str(x)) >= 3)] if not preview.empty else []
            if bad_no:
                st.warning(f"현황판에 표시되지 않을 호수 형식 {len(bad_no)}개 (예: {bad_no[:5]}) — '4601'처럼 층+라인 숫자여야 합니다.")
            if errors:
                with st.expander(f"제외된 행 {len(errors)}건"):
                    for e in errors:
                        st.write(e)
            if rows and st.button("✅ 업로드 반영", type="primary", key="do_upload"):
                try:
                    n_c, n_b, n_new, n_upd = db.bulk_upload_units(up_sid, rows)
                except Exception as e:
                    st.error(f"업로드 실패 (아무것도 반영되지 않음): {e}")
                else:
                    st.session_state.pop('unit_upload', None)
                    sidebar.flash(f"단지 {n_c}개 · 동 {n_b}개 · 신규 호실 {n_new}개 · 갱신 {n_upd}개 반영 완료")
                    st.rerun()

with tab_floor:
    st.markdown("##### 현황판 층 표시 설정")
    st.caption("호실이 없는 층에 이름을 붙여 현황판에 표시합니다 (예: 1~2층 근린생활시설, 3층 비주거 주차장, 4층 옥상정원). "
               "최상층보다 높은 층 번호(예: 47층)를 넣으면 맨 위에 '스카이라운지'처럼 표시됩니다. "
               "이름이 없는 빈 층은 ✕(피난층 등)로 표시됩니다.")
    if not sites:
        st.info("현장을 먼저 추가하세요.")
    else:
        by_id = {s['id']: s for s in sites}
        fl_sid = st.selectbox("현장", list(by_id), key="fl_site", format_func=lambda i: by_id[i]['name'])
        blds = db.get_buildings(site_id=fl_sid)
        if not blds:
            st.info("이 현장에 등록된 동이 없습니다.")
        else:
            multi = len({b['complex_id'] for b in blds}) > 1
            bmap = {b['id']: b for b in blds}
            fl_bid = st.selectbox("기준 동", list(bmap), key="fl_bld",
                                  format_func=lambda i: sidebar.building_label(bmap[i], multi))
            cur = db.get_floor_labels(fl_sid).get(fl_bid, {})
            bunits = db.get_units(site_id=fl_sid, building_id=fl_bid)
            floors = {board.parse_unit_no(u['unit_no'])[0] for u in bunits} - {None}
            if floors:
                empty = [f for f in range(1, max(floors) + 1) if f not in floors]
                st.caption(f"이 동의 호실 층: {min(floors)}~{max(floors)}층 · 호실 없는 층: "
                           + (", ".join(f"{f}층" for f in empty) if empty else "없음"))
            df = pd.DataFrame([{'층': f, '표시 이름': l} for f, l in sorted(cur.items(), reverse=True)],
                              columns=['층', '표시 이름'])
            edited = st.data_editor(
                df, num_rows="dynamic", width="content", hide_index=True, key=f"fl_editor_{fl_bid}",
                column_config={'층': st.column_config.NumberColumn('층', min_value=1, max_value=200, step=1, format="%d"),
                               '표시 이름': st.column_config.TextColumn('표시 이름', width="medium")})
            apply_all = st.checkbox("이 현장의 모든 동에 똑같이 적용", value=False, key="fl_all")
            if st.button("💾 층 표시 저장", type="primary"):
                new = {}
                for _, r in edited.iterrows():
                    if pd.notna(r['층']) and str(r['표시 이름'] or '').strip():
                        new[int(r['층'])] = str(r['표시 이름']).strip()
                targets = list(bmap) if apply_all else [fl_bid]
                for bid in targets:
                    db.save_floor_labels(bid, new)
                sidebar.flash(f"{len(targets)}개 동에 층 표시 {len(new)}개 저장")
                st.rerun()
