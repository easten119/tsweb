import streamlit as st
import pandas as pd
import db
import sidebar

st.set_page_config(page_title="사용자 관리", page_icon="🔑", layout="wide")

sidebar.require_login()

user = st.session_state.user

if user['role'] != 'admin':
    st.error("관리자(admin)만 접근할 수 있는 페이지입니다.")
    st.stop()

sidebar.render_sidebar(user)

st.title("🔑 사용자 관리")

users = db.get_all_users()
sites = db.get_all_sites()
site_name_to_id = {s['name']: s['id'] for s in sites}
site_names = [s['name'] for s in sites]

ROLE_KO = {'admin': '관리자', 'manager': '현장담당자', 'viewer': '뷰어'}

if users:
    df = pd.DataFrame(users)[['username', 'role', 'site_name', 'created_at']]
    df.columns = ['아이디', '권한', '담당 현장', '생성일시']
    df['권한'] = df['권한'].map(lambda x: ROLE_KO.get(x, x))
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("등록된 사용자가 없습니다.")

st.markdown("---")
tab_add, tab_pw, tab_role, tab_del = st.tabs(["➕ 사용자 추가", "🔒 비밀번호 변경", "✏️ 권한 변경", "🗑️ 삭제"])

with tab_add:
    with st.form("form_add_user", clear_on_submit=True):
        col1, col2 = st.columns(2)
        new_username = col1.text_input("아이디 *")
        new_password = col2.text_input("비밀번호 *", type="password")
        col3, col4 = st.columns(2)
        role = col3.selectbox("권한", ['manager', 'viewer', 'admin'])
        sel_sites = col4.multiselect("담당 현장", site_names)
        if st.form_submit_button("추가", type="primary"):
            if not new_username.strip() or not new_password:
                st.error("아이디와 비밀번호를 입력하세요.")
            elif role == 'manager' and not sel_sites:
                st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
            else:
                site_id_list = [site_name_to_id[n] for n in sel_sites]
                ok, result = db.add_user(new_username.strip(), new_password, role, site_id_list)
                if ok:
                    st.success(f"사용자 '{new_username}' 추가 완료.")
                    st.rerun()
                else:
                    st.error(result)

with tab_pw:
    user_map = {u['username']: u['id'] for u in users}
    sel_user = st.selectbox("사용자 선택", list(user_map.keys()), key="pw_sel")
    with st.form("form_change_pw"):
        pw1 = st.text_input("새 비밀번호 *", type="password")
        pw2 = st.text_input("비밀번호 확인 *", type="password")
        if st.form_submit_button("변경", type="primary"):
            if not pw1:
                st.error("새 비밀번호를 입력하세요.")
            elif pw1 != pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                db.update_user_password(user_map[sel_user], pw1)
                st.success("비밀번호가 변경되었습니다.")

with tab_role:
    user_map2 = {u['username']: u for u in users}
    sel_user2 = st.selectbox("사용자 선택", list(user_map2.keys()), key="role_sel")
    u_info = user_map2[sel_user2]
    ROLE_OPTIONS = ['admin', 'manager', 'viewer']

    # 현재 배정된 현장 ID 목록 파싱
    site_ids_str = u_info.get('site_ids_str') or ''
    cur_site_ids = {int(x) for x in site_ids_str.split(',') if x.strip()}
    cur_site_names = [s['name'] for s in sites if s['id'] in cur_site_ids]

    with st.form("form_change_role"):
        col1, col2 = st.columns(2)
        cur_role_idx = ROLE_OPTIONS.index(u_info['role']) if u_info['role'] in ROLE_OPTIONS else 0
        new_role = col1.selectbox("권한", ROLE_OPTIONS, index=cur_role_idx)
        new_site_names = col2.multiselect("담당 현장", site_names, default=cur_site_names)
        if st.form_submit_button("저장", type="primary"):
            if new_role == 'manager' and not new_site_names:
                st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
            else:
                new_site_ids = [site_name_to_id[n] for n in new_site_names]
                db.update_user(u_info['id'], new_role, new_site_ids)
                st.success("변경되었습니다.")
                st.rerun()

with tab_del:
    deletable = [u for u in users if u['username'] != 'admin']
    if not deletable:
        st.info("삭제 가능한 사용자가 없습니다. (admin 계정은 삭제 불가)")
    else:
        del_map = {u['username']: u['id'] for u in deletable}
        sel_del = st.selectbox("삭제할 사용자", list(del_map.keys()), key="del_sel")
        st.warning(f"'{sel_del}' 계정을 삭제합니다. 이 작업은 되돌릴 수 없습니다.")
        if st.button("삭제 확인", type="primary"):
            db.delete_user(del_map[sel_del])
            st.success("삭제되었습니다.")
            st.rerun()
