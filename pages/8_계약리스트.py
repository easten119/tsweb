import io
import streamlit as st
import pandas as pd
import db
import sidebar

st.set_page_config(page_title="계약 리스트", page_icon="📋", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📋 계약 리스트")

# ── 현장 선택 ─────────────────────────────────────────────────────
all_sites = db.get_all_sites()
if not all_sites:
    st.info("등록된 현장이 없습니다.")
    st.stop()

accessible = sidebar.get_accessible_sites(user, all_sites)
if not accessible:
    st.error("담당 현장이 배정되지 않았습니다. 관리자에게 문의하세요.")
    st.stop()
elif len(accessible) == 1:
    site_id = accessible[0]['id']
    st.caption(f"현장: **{accessible[0]['name']}**")
else:
    site_map = {s['name']: s['id'] for s in accessible}
    sel_site = st.selectbox("현장 선택", list(site_map.keys()))
    site_id = site_map[sel_site]

# ── 필터 ─────────────────────────────────────────────────────────
fc1, fc2 = st.columns(2)
type_filter = fc1.selectbox("계약구분 필터", ["전체", "가계약", "계약"])
contracts = db.get_contracts(
    site_id=site_id,
    contract_type=type_filter if type_filter != "전체" else None,
    active_only=True,
)

employees = db.get_employees(site_id)
teams = ["전체"] + sorted(set(e['team'] for e in employees if e.get('team')))
team_filter = fc2.selectbox("담당팀 필터", teams)
if team_filter != "전체":
    contracts = [c for c in contracts if c.get('assigned_team') == team_filter]

if not contracts:
    st.info("계약 내역이 없습니다.")
    st.stop()

# ── 테이블 ───────────────────────────────────────────────────────
rows = []
for ct in contracts:
    bno = str(ct.get('building_no') or '')
    uno = str(ct.get('unit_no') or '')
    rows.append({
        "단지": ct.get("complex_name") or "",
        "동": bno + "동" if bno else "",
        "호수": uno,
        "계약구분": ct.get("contract_type") or "",
        "계약자명": ct.get("customer_name") or "",
        "연락처": ct.get("phone") or "",
        "계약일": ct.get("contract_date") or "",
        "담당팀": ct.get("assigned_team") or "",
        "담당자": ct.get("assigned_staff") or "",
        "계약금(원)": ct.get("deposit_total") or 0,
        "비고": ct.get("notes") or "",
    })

df = pd.DataFrame(rows)

st.markdown(f"총 **{len(contracts)}**건")
st.dataframe(
    df.style.format({"계약금(원)": "{:,}"}),
    use_container_width=True,
    hide_index=True,
)

# ── 엑셀 다운로드 ─────────────────────────────────────────────────
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='계약리스트')
buf.seek(0)
st.download_button(
    "📥 엑셀 다운로드",
    data=buf,
    file_name="계약리스트.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
