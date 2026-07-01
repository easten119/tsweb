import io
import streamlit as st
import pandas as pd
import openpyxl
from datetime import date, datetime
import db
import sidebar

st.set_page_config(page_title="직원 관리", page_icon="👷", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("👷 직원 관리")

# ── 현장 선택 ──────────────────────────────────────────────────────
all_sites = db.get_all_sites()

site_options = sidebar.get_accessible_sites(user, all_sites)

if not site_options:
    st.info("접근 가능한 현장이 없습니다.")
    st.stop()

site_map = {s['name']: s['id'] for s in site_options}
selected_site_name = st.selectbox("현장 선택", list(site_map.keys()))
site_id = site_map[selected_site_name]

# ── 직원 목록 ──────────────────────────────────────────────────────
show_retired = st.checkbox("퇴직자 포함")
employees = db.get_employees(site_id, include_retired=show_retired)

if employees:
    df = pd.DataFrame(employees)[['name', 'division', 'team', 'phone', 'first_work_date', 'housing_region', 'status']]
    df.columns = ['이름', '본부', '팀', '연락처', '첫출근일', '지역구분', '상태']

    def color_status(val):
        return 'color: gray' if val == '퇴직' else ''

    st.dataframe(
        df.style.map(color_status, subset=['상태']),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("등록된 재직 직원이 없습니다.")

# ── viewer는 읽기 전용 ─────────────────────────────────────────────
if user['role'] == 'viewer':
    st.caption("뷰어 권한으로는 수정할 수 없습니다.")
    st.stop()

st.markdown("---")
tab_add, tab_edit, tab_upload = st.tabs(["➕ 직원 추가", "✏️ 직원 수정 / 퇴직 처리", "📤 엑셀 일괄 업로드"])

with tab_add:
    with st.form("form_add_emp", clear_on_submit=True):
        col1, col2 = st.columns(2)
        name = col1.text_input("이름 *")
        division = col2.text_input("본부")
        col3, col4 = st.columns(2)
        team = col3.text_input("팀명 (예: 1팀)")
        phone = col4.text_input("연락처")
        col5, col6 = st.columns(2)
        first_work_date = col5.date_input("첫출근일", value=date.today())
        housing_region = col6.selectbox("지역구분", ['해당지역', '타지역'])
        if st.form_submit_button("추가", type="primary"):
            if name.strip():
                db.add_employee(
                    site_id, name.strip(), division.strip() or None,
                    team.strip(), phone.strip(), str(first_work_date), housing_region
                )
                st.success(f"'{name}' 직원 추가 완료.")
                st.rerun()
            else:
                st.error("이름을 입력하세요.")

with tab_edit:
    active_emps = db.get_employees(site_id, include_retired=True)
    if not active_emps:
        st.info("직원이 없습니다.")
    else:
        emp_map = {f"{e['name']} ({e['team'] or '-'})": e['id'] for e in active_emps}
        selected_emp_label = st.selectbox("수정할 직원 선택", list(emp_map.keys()), key="edit_emp_sel")
        emp = db.get_employee(emp_map[selected_emp_label])

        with st.form("form_edit_emp"):
            col1, col2 = st.columns(2)
            name = col1.text_input("이름 *", value=emp['name'])
            division = col2.text_input("본부", value=emp.get('division') or '')
            col3, col4 = st.columns(2)
            team = col3.text_input("팀명", value=emp['team'] or '')
            phone = col4.text_input("연락처", value=emp['phone'] or '')
            col5, col6 = st.columns(2)
            fwd = date.fromisoformat(emp['first_work_date']) if emp.get('first_work_date') else date.today()
            first_work_date = col5.date_input("첫출근일", value=fwd)
            hr_idx = 0 if emp['housing_region'] == '해당지역' else 1
            housing_region = col6.selectbox("지역구분", ['해당지역', '타지역'], index=hr_idx)
            col7, col8 = st.columns(2)
            status_idx = 0 if emp['status'] == '재직' else 1
            status = col7.selectbox("재직 상태", ['재직', '퇴직'], index=status_idx)

            if st.form_submit_button("저장", type="primary"):
                if name.strip():
                    db.update_employee(
                        emp['id'], name.strip(), division.strip() or None,
                        team.strip(), phone.strip(), str(first_work_date), housing_region, status
                    )
                    st.success("저장 완료.")
                    st.rerun()
                else:
                    st.error("이름을 입력하세요.")

        st.markdown("---")
        confirm_del = st.checkbox(f"'{emp['name']}' 직원을 삭제합니다 (출근·정산 이력 포함)", key="confirm_del")
        if confirm_del:
            if st.button("삭제 확인", type="primary", key="del_emp_btn"):
                db.delete_employee(emp['id'])
                st.success(f"'{emp['name']}' 직원이 삭제되었습니다.")
                st.rerun()

with tab_upload:
    st.markdown("##### 엑셀 일괄 업로드")
    st.caption(
        "**①직원정보 시트** (시트명에 '직원' 포함): 현장명 | 본부 | 팀 | 이름 | 연락처 | 첫출근일 | 지역구분 | 상태 | 비고  \n"
        "**②출근현황 시트** (시트명에 '출근' 또는 '월' 포함): 현장명 | 본부 | 팀 | 이름 | MM/DD | MM/DD | … | 출근: **O**, 미출근: 빈칸"
    )

    upload_year = st.number_input(
        "출근 연도", min_value=2020, max_value=2035,
        value=date.today().year, step=1, key="upload_year"
    )

    uploaded_file = st.file_uploader("xlsx 파일 선택", type=["xlsx"])
    if uploaded_file:
        try:
            file_bytes = uploaded_file.read()
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            wb.close()
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")
            st.stop()

        # 직원정보 시트: "직원" 포함 우선, 없으면 출근/월 미포함 시트
        employee_sheets = [sn for sn in sheet_names if "직원" in sn]
        if not employee_sheets:
            non_att = [sn for sn in sheet_names if "출근" not in sn and "월" not in sn]
            employee_sheets = non_att

        # 출근현황 시트: "출근" 또는 "월" 포함, 없으면 전체 fallback
        attendance_sheets = [sn for sn in sheet_names if "출근" in sn or "월" in sn]
        if not attendance_sheets:
            attendance_sheets = [sn for sn in sheet_names if sn not in employee_sheets] or list(sheet_names)

        print(f"[DEBUG] 전체시트={sheet_names}, 직원시트={employee_sheets}, 출근시트={attendance_sheets}")

        # ── 날짜 헤더 파싱 함수 ───────────────────────────────────
        def parse_date_header(val, default_year):
            if hasattr(val, 'month') and hasattr(val, 'day'):
                yr = val.year if hasattr(val, 'year') else default_year
                return date(yr, val.month, val.day)
            s = str(val).strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(s, fmt).date()
                except ValueError:
                    pass
            parts = s.split('/')
            if len(parts) == 2:
                try:
                    return date(default_year, int(parts[0]), int(parts[1]))
                except (ValueError, TypeError):
                    pass
            return None

        default_year = int(upload_year)

        def _read_sheet(sn):
            """시트 읽기 + 헤더 자동 감지 → (raw_df, date_cols) 반환"""
            probe = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sn,
                                  header=None, nrows=2, dtype=str)
            first_cell = str(probe.iloc[0, 0]).strip() if not probe.empty else ''
            hrow = 0 if first_cell == "현장명" else 1
            print(f"[DEBUG] [{sn}] 첫셀={first_cell!r} → header={hrow}")
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sn,
                               header=hrow, dtype=str).fillna('')
            dcols = []
            for ci, cn in enumerate(df.columns):
                if ci < 4:  # 현장명(0) 본부(1) 팀(2) 이름(3) skip — 날짜는 col4부터
                    continue
                p = parse_date_header(cn, default_year)
                if p:
                    dcols.append((ci, p.month, p.day))
            print(f"[DEBUG] [{sn}] 날짜컬럼 {len(dcols)}개: {[f'{m}/{d}' for _, m, d in dcols[:5]]}")
            return df, dcols

        # ── Phase 1: 직원 upsert (직원정보 시트) ─────────────────
        emp_sheet = employee_sheets[0] if employee_sheets else (attendance_sheets[0] if attendance_sheets else sheet_names[0])
        try:
            probe_e = pd.read_excel(io.BytesIO(file_bytes), sheet_name=emp_sheet,
                                    header=None, nrows=2, dtype=str)
            fc_e = str(probe_e.iloc[0, 0]).strip() if not probe_e.empty else ''
            hrow_e = 0 if fc_e == "현장명" else 1
            first_df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=emp_sheet,
                                     header=hrow_e, dtype=str).fillna('')
            print(f"[DEBUG] 직원시트[{emp_sheet}] header={hrow_e}, shape={first_df.shape}, cols={list(first_df.columns[:9])}")
        except Exception as e:
            st.error(f"직원정보 시트 읽기 오류: {e}")
            st.stop()

        if len(first_df.columns) < 4:
            st.error("컬럼 수 부족: 최소 4개 (현장명, 본부, 팀, 이름) 필요")
            st.stop()

        all_sites_map = {s['name']: s['id'] for s in db.get_all_sites()}

        emp_lookup = {}
        for site in db.get_all_sites():
            for e in db.get_employees(site['id'], include_retired=True):
                emp_lookup[(site['id'], e['name'])] = e

        def _s(val, default=None):
            v = str(val).strip()
            return default if not v or v == 'nan' else v

        ok_emp, fail_emp, msgs = 0, 0, []

        def _parse_work_date(raw):
            """엑셀 첫출근일 → 'YYYY-MM-DD' 문자열 또는 None.
            datetime/Timestamp 객체 우선 처리, 그 외 문자열 다양한 포맷 시도."""
            if raw is None:
                return None
            # datetime / Timestamp / date 객체 직접 처리 (최우선)
            if hasattr(raw, 'strftime'):
                try:
                    return raw.strftime("%Y-%m-%d")
                except Exception:
                    pass
            s = str(raw).strip()
            if not s or s in ('nan', 'NaT', ''):
                return None
            # 시간 컴포넌트 제거: "2026-01-15 00:00:00" → "2026-01-15"
            date_part = s.split(' ')[0].split('T')[0]
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d"):
                try:
                    return datetime.strptime(date_part, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    pass
            # 엑셀 날짜 시리얼 숫자 (예: "45636.0") — 합리적 범위만 허용
            try:
                from datetime import timedelta
                serial = float(s)
                if 20000 < serial < 60000:
                    return (date(1899, 12, 30) + timedelta(days=int(serial))).strftime("%Y-%m-%d")
            except (ValueError, OverflowError):
                pass
            return None

        for i, row in first_df.iterrows():
            site_name = _s(row.iloc[0])
            division  = _s(row.iloc[1])
            team      = _s(row.iloc[2])
            emp_name  = _s(row.iloc[3])
            # 연락처(col4): _s()로 문자열 변환, 첫출근일(col5): raw 유지 → datetime 처리
            phone   = _s(row.iloc[4]) if len(row) > 4 else None
            fwd_raw = row.iloc[5] if len(row) > 5 else None      # raw 값 유지
            first_work_date = _parse_work_date(fwd_raw)

            print(f"[DEBUG] 행{i+2} {emp_name!r}: 연락처={phone!r}, "
                  f"첫출근일raw={type(fwd_raw).__name__}:{fwd_raw!r}→{first_work_date!r}")

            if not site_name or not emp_name:
                continue
            if site_name not in all_sites_map:
                fail_emp += 1
                msgs.append(f"행 {i + 2}: 현장명 '{site_name}' 없음")
                continue

            site_id_val = all_sites_map[site_name]
            existing = emp_lookup.get((site_id_val, emp_name))
            try:
                if existing:
                    db.update_employee(
                        existing['id'], existing['name'],
                        division, team,
                        phone if phone is not None else existing['phone'],
                        first_work_date if first_work_date is not None else existing['first_work_date'],
                        existing['housing_region'], existing['status'],
                    )
                    emp_id = existing['id']
                else:
                    emp_id = db.add_employee(
                        site_id_val, emp_name, division, team,
                        phone or None, first_work_date
                    )
                db.set_sort_order(emp_id, i)
                ok_emp += 1
            except Exception as e:
                fail_emp += 1
                msgs.append(f"행 {i + 2} ({emp_name}) 직원 오류: {e}")

        # 직원 추가 후 emp_lookup 갱신
        emp_lookup = {}
        for site in db.get_all_sites():
            for e in db.get_employees(site['id'], include_retired=True):
                emp_lookup[(site['id'], e['name'])] = e

        # ── Phase 2: 출근 저장 (출근현황 시트 전체) ──────────────
        ok_att, fail_att = 0, 0
        month_att_ok = {}   # {month: 성공 건수}
        any_date_cols = False

        for sheet_name in attendance_sheets:
            try:
                att_df, date_cols = _read_sheet(sheet_name)
            except Exception as e:
                msgs.append(f"[{sheet_name}] 시트 읽기 오류: {e}")
                continue
            if not date_cols:
                print(f"[DEBUG] [{sheet_name}] 날짜 컬럼 없음 → 건너뜀")
                continue
            any_date_cols = True
            months_in_sheet = sorted({m for _, m, _ in date_cols})

            for i, row in att_df.iterrows():
                site_name = _s(row.iloc[0])
                emp_name  = _s(row.iloc[3])
                if not site_name or not emp_name:
                    continue
                if site_name not in all_sites_map:
                    continue
                site_id_val = all_sites_map[site_name]
                emp = emp_lookup.get((site_id_val, emp_name))
                if not emp:
                    fail_att += 1
                    msgs.append(f"[{sheet_name}] 행 {i + 2} ({emp_name}) 직원 미등록")
                    continue
                emp_id = emp['id']

                month_work = {m: set() for m in months_in_sheet}
                for col_idx, month, day in date_cols:
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ('O', '○', '◯', '1', 'Y'):
                        month_work[month].add(f"{upload_year}-{month:02d}-{day:02d}")

                for month, work_set in month_work.items():
                    print(f"[DEBUG] [{sheet_name}] {emp_name} {month}월 {len(work_set)}일")
                    try:
                        db.save_attendance_month(emp_id, upload_year, month, work_set)
                        ok_att += 1
                        month_att_ok[month] = month_att_ok.get(month, 0) + 1
                    except Exception as e:
                        fail_att += 1
                        msgs.append(f"[{sheet_name}] 행 {i + 2} ({emp_name}) {month}월 출근 오류: {e}")

        # DB 저장 건수 확인
        import sqlite3 as _sqlite3
        _conn = _sqlite3.connect(db.DB_PATH)
        _cur = _conn.cursor()
        _cur.execute("SELECT COUNT(*) FROM attendance WHERE is_present=1")
        total_present = _cur.fetchone()[0]
        _conn.close()
        print(f"[DEBUG] attendance 테이블 is_present=1 총 건수: {total_present}")

        result_parts = [f"직원 성공 {ok_emp}명 / 실패 {fail_emp}명"]
        if any_date_cols:
            month_detail = ", ".join(f"{m}월: {cnt}건" for m, cnt in sorted(month_att_ok.items()))
            att_msg = f"출근 성공 {ok_att}명분 ({month_detail})"
            if fail_att:
                att_msg += f" / 실패 {fail_att}명분"
            result_parts.append(att_msg)
        else:
            result_parts.append("날짜 컬럼 없음 → 출근 저장 안 됨")
        st.success("  |  ".join(result_parts))
        if msgs:
            with st.expander("실패 내역 보기"):
                for msg in msgs:
                    st.error(msg)
        if ok_emp or ok_att:
            st.info("직원 목록을 갱신하려면 페이지를 새로고침하세요.")
