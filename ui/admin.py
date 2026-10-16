"""관리자 화면 — 현장 관리 · 사용자 관리 · 데이터 점검"""
import os
import tempfile
from datetime import date, datetime

import pandas as pd
import streamlit as st

import db
import templates
from ui import common as cm
from ui import layout


def render(user, view):
    {'admin_sites': _sites, 'admin_users': _users, 'admin_check': _check}[view](user)


def _title(t, sub=None):
    st.markdown(f"<div class='ts-crumb'>관리</div><div class='ts-title'>{t}</div>"
                + (f"<div class='ts-meta'>{sub}</div>" if sub else ""), unsafe_allow_html=True)


# ── 현장 관리 ─────────────────────────────────────────────────────
def _sites(user):
    _title("현장 관리", "현장 추가·삭제. 현장별 세부 설정은 각 현장 화면의 '설정' 탭에서 합니다.")
    sites = db.get_all_sites()
    summ = db.get_all_site_unit_summary()
    if sites:
        df = pd.DataFrame([{'_id': s['id'], '현장명': s['name'], '지역': s['region'], '양식': s.get('template') or '-',
                            '상태': s['status'], '시작일': s['start_date'], '호실': sum(summ.get(s['id'], {}).values()),
                            '재직': s['employee_count'], '일비': s.get('daily_allowance'),
                            '숙소비(해당/타)': f"{cm.won(s.get('housing_local'))} / {cm.won(s.get('housing_other'))}"}
                           for s in sites])
        ev = st.dataframe(df, hide_index=True, placeholder="", width="stretch", on_select="rerun", selection_mode="single-row",
                          column_config={'_id': None, '일비': cm.MONEY}, key="as_df")
        rows = ev.selection.rows if hasattr(ev, 'selection') else []
        if rows:
            sid = int(df.iloc[rows[0]]['_id'])
            c = st.columns([1.3, 1.3, 5])
            if c[0].button("현장 화면 열기", type="primary", icon=":material/open_in_new:"):
                layout.go('site', sid, tab='설정')
            with c[1].popover("현장 삭제", icon=":material/delete:"):
                st.caption("직원·호실·입출금·정산 이력이 없는 현장만 삭제됩니다. 끝난 현장은 설정에서 '완료'로 바꾸세요.")
                if st.button("삭제 확인", type="primary", key=f"as_del_{sid}"):
                    ok, msg = db.delete_site(sid)
                    cm.flash(msg, "success" if ok else "error")
                    st.rerun()

    cm.section("현장 추가")
    with st.form("as_add", clear_on_submit=True):
        r = st.columns(4)
        name = r[0].text_input("현장명 *")
        region = r[1].text_input("지역 *")
        start = r[2].date_input("시작일", value=date.today(), format="YYYY-MM-DD")
        preset = r[3].selectbox("계약 양식", list(templates.PRESETS), format_func=lambda k: templates.PRESETS[k]['label'])
        r = st.columns(4)
        da = r[0].number_input("일비 단가", value=10000, step=1000, min_value=0)
        hl = r[1].number_input("숙소비 (해당지역)", value=200000, step=10000, min_value=0)
        ho = r[2].number_input("숙소비 (타지역)", value=300000, step=10000, min_value=0)
        if st.form_submit_button("추가", type="primary"):
            if not name.strip() or not region.strip():
                st.error("현장명과 지역을 입력하세요.")
            elif db.site_name_exists(name.strip()):
                st.error("같은 이름의 현장이 이미 있습니다.")
            else:
                sid = db.add_site(name.strip(), region.strip(), str(start), '진행중', int(da), int(hl), int(ho),
                                  template=preset, config=templates.dump_config(templates.preset_config(preset)))
                cm.flash(f"'{name.strip()}' 추가 완료 — 설정 탭에서 호실을 등록하세요.")
                layout.go('site', sid, tab='설정')


# ── 사용자 관리 ───────────────────────────────────────────────────
def _users(user):
    _title("사용자 관리")
    users = db.get_all_users()
    sites = db.get_all_sites()
    sbi = {s['id']: s for s in sites}
    roles = ['manager', 'viewer', 'admin']
    rfmt = lambda r: cm.ROLE_LABELS.get(r, r)  # noqa: E731
    st.dataframe(pd.DataFrame([{'아이디': u['username'], '권한': rfmt(u['role']),
                                '담당 현장': u.get('site_name') or ('전체' if u['role'] != 'manager' else '(미배정)'),
                                '생성일': u['created_at']} for u in users]), hide_index=True, placeholder="", width="stretch")
    by = {u['id']: u for u in users}
    t_add, t_role, t_pw, t_del = st.tabs(["사용자 추가", "권한·담당 현장", "비밀번호 초기화", "삭제"])
    with t_add:
        with st.form("au_add", clear_on_submit=True):
            r = st.columns(4)
            un = r[0].text_input("아이디 *")
            pw = r[1].text_input(f"비밀번호 * ({cm.MIN_PASSWORD_LEN}자 이상)", type="password")
            role = r[2].selectbox("권한", roles, format_func=rfmt)
            ss = r[3].multiselect("담당 현장 (현장담당자)", list(sbi), format_func=lambda i: sbi[i]['name'])
            if st.form_submit_button("추가", type="primary"):
                problem = cm.password_problem(pw, pw)
                if not un.strip():
                    st.error("아이디를 입력하세요.")
                elif problem:
                    st.error(problem)
                elif role == 'manager' and not ss:
                    st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
                else:
                    ok, res = db.add_user(un.strip(), pw, role, ss)
                    if ok:
                        cm.flash(f"'{un.strip()}' 추가 완료")
                        st.rerun()
                    st.error(res)
    with t_role:
        uid = st.selectbox("사용자", list(by), key="au_role_u", format_func=lambda i: by[i]['username'])
        u = by[uid]
        cur = [int(x) for x in (u.get('site_ids_str') or '').split(',') if x.strip()]
        with st.form(f"au_role_{uid}"):
            r = st.columns(2)
            role = r[0].selectbox("권한", roles, index=roles.index(u['role']) if u['role'] in roles else 0,
                                  format_func=rfmt)
            ss = r[1].multiselect("담당 현장", list(sbi), default=[i for i in cur if i in sbi],
                                  format_func=lambda i: sbi[i]['name'])
            if st.form_submit_button("저장", type="primary"):
                if role == 'manager' and not ss:
                    st.error("현장담당자는 담당 현장을 하나 이상 선택해야 합니다.")
                else:
                    ok, msg = db.update_user(uid, role, ss)
                    if ok:
                        if uid == user['id']:
                            st.session_state.user.update(role=role, site_ids=ss)
                        cm.flash(msg)
                        st.rerun()
                    st.error(msg)
        st.caption("변경 내용은 해당 사용자가 다시 로그인하면 적용됩니다.")
    with t_pw:
        uid = st.selectbox("사용자", list(by), key="au_pw_u", format_func=lambda i: by[i]['username'])
        with st.form("au_pw", clear_on_submit=True):
            p1 = st.text_input("새 비밀번호", type="password")
            p2 = st.text_input("새 비밀번호 확인", type="password")
            if st.form_submit_button("변경", type="primary"):
                problem = cm.password_problem(p1, p2)
                if problem:
                    st.error(problem)
                else:
                    db.update_user_password(uid, p1)
                    st.success(f"'{by[uid]['username']}' 비밀번호 변경 완료")
    with t_del:
        others = {i: u for i, u in by.items() if i != user['id']}
        if not others:
            st.caption("삭제할 수 있는 다른 사용자가 없습니다.")
        else:
            uid = st.selectbox("사용자", list(others), key="au_del_u", format_func=lambda i: others[i]['username'])
            if st.button("삭제", type="primary", key=f"au_del_{uid}"):
                ok, msg = db.delete_user(uid)
                cm.flash(msg, "success" if ok else "error")
                st.rerun()


# ── 데이터 점검 ───────────────────────────────────────────────────
def _check(user):
    _title("데이터 점검", "규칙과 맞지 않는 기록을 찾아 보여줍니다. 수정은 버튼을 눌러야만 실행됩니다.")
    with st.expander("DB 백업 받기 (수정 전 권장)", icon=":material/backup:"):
        if st.button("백업 파일 만들기"):
            path = os.path.join(tempfile.gettempdir(), f"tsweb_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
            db.backup_database(path)
            with open(path, 'rb') as fh:
                data = fh.read()
            os.remove(path)
            st.download_button("백업 다운로드", data=data, file_name=os.path.basename(path),
                               mime="application/octet-stream")

    cm.section("정산 이력")
    issues = db.find_settlement_anomalies()
    ex_issues = [i for i in issues if i['issue'] == 'exec_date']
    other = [i for i in issues if i['issue'] != 'exec_date']
    if not issues:
        st.success("이상 없음")
    if ex_issues:
        st.warning(f"규칙과 다른 일비 집행일 {len(ex_issues)}건")
        if st.button("일비 집행일을 규칙대로 바로잡기"):
            fixed, skipped = db.fix_daily_execution_dates()
            cm.flash(f"{fixed}건 수정" + (f", {skipped}건 건너뜀" if skipped else ""))
            st.rerun()
    if other:
        st.warning(f"확인이 필요한 정산 기록 {len(other)}건 — 실제 지급 여부를 확인한 뒤 잘못된 기록만 삭제하세요.")
        df = pd.DataFrame([{'_id': i['id'], '선택': False, '현장': i['site_name'], '직원': i['employee_name'],
                            '직원ID': i['employee_id'],
                            '유형': '일비' if i['settlement_type'] == 'daily_allowance' else '숙소비',
                            '집행일': i['execution_date'], '판정기간': f"{i['period_start']}~{i['period_end']}",
                            '금액': i['amount'], '문제': i['desc']} for i in other])
        ed = st.data_editor(df, hide_index=True, placeholder="", width="stretch", key="ck_ed",
                            disabled=[c for c in df.columns if c != '선택'],
                            column_config={'_id': None, '금액': cm.MONEY})
        ids = ed.loc[ed['선택'] == True, '_id'].tolist()  # noqa: E712
        if ids and st.button(f"선택 {len(ids)}건 삭제", type="primary"):
            cm.flash(f"{db.delete_settlements(ids)}건 삭제")
            st.rerun()

    cm.section("호실 상태 ↔ 유효 계약")
    mism = db.find_unit_status_mismatches()
    if not mism:
        st.success("이상 없음")
    else:
        st.warning(f"호실 상태와 계약이 맞지 않는 호실 {len(mism)}개")
        st.dataframe(pd.DataFrame([{'현장': m['site_name'], '동': m['building_no'], '호수': m['unit_no'],
                                    '현재': m['status'], '계약 기준': m['expected'] or '공실'} for m in mism]),
                     hide_index=True, placeholder="", width="stretch")
        if st.button("계약 기준으로 맞추기"):
            cm.flash(f"{db.resync_unit_status()}개 호실 변경")
            st.rerun()
    orphans = db.find_orphan_cancellations()
    if orphans:
        st.info(f"원 계약 기록이 없는 해지 내역 {len(orphans)}건 (해지 목록에 계약자명이 빈칸으로 표시)")

    cm.section("직원")
    dups = db.find_duplicate_employee_names()
    no_fwd = db.find_employees_without_first_date()
    if not dups and not no_fwd:
        st.success("이상 없음")
    if dups:
        rows = []
        for d in dups:
            for eid in d['ids'].split(','):
                e = db.get_employee(int(eid))
                rows.append({'현장': d['site_name'], '이름': e['name'], 'ID': e['id'], '팀': e.get('team'),
                             '연락처': e.get('phone') or '(없음)', '첫출근일': e.get('first_work_date') or '(없음)',
                             '정산이력': db.count_employee_settlements(e['id'])})
        st.info("같은 현장의 동명이인 — 연락처를 입력해 두면 업로드에서 구분됩니다.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, placeholder="", width="stretch")
    if no_fwd:
        st.info(f"첫출근일이 없는 재직자 {len(no_fwd)}명 — 숙소비 계산 불가")
        st.dataframe(pd.DataFrame([{'현장': e['site_name'], '이름': e['name'], 'ID': e['id'], '팀': e.get('team')}
                                   for e in no_fwd]), hide_index=True, placeholder="", width="stretch")
