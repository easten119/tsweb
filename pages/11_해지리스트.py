import io
import streamlit as st
import pandas as pd
from datetime import date
import db
import sidebar

st.set_page_config(page_title="해지 리스트", page_icon="📋", layout="wide")

sidebar.require_login()

user = st.session_state.user
sidebar.render_sidebar(user)

st.title("📋 해지 리스트")

# ── 금액 입력 헬퍼 ─────────────────────────────────────────────────
def _fmt_key(key):
    raw = st.session_state.get(key, "")
    cleaned = str(raw).replace(",", "").replace(" ", "")
    if cleaned and cleaned.isdigit():
        st.session_state[key] = f"{int(cleaned):,}"

def parse_amount(text):
    cleaned = str(text or "").replace(",", "").replace(" ", "")
    if not cleaned:
        return 0
    if not cleaned.isdigit():
        return None
    return int(cleaned)

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
today = date.today()
fc1, fc2, fc3 = st.columns([2, 2, 2])
start_date = fc1.date_input("시작일 (해지접수일)", value=today.replace(day=1))
end_date   = fc2.date_input("종료일 (해지접수일)", value=today)

buildings = db.get_buildings(site_id=site_id)
bld_options = ["전체"] + [b['building_no'] + "동" for b in buildings]
sel_bld_filter = fc3.selectbox("동 필터", bld_options)

# ── 데이터 조회 ───────────────────────────────────────────────────
cancels_all = db.get_cancellations(site_id=site_id)
cancels_all = [
    c for c in cancels_all
    if str(start_date) <= str(c.get('cancel_date') or '') <= str(end_date)
]

if sel_bld_filter != "전체":
    bld_no = sel_bld_filter.replace("동", "")
    cancels_all = [c for c in cancels_all if str(c.get('building_no', '')) == bld_no]

# 해지접수일 최신순
cancels_all = sorted(cancels_all, key=lambda x: x.get('cancel_date') or '', reverse=True)

# ── 수정 폼 ──────────────────────────────────────────────────────
edit_cancel_id = st.session_state.get('edit_cancel_id')
if edit_cancel_id:
    ce = next((c for c in cancels_all if c['id'] == edit_cancel_id), None)
    if ce is None:
        ce = db.get_cancellation(edit_cancel_id)

    if ce:
        bno = str(ce.get('building_no') or '')
        uno = str(ce.get('unit_no') or '')
        dong_ho = f"{bno}동 {uno}" if bno else uno
        st.subheader("✏️ 해지 수정")
        st.caption(f"대상: {dong_ho} | ID: {edit_cancel_id}")

        amt_key  = f"edt_refund_{edit_cancel_id}"
        bank_key = f"edt_bank_{edit_cancel_id}"
        acno_key = f"edt_acno_{edit_cancel_id}"
        nts_key  = f"edt_nts_{edit_cancel_id}"

        # 첫 렌더링 시 초기화
        if amt_key not in st.session_state:
            st.session_state[amt_key]  = f"{ce.get('refund_amount', 0):,}"
            st.session_state[bank_key] = ce.get('bank') or ''
            st.session_state[acno_key] = ce.get('account_no') or ''
            st.session_state[nts_key]  = ce.get('notes') or ''

        ec1, ec2 = st.columns(2)
        ec1.date_input(
            "해지접수일",
            value=date.fromisoformat(str(ce['cancel_date'])) if ce.get('cancel_date') else date.today(),
            key=f"edt_cdate_{edit_cancel_id}",
        )
        ec2.text_input("환불은행", key=bank_key)

        ec3, ec4 = st.columns(2)
        ec3.text_input("계좌번호", key=acno_key)
        ec4.text_input(
            "환불금액 (원)",
            key=amt_key,
            placeholder="예: 1,000,000",
            on_change=_fmt_key,
            args=(amt_key,),
        )

        st.text_area("비고", key=nts_key, height=80)

        sv_col, cx_col, _ = st.columns([1, 1, 4])
        if sv_col.button("💾 수정 저장", type="primary", key="btn_cedit_save"):
            new_refund = parse_amount(st.session_state.get(amt_key, ""))
            if new_refund is None:
                st.error("환불금액: 숫자 외 문자가 포함되어 있습니다.")
            else:
                new_cdate = st.session_state.get(
                    f"edt_cdate_{edit_cancel_id}", date.today()
                )
                db.update_cancellation(
                    cancel_id=edit_cancel_id,
                    cancel_date=str(new_cdate),
                    refund_amount=new_refund,
                    bank=st.session_state.get(bank_key, "").strip() or None,
                    account_no=st.session_state.get(acno_key, "").strip() or None,
                    notes=st.session_state.get(nts_key, "").strip() or None,
                )
                st.session_state.pop('edit_cancel_id', None)
                st.session_state['_clist_ok'] = "✅ 수정 완료"
                st.rerun()

        if cx_col.button("❌ 취소", key="btn_cedit_cancel"):
            st.session_state.pop('edit_cancel_id', None)
            st.rerun()

        st.markdown("---")
    else:
        st.warning("수정할 해지 내역을 찾을 수 없습니다.")
        st.session_state.pop('edit_cancel_id', None)

# ── 삭제 확인 ────────────────────────────────────────────────────
del_cancel_id = st.session_state.get('del_cancel_id')
if del_cancel_id and not edit_cancel_id:
    cd = next((c for c in cancels_all if c['id'] == del_cancel_id), None)
    if cd is None:
        cd = db.get_cancellation(del_cancel_id)

    if cd:
        bno = str(cd.get('building_no') or '')
        uno = str(cd.get('unit_no') or '')
        dong_ho_d = f"{bno}동 {uno}" if bno else uno
        st.warning(
            f"**삭제 확인:** {cd.get('cancel_date', '-')} | {dong_ho_d} | "
            f"{cd.get('customer_name', '-')} | 환불 {cd.get('refund_amount', 0):,}원  \n"
            f"삭제 후 해당 호실 상태가 **'공실'**로 변경됩니다."
        )
        confirm_del = st.checkbox(
            "위 해지 내역을 삭제하고 호실 상태를 '공실'로 되돌립니다. (취소 불가)",
            key="del_cancel_chk",
        )
        dc1, dc2, _ = st.columns([1, 1, 4])
        if dc1.button("🗑️ 삭제 확인", type="primary", disabled=not confirm_del, key="btn_cdel_ok"):
            db.delete_cancellation(del_cancel_id)
            st.session_state.pop('del_cancel_id', None)
            st.session_state.pop('del_cancel_chk', None)
            st.session_state['_clist_ok'] = "🗑️ 삭제 완료 (호실 상태 → 공실)"
            st.rerun()
        if dc2.button("❌ 취소", key="btn_cdel_cancel"):
            st.session_state.pop('del_cancel_id', None)
            st.rerun()
        st.markdown("---")
    else:
        st.session_state.pop('del_cancel_id', None)

# ── 알림 ─────────────────────────────────────────────────────────
if st.session_state.get("_clist_ok"):
    st.success(st.session_state.pop("_clist_ok"))

if not cancels_all:
    st.info("조건에 맞는 해지 내역이 없습니다.")
    st.stop()

# ── 테이블 ────────────────────────────────────────────────────────
COL_W   = [0.6, 0.7, 0.8, 1.0, 1.3, 1.1, 1.1, 1.4, 1.2, 1.6, 0.5, 0.5]
HEADERS = ["동", "호수", "타입", "해지접수일", "계약자명", "연락처",
           "환불은행", "계좌번호", "환불금액", "비고", "", ""]

hdr_cols = st.columns(COL_W)
for label, col in zip(HEADERS, hdr_cols):
    col.markdown(f"**{label}**")
st.markdown("---")

for c in cancels_all:
    row = st.columns(COL_W)
    row[0].write(str(c.get('building_no') or ''))
    row[1].write(str(c.get('unit_no') or ''))
    row[2].write(str(c.get('unit_type') or ''))
    row[3].write(str(c.get('cancel_date') or ''))
    row[4].write(str(c.get('customer_name') or ''))
    row[5].write(str(c.get('phone') or ''))
    row[6].write(str(c.get('bank') or ''))
    row[7].write(str(c.get('account_no') or ''))
    row[8].write(f"{c.get('refund_amount', 0) or 0:,}")
    row[9].write(str(c.get('notes') or ''))

    if row[10].button("✏️", key=f"cedit_{c['id']}", help="수정"):
        for k in list(st.session_state.keys()):
            if k.startswith('edt_'):
                del st.session_state[k]
        st.session_state['edit_cancel_id'] = c['id']
        st.session_state.pop('del_cancel_id', None)
        st.rerun()

    if row[11].button("🗑️", key=f"cdel_{c['id']}", help="삭제"):
        st.session_state['del_cancel_id'] = c['id']
        st.session_state.pop('edit_cancel_id', None)
        st.rerun()

st.markdown("---")

# ── 요약 ─────────────────────────────────────────────────────────
total_count  = len(cancels_all)
total_refund = sum(c.get('refund_amount', 0) or 0 for c in cancels_all)
m1, m2 = st.columns(2)
m1.metric("총 해지 건수", f"{total_count}건")
m2.metric("총 환불액",   f"{total_refund:,}원")

# ── 엑셀 다운로드 ─────────────────────────────────────────────────
excel_rows = []
for c in cancels_all:
    excel_rows.append({
        "동":       c.get('building_no') or '',
        "호수":     c.get('unit_no') or '',
        "타입":     c.get('unit_type') or '',
        "해지접수일": c.get('cancel_date') or '',
        "계약자명": c.get('customer_name') or '',
        "연락처":   c.get('phone') or '',
        "환불은행": c.get('bank') or '',
        "계좌번호": c.get('account_no') or '',
        "환불금액": c.get('refund_amount', 0) or 0,
        "비고":     c.get('notes') or '',
    })

df_excel = pd.DataFrame(excel_rows)
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine='openpyxl') as writer:
    df_excel.to_excel(writer, index=False, sheet_name='해지리스트')
buf.seek(0)
st.download_button(
    "📥 엑셀 다운로드",
    data=buf,
    file_name=f"해지리스트_{start_date}_{end_date}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
