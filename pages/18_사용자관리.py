import streamlit as st
import pandas as pd
import db
import sidebar

user = sidebar.page_setup("사용자 관리", "🔑", roles=('admin',))
sidebar.show_flash()

users = db.get_all_users()
sites = db.get_all_sites()
site_by_id = {s['id']: s for s in sites}
ROLE_OPTIONS = ['manager', 'viewer', 'admin']
role_fmt = lambda r: f"{sidebar.ROLE_LABELS.get(r, r)} ({r})"  # noqa: E731

if users:
    df = pd.DataFrame([{'아이디': u['username'], '권한': sidebar.ROLE_LABELS.get(u['role'], u['role']),
                        '담당 현장': u.get('site_name') or ('전체' if u['role'] != 'manager' else '(미배정)'),
                        '생성일시': u['created_at']} for u in users])
    st.dataframe(df, width="stretch", hide_index=True)

st.markdown("---")
tab_add, tab_pw, tab_role, tab_del = st.tabs(["➕ 사용자 추가", "🔒 비밀번호 초기화", "✏️ 권한 변경", "🗑️ 삭제"])

with tab_add:
    with st.form("form_add_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_username = c1.text_input("아이디 *")
        new_password = c2.text_input(f"비밀번호 * ({sidebar.MIN_PASSWORD_LEN}자 이상)", type="password")
        c3, c4 = st.columns(2)
        role = c3.selectbox("권한", ROLE_OPTIONS, format_func=role_fmt)
        sel_sites = c4.multiselect("담당 현장 (현장담당자만 해당)", list(site_by_id),
                                   format_func=lambda i: site_by_id[i]['name'])
        if st.form_submit_button("추가", type="primary"):
            problem = sidebar.password_problem(new_password, new_password)
            if not new_username.strip():
                st.error("아이디를 입력하세요.")
            elif problem:
                st.error(problem)
            elif role == 'manager' and not sel_sites:
                st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
            else:
                ok, result = db.add_user(new_username.strip(), new_password, role, sel_sites)
                if ok:
                    sidebar.flash(f"사용자 '{new_username.strip()}' 추가 완료.")
                    st.rerun()
                st.error(result)

by_id = {u['id']: u for u in users}

with tab_pw:
    sel = st.selectbox("사용자 선택", list(by_id), key="pw_sel", format_func=lambda i: by_id[i]['username'])
    with st.form("form_change_pw", clear_on_submit=True):
        pw1 = st.text_input("새 비밀번호 *", type="password")
        pw2 = st.text_input("비밀번호 확인 *", type="password")
        if st.form_submit_button("변경", type="primary"):
            problem = sidebar.password_problem(pw1, pw2)
            if problem:
                st.error(problem)
            else:
                db.update_user_password(sel, pw1)
                st.success(f"'{by_id[sel]['username']}' 비밀번호가 변경되었습니다.")

with tab_role:
    sel2 = st.selectbox("사용자 선택", list(by_id), key="role_sel", format_func=lambda i: by_id[i]['username'])
    u_info = by_id[sel2]
    cur_ids = [int(x) for x in (u_info.get('site_ids_str') or '').split(',') if x.strip()]
    with st.form(f"form_change_role_{sel2}"):
        c1, c2 = st.columns(2)
        new_role = c1.selectbox("권한", ROLE_OPTIONS, format_func=role_fmt,
                                index=ROLE_OPTIONS.index(u_info['role']) if u_info['role'] in ROLE_OPTIONS else 0)
        new_sites = c2.multiselect("담당 현장", list(site_by_id), default=[i for i in cur_ids if i in site_by_id],
                                   format_func=lambda i: site_by_id[i]['name'])
        if st.form_submit_button("저장", type="primary"):
            if new_role == 'manager' and not new_sites:
                st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
            else:
                ok, msg = db.update_user(sel2, new_role, new_sites)
                if ok:
                    if sel2 == user['id']:
                        st.session_state.user.update(role=new_role, site_ids=new_sites)
                    sidebar.flash(msg)
                    st.rerun()
                st.error(msg)
    st.caption("권한 변경은 해당 사용자가 다시 로그인하면 적용됩니다.")

with tab_del:
    deletable = [u for u in users if u['id'] != user['id']]
    if not deletable:
        st.info("삭제할 수 있는 다른 사용자가 없습니다. (본인 계정은 삭제 불가)")
    else:
        dmap = {u['id']: u for u in deletable}
        sel_del = st.selectbox("삭제할 사용자", list(dmap), key="del_sel", format_func=lambda i: dmap[i]['username'])
        ok_chk = st.checkbox(f"'{dmap[sel_del]['username']}' 계정을 삭제합니다. (되돌릴 수 없음)", key=f"del_u_{sel_del}")
        if st.button("삭제 확인", type="primary", disabled=not ok_chk):
            ok, msg = db.delete_user(sel_del)
            sidebar.flash(msg, "success" if ok else "error")
            st.rerun()
