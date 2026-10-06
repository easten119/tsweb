import os
import tempfile
import pandas as pd
import streamlit as st
from datetime import datetime
import db
import sidebar

user = sidebar.page_setup("데이터 점검", "🩺", roles=('admin',))
sidebar.show_flash()
st.caption("정산·계약 데이터에서 규칙과 맞지 않는 기록을 찾아 보여줍니다. 수정은 버튼을 눌러야만 실행됩니다.")

# ── 백업 ─────────────────────────────────────────────────────────
with st.expander("💾 DB 백업 받기 (수정 전 권장)"):
    if st.button("백업 파일 만들기"):
        path = os.path.join(tempfile.gettempdir(), f"tsweb_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
        db.backup_database(path)
        with open(path, 'rb') as f:
            data = f.read()
        os.remove(path)
        st.download_button("📥 백업 다운로드", data=data, file_name=os.path.basename(path),
                           mime="application/octet-stream")

# ── 1. 정산 이력 ─────────────────────────────────────────────────
st.markdown("### 1. 정산 이력")
issues = db.find_settlement_anomalies()
exec_issues = [i for i in issues if i['issue'] == 'exec_date']
other_issues = [i for i in issues if i['issue'] != 'exec_date']

if not issues:
    st.success("이상 없음")
else:
    if exec_issues:
        st.warning(f"규칙과 다른 일비 집행일 {len(exec_issues)}건 — 같은 차수가 다른 집행일로 두 번 저장될 수 있는 원인입니다.")
        st.dataframe(pd.DataFrame([{'현장': i['site_name'], '직원': i['employee_name'], '판정기간':
                                    f"{i['period_start']}~{i['period_end']}", '저장 집행일': i['execution_date'],
                                    '규칙 집행일': i['expected'], '금액': i['amount']} for i in exec_issues]),
                     width="stretch", hide_index=True)
        if st.button("🔧 일비 집행일을 규칙대로 바로잡기"):
            fixed, skipped = db.fix_daily_execution_dates()
            sidebar.flash(f"{fixed}건 수정" + (f", {skipped}건은 같은 집행일 기록이 이미 있어 건너뜀(아래 목록에서 확인)"
                                             if skipped else ""))
            st.rerun()
    if other_issues:
        st.warning(f"확인이 필요한 정산 기록 {len(other_issues)}건 — 실제 지급 여부를 확인한 뒤, 잘못된 기록만 선택해 삭제하세요.")
        df = pd.DataFrame([{'_id': i['id'], '선택': False, '현장': i['site_name'], '직원': i['employee_name'],
                            '직원ID': i['employee_id'],
                            '유형': '일비' if i['settlement_type'] == 'daily_allowance' else '숙소비',
                            '집행일': i['execution_date'], '판정기간': f"{i['period_start']}~{i['period_end']}",
                            '금액': i['amount'], '문제': i['desc']} for i in other_issues])
        ed = st.data_editor(df, hide_index=True, width="stretch", key="anomaly_editor",
                            disabled=[c for c in df.columns if c != '선택'],
                            column_config={'_id': None, '금액': st.column_config.NumberColumn(format="localized")})
        ids = ed.loc[ed['선택'] == True, '_id'].tolist()  # noqa: E712
        if ids and st.button(f"🗑️ 선택한 정산 기록 {len(ids)}건 삭제", type="primary"):
            n = db.delete_settlements(ids)
            sidebar.flash(f"{n}건 삭제")
            st.rerun()

# ── 2. 호실 상태 ↔ 계약 ──────────────────────────────────────────
st.markdown("### 2. 호실 상태 ↔ 유효 계약")
mism = db.find_unit_status_mismatches()
if not mism:
    st.success("이상 없음")
else:
    st.warning(f"호실 상태와 계약이 맞지 않는 호실 {len(mism)}개")
    st.dataframe(pd.DataFrame([{'현장': m['site_name'], '동': m['building_no'], '호수': m['unit_no'],
                                '현재 상태': m['status'], '계약 기준 상태': m['expected'] or '공실'} for m in mism]),
                 width="stretch", hide_index=True)
    if st.button("🔧 계약 기준으로 호실 상태 맞추기"):
        n = db.resync_unit_status()
        sidebar.flash(f"{n}개 호실 상태 변경")
        st.rerun()

orphans = db.find_orphan_cancellations()
if orphans:
    st.info(f"원 계약 기록이 없는 해지 내역 {len(orphans)}건 (해지 리스트에 계약자명이 빈칸으로 표시됨)")
    st.dataframe(pd.DataFrame([{'현장': o['site_name'], '동': o['building_no'], '호수': o['unit_no'],
                                '해지접수일': o['cancel_date'], '원 계약ID': o['contract_id']} for o in orphans]),
                 width="stretch", hide_index=True)

# ── 3. 직원 ─────────────────────────────────────────────────────
st.markdown("### 3. 직원")
dups = db.find_duplicate_employee_names()
no_fwd = db.find_employees_without_first_date()
if not dups and not no_fwd:
    st.success("이상 없음")
if dups:
    st.info("같은 현장의 동명이인 — 연락처를 꼭 입력해 두면 엑셀 업로드에서 구분됩니다. "
            "실수로 중복 등록한 경우 출근·정산 기록이 없는 쪽을 직원 관리에서 삭제하세요.")
    rows = []
    for d in dups:
        for eid in d['ids'].split(','):
            e = db.get_employee(int(eid))
            rows.append({'현장': d['site_name'], '이름': e['name'], 'ID': e['id'], '팀': e.get('team'),
                         '연락처': e.get('phone') or '(없음)', '첫출근일': e.get('first_work_date') or '(없음)',
                         '상태': e['status'], '정산이력': db.count_employee_settlements(e['id'])})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
if no_fwd:
    st.info(f"첫출근일이 없는 재직자 {len(no_fwd)}명 — 숙소비가 계산되지 않습니다.")
    st.dataframe(pd.DataFrame([{'현장': e['site_name'], '이름': e['name'], 'ID': e['id'], '팀': e.get('team')}
                               for e in no_fwd]), width="stretch", hide_index=True)
