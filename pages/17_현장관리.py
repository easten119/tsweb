import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

st.set_page_config(page_title="현장 관리", page_icon="📍", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📍 현장 관리")

sites = db.get_all_sites()

if sites:
    df = pd.DataFrame(sites)
    for col in ['daily_allowance', 'housing_local', 'housing_other']:
        if col not in df.columns:
            df[col] = None
    df = df[['id', 'name', 'region', 'start_date', 'status', 'employee_count', 'daily_allowance', 'housing_local', 'housing_other']]
    df.columns = ['ID', '현장명', '지역', '시작일', '상태', '재직 인원', '일비 단가', '해당지역 숙소비', '타지역 숙소비']

    def color_status(val):
        return 'color: green' if val == '진행중' else 'color: gray'

    st.dataframe(
        df.style.map(color_status, subset=['상태']).format({
            '일비 단가': lambda v: f"{int(v):,}원" if v is not None else '-',
            '해당지역 숙소비': lambda v: f"{int(v):,}원" if v is not None else '-',
            '타지역 숙소비': lambda v: f"{int(v):,}원" if v is not None else '-',
        }),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("등록된 현장이 없습니다.")

if user['role'] != 'admin':
    st.caption("현장 추가·수정·삭제는 관리자만 가능합니다.")
    st.stop()

st.markdown("---")
tab_add, tab_edit, tab_del, tab_upload = st.tabs(["➕ 현장 추가", "✏️ 현장 수정", "🗑️ 현장 삭제", "📤 호실 일괄 업로드"])

with tab_add:
    with st.form("form_add_site", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("현장명 *")
        region = col2.text_input("지역 *")
        col3, col4 = st.columns(2)
        start_date = col3.date_input("시작일", value=date.today())
        status = col4.selectbox("상태", ['진행중', '완료'])
        col5, col6, col7 = st.columns(3)
        daily_allowance = col5.number_input("일비 단가 (원)", value=10000, step=1000, min_value=0)
        housing_local = col6.number_input("해당지역 숙소비 (원)", value=200000, step=10000, min_value=0)
        housing_other = col7.number_input("타지역 숙소비 (원)", value=300000, step=10000, min_value=0)
        if st.form_submit_button("추가", type="primary"):
            if name.strip() and region.strip():
                db.add_site(name.strip(), region.strip(), str(start_date), status, daily_allowance, housing_local, housing_other)
                st.success(f"현장 '{name}' 추가 완료.")
                st.rerun()
            else:
                st.error("현장명과 지역을 입력하세요.")

with tab_edit:
    if not sites:
        st.info("수정할 현장이 없습니다.")
    else:
        site_map = {s['name']: s['id'] for s in sites}
        selected = st.selectbox("수정할 현장 선택", list(site_map.keys()), key="edit_sel")
        site = db.get_site(site_map[selected])
        with st.form("form_edit_site"):
            col1, col2 = st.columns(2)
            name = col1.text_input("현장명 *", value=site['name'])
            region = col2.text_input("지역 *", value=site['region'])
            col3, col4 = st.columns(2)
            sd = date.fromisoformat(site['start_date']) if site.get('start_date') else date.today()
            start_date = col3.date_input("시작일", value=sd)
            status_idx = 0 if site['status'] == '진행중' else 1
            status = col4.selectbox("상태", ['진행중', '완료'], index=status_idx)
            col5, col6, col7 = st.columns(3)
            daily_allowance = col5.number_input("일비 단가 (원)", value=int(site.get('daily_allowance') or 10000), step=1000, min_value=0)
            housing_local = col6.number_input("해당지역 숙소비 (원)", value=int(site.get('housing_local') or 200000), step=10000, min_value=0)
            housing_other = col7.number_input("타지역 숙소비 (원)", value=int(site.get('housing_other') or 300000), step=10000, min_value=0)
            if st.form_submit_button("수정 저장", type="primary"):
                if name.strip() and region.strip():
                    db.update_site(site['id'], name.strip(), region.strip(), str(start_date), status, daily_allowance, housing_local, housing_other)
                    st.success("수정 완료.")
                    st.rerun()
                else:
                    st.error("현장명과 지역을 입력하세요.")

with tab_del:
    if not sites:
        st.info("삭제할 현장이 없습니다.")
    else:
        site_map2 = {s['name']: s['id'] for s in sites}
        selected2 = st.selectbox("삭제할 현장 선택", list(site_map2.keys()), key="del_sel")
        st.warning(f"'{selected2}' 현장을 삭제합니다. 직원이 없는 현장만 삭제 가능합니다.")
        if st.button("삭제 확인", type="primary"):
            ok, msg = db.delete_site(site_map2[selected2])
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

with tab_upload:
    st.markdown("### 호실 일괄 업로드")
    st.caption("엑셀 컬럼 순서 (고정): 단지번호 | 단지명 | 동 | 호수 | 타입 | 층 | 라인 | 분양가 | 계약금")

    if not sites:
        st.info("현장을 먼저 추가하세요.")
    else:
        site_map_up = {s['name']: s['id'] for s in sites}
        sel_site_up = st.selectbox("현장 선택", list(site_map_up.keys()), key="upload_site")
        site_id_up = site_map_up[sel_site_up]
        uploaded = st.file_uploader("엑셀 파일 업로드 (.xlsx / .xls)", type=["xlsx", "xls"], key="unit_upload")

        if uploaded is not None:
            try:
                import pandas as pd
                df_up = pd.read_excel(uploaded, header=0)
                col_names = ["단지번호", "단지명", "동", "호수", "타입", "층", "라인", "분양가", "계약금"]
                df_up.columns = col_names[:len(df_up.columns)]
                st.dataframe(df_up.head(10), use_container_width=True)

                if st.button("업로드 처리", type="primary", key="do_upload"):
                    rows = []
                    for _, r in df_up.iterrows():
                        rows.append({
                            "complex_no": r["단지번호"], "complex_name": str(r["단지명"]),
                            "building_no": str(r["동"]), "unit_no": str(r["호수"]),
                            "type_": str(r.get("타입") or ""), "floor": r.get("층"),
                            "line": str(r.get("라인") or ""),
                            "sale_price": r.get("분양가", 0), "rental_price": r.get("계약금", 0),
                        })
                    n_c, n_b, n_u = db.bulk_upload_units(site_id_up, rows)
                    st.success(f"단지 {n_c}개, 동 {n_b}개, 호실 {n_u}개 등록 완료")
            except Exception as e:
                st.error(f"파일 처리 오류: {e}")
