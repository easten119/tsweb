import streamlit as st
import pandas as pd
import db
import sidebar

user = sidebar.page_setup("계약 리스트", "📋")

site_id, site, _ = sidebar.select_site(user)

fc1, fc2, fc3 = st.columns(3)
type_filter = fc1.selectbox("계약구분", ["전체", "가계약", "계약"])
status_filter = fc2.selectbox("계약상태", ["유효 계약만", "해지 포함 전체", "해지된 계약만"])
employees = db.get_employees(site_id, include_retired=True)
teams = ["전체"] + sorted({e['team'] for e in employees if e.get('team')})
team_filter = fc3.selectbox("담당팀", teams)
keyword = st.text_input("검색 (호수·계약자·연락처·담당자)", placeholder="예: 1502, 홍길동")

contracts = db.get_contracts(site_id=site_id, contract_type=None if type_filter == "전체" else type_filter,
                             active_only=status_filter == "유효 계약만")
if status_filter == "해지된 계약만":
    contracts = [c for c in contracts if c.get('status') == db.CONTRACT_CANCELLED]
if team_filter != "전체":
    contracts = [c for c in contracts if c.get('assigned_team') == team_filter]
if keyword.strip():
    kw = keyword.strip()
    contracts = [c for c in contracts if any(kw in str(c.get(f) or '') for f in
                                             ('unit_no', 'customer_name', 'phone', 'assigned_staff', 'notes'))]

if not contracts:
    st.info("계약 내역이 없습니다.")
    st.stop()

df = pd.DataFrame([{
    "단지": c.get("complex_name") or "", "동": f"{c['building_no']}동", "호수": c.get('unit_no') or '',
    "타입": c.get('unit_type') or '', "상태": c.get('status') or '', "계약구분": c.get("contract_type") or "",
    "계약자명": c.get("customer_name") or "", "연락처": c.get("phone") or "",
    "계약일": c.get("contract_date") or "", "담당팀": c.get("assigned_team") or "",
    "담당자": c.get("assigned_staff") or "", "분양가": c.get('sale_price') or 0,
    "계약금": c.get("deposit_total") or 0, "비고": c.get("notes") or "",
} for c in contracts])

m1, m2, m3 = st.columns(3)
m1.metric("건수", f"{len(df)}건")
m2.metric("계약금 합계", f"{int(df['계약금'].sum()):,}원")
m3.metric("분양가 합계", f"{int(df['분양가'].sum()):,}원")

st.dataframe(df, width="stretch", hide_index=True,
             column_config={"분양가": st.column_config.NumberColumn(format="localized"),
                            "계약금": st.column_config.NumberColumn(format="localized")})

with st.expander("📊 담당팀·담당자별 실적"):
    active_df = df[df['상태'] == db.CONTRACT_ACTIVE]
    if active_df.empty:
        st.caption("유효 계약 없음")
    else:
        g = active_df.groupby(['담당팀', '담당자', '계약구분']).size().unstack(fill_value=0)
        g['합계'] = g.sum(axis=1)
        st.dataframe(g.sort_values('합계', ascending=False), width="stretch")

st.download_button("📥 엑셀 다운로드", data=sidebar.excel_bytes({'계약리스트': df}),
                   file_name=f"계약리스트_{site['name']}.xlsx", mime=sidebar.XLSX_MIME)
