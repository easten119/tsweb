"""ui/unit_card.py — 호실 카드: 계약정보 편집 · 납부현황 · 입출금 · 이력 (현황판/계약관리 공용)"""
from datetime import date

import pandas as pd
import streamlit as st

import db
import templates
from ui import common as cm
from ui import money

STATE_KEY = '_unit_card'   # 현재 열린 호실 id


def open_card(unit_id):
    st.session_state[STATE_KEY] = unit_id


def close_card():
    st.session_state.pop(STATE_KEY, None)


def _price_value(unit, key):
    if key in templates.UNIT_COLUMNS:
        return unit.get(key) or 0
    return db.unit_extra(unit).get(key) or 0


def _field_input(f, value, key, disabled):
    t = f.get('type', 'text')
    label = f['label']
    if t == 'date':
        return st.date_input(label, value=cm.to_date(value), key=key, disabled=disabled, format="YYYY-MM-DD")
    if t in ('number', 'money'):
        return st.number_input(label, value=int(value or 0), step=10000 if t == 'money' else 1, min_value=0,
                               format="%d", key=key, disabled=disabled)
    if t == 'select':
        opts = [''] + list(f.get('options') or [])
        if value and value not in opts:
            opts.append(value)
        return st.selectbox(label, opts, index=opts.index(value or ''), key=key, disabled=disabled)
    if t == 'check':
        return st.checkbox(label, value=bool(value), key=key, disabled=disabled)
    return st.text_input(label, value=value or '', key=key, disabled=disabled)


def render(ctx, unit_id, show_close=True):
    site_id, cfg, editable = ctx['site_id'], ctx['cfg'], ctx['editable']
    unit = db.get_unit(unit_id)
    if not unit or unit['site_id'] != site_id:
        close_card()
        return
    ct = db.get_active_contract(unit_id)
    colors = templates.status_colors(cfg)
    bg, fg = colors.get(unit['status'], ('#999', '#fff'))

    head, close = st.columns([10, 1])
    with head:
        prices = " · ".join(f"{p['label']} {cm.won(_price_value(unit, p['key']))}" for p in cfg['price_fields'])
        st.markdown(
            f"<div class='ts-section' style='margin-top:4px'>{unit['building_no']}동 {unit['unit_no']}호 "
            f"<span style='background:{bg};color:{fg};border:1px solid #ccc;padding:1px 8px;border-radius:3px;"
            f"font-size:12px;margin-left:6px'>{unit['status']}</span>"
            f"<span style='font-weight:400;color:#6B7686;font-size:12px;margin-left:10px'>"
            f"타입 {unit.get('type') or '-'} · {prices}</span></div>", unsafe_allow_html=True)
    if show_close and close.button("닫기", key=f"uc_close_{unit_id}", icon=":material/close:"):
        close_card()
        st.rerun()

    t_info, t_pay, t_tx, t_hist = st.tabs(["계약정보", "납부현황", "입출금", "이력"])
    with t_info:
        _contract_form(ctx, unit, ct)
    with t_pay:
        _payments(ctx, unit)
    with t_tx:
        _transactions(ctx, unit, ct)
    with t_hist:
        _history(unit)


def _contract_form(ctx, unit, ct):
    site_id, cfg, editable = ctx['site_id'], ctx['cfg'], ctx['editable']
    ct = ct or {}
    extra = db._jload(ct.get('extra'))
    fvals, dvals = extra.get('fields', {}), extra.get('docs', {})
    employees = db.get_employees(site_id)
    teams = sorted({e['team'] for e in employees if e.get('team')})
    k = f"uc_{unit['id']}_{ct.get('id', 'new')}"
    statuses = templates.status_names(cfg)
    disabled = not editable
    if not ct and editable:
        st.caption("유효한 계약이 없습니다. 아래에 입력하면 신규 계약으로 등록됩니다.")

    with st.form(f"{k}_form"):
        c = st.columns(4)
        status = c[0].selectbox("상태", statuses, disabled=disabled,
                                index=statuses.index(ct['contract_type']) if ct.get('contract_type') in statuses else 0)
        name = c[1].text_input("계약자명 *", value=ct.get('customer_name') or '', disabled=disabled)
        birth = c[2].date_input("생년월일", value=cm.to_date(ct.get('birth_date')), min_value=date(1920, 1, 1),
                                max_value=date.today(), disabled=disabled, format="YYYY-MM-DD")
        phone = c[3].text_input("연락처", value=ct.get('phone') or '', disabled=disabled)
        address = st.text_input("주소", value=ct.get('address') or '', disabled=disabled)

        c = st.columns(4)
        pre_date = c[0].date_input("가계약일", value=cm.to_date(ct.get('pre_date')), disabled=disabled, format="YYYY-MM-DD")
        planned = c[1].date_input("계약예정일", value=cm.to_date(ct.get('planned_date')), disabled=disabled,
                                  format="YYYY-MM-DD")
        cdate = c[2].date_input("계약일", value=cm.to_date(ct.get('contract_date')), disabled=disabled,
                                format="YYYY-MM-DD")
        deposit = c[3].number_input("계약금", value=int(ct.get('deposit_total') or 0), min_value=0, step=100000,
                                    format="%d", disabled=disabled)

        c = st.columns(4)
        cur_team = ct.get('assigned_team') or ''
        team_opts = [''] + teams + ([cur_team] if cur_team and cur_team not in teams else [])
        team = c[0].selectbox("담당팀", team_opts, index=team_opts.index(cur_team), disabled=disabled)
        staff_names = sorted({e['name'] for e in employees if not team or e.get('team') == team})
        cur_staff = ct.get('assigned_staff') or ''
        staff_opts = [''] + staff_names + ([cur_staff] if cur_staff and cur_staff not in staff_names else [])
        staff = c[1].selectbox("담당자", staff_opts, index=staff_opts.index(cur_staff), disabled=disabled)

        # 현장 양식의 기타 항목: 담당팀·담당자 옆 빈칸부터 4칸씩 채움
        new_fields = {}
        slots = [c[2], c[3]]
        for i, f in enumerate(cfg['fields']):
            if i >= len(slots):
                slots += list(st.columns(4))
            with slots[i]:
                new_fields[f['label']] = _field_input(f, fvals.get(f['label']), f"{k}_f{i}", disabled)
        # 호실 가격 (양식 항목)
        new_prices = {}
        if cfg['price_fields']:
            cols = st.columns(4)
            for i, p in enumerate(cfg['price_fields']):
                new_prices[p['key']] = cols[i % 4].number_input(
                    p['label'], value=int(_price_value(unit, p['key']) or 0), min_value=0, step=1_000_000,
                    format="%d", disabled=disabled, key=f"{k}_p{i}")
        # 서류
        new_docs = {}
        if cfg['docs']:
            st.markdown("<div style='font-size:12px;color:#6B7686;margin-top:4px'>서류</div>", unsafe_allow_html=True)
            cols = st.columns(min(len(cfg['docs']), 6))
            for i, d in enumerate(cfg['docs']):
                new_docs[d] = cols[i % len(cols)].checkbox(d, value=bool(dvals.get(d)), disabled=disabled,
                                                           key=f"{k}_d{i}")
        c = st.columns(2)
        notes = c[0].text_input("비고1", value=ct.get('notes') or '', disabled=disabled)
        notes2 = c[1].text_input("비고2", value=ct.get('notes2') or '', disabled=disabled)

        submitted = st.form_submit_button("저장" if ct else "신규 계약 등록", type="primary", disabled=disabled)

    if submitted:
        if not name.strip():
            st.error("계약자명을 입력하세요.")
            return
        data = {
            'customer_name': name.strip(), 'phone': phone.strip() or None, 'birth_date': cm.date_str(birth),
            'address': address.strip() or None, 'contract_type': status,
            'pre_date': cm.date_str(pre_date), 'planned_date': cm.date_str(planned),
            'contract_date': cm.date_str(cdate), 'deposit_total': int(deposit),
            'assigned_team': team or None, 'assigned_staff': staff or None,
            'notes': notes.strip() or None, 'notes2': notes2.strip() or None,
            'extra': {'fields': {k2: (cm.date_str(v) if isinstance(v, date) else v) for k2, v in new_fields.items()
                                 if v not in (None, '', False, 0)},
                      'docs': {k2: True for k2, v in new_docs.items() if v}},
        }
        changed_prices = {key: v for key, v in new_prices.items() if int(_price_value(unit, key) or 0) != v}
        try:
            db.apply_sheet_changes(site_id, [{'unit_id': unit['id'], 'unit': changed_prices, 'contract': data}])
        except ValueError as e:
            st.error(str(e))
            return
        cm.flash(f"{unit['building_no']}동 {unit['unit_no']}호 — {'저장' if ct else '신규 등록'} 완료")
        st.rerun()

    if ct and editable:
        a, b, _ = st.columns([1.3, 1.6, 5])
        if a.button("해지 처리", key=f"{k}_cancel", icon=":material/block:"):
            st.session_state['_cancel_unit'] = unit['id']
            st.session_state['site_tab'] = '해지'
            st.rerun()
        with b.popover("잘못 등록한 계약 삭제"):
            st.caption("실제 해지는 '해지 처리'를 사용하세요. 삭제하면 계약 기록이 남지 않습니다.")
            if st.button("삭제", type="primary", key=f"{k}_del"):
                db.delete_contract(ct['id'])
                cm.flash("계약이 삭제되었습니다.")
                st.rerun()


def _payments(ctx, unit):
    cfg = ctx['cfg']
    txs = db.get_transactions(unit_id=unit['id'])
    rows = []
    for item in cfg['payment_items'] + ['(항목 미지정)']:
        sel = [t for t in txs if (t.get('item') or '(항목 미지정)') == item]
        if not sel and item == '(항목 미지정)':
            continue
        amt = sum(t['amount'] if t['type'] == '입금' else -t['amount'] for t in sel)
        dates = sorted(t['date'] for t in sel if t['type'] == '입금')
        rows.append({'입금항목': item, '납부액': amt, '최초 납부일': dates[0] if dates else '',
                     '최근 납부일': dates[-1] if dates else '', '건수': len(sel)})
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, placeholder="", width="stretch", column_config={'납부액': cm.MONEY})
    total_in = sum(t['amount'] for t in txs if t['type'] == '입금')
    total_out = sum(t['amount'] for t in txs if t['type'] == '출금')
    st.caption(f"입금 {total_in:,}원 · 출금 {total_out:,}원 · 잔액 {total_in - total_out:,}원  —  "
               "입출금 등록 때 '입금항목'을 고르면 항목별로 집계됩니다.")


def _transactions(ctx, unit, ct):
    site_id, cfg, editable = ctx['site_id'], ctx['cfg'], ctx['editable']
    txs = db.get_transactions(unit_id=unit['id'])
    if txs:
        st.dataframe(pd.DataFrame([{
            '날짜': t['date'], '구분': t['type'], '입금항목': t.get('item') or '', '금액': t['amount'],
            '입금자': t.get('depositor') or '', '계좌': t.get('account') or '',
            '출금사유': t.get('out_reason') or '', '비고': t.get('notes') or ''} for t in txs]),
            hide_index=True, placeholder="", width="stretch", column_config={'금액': cm.MONEY})
    else:
        st.caption("입출금 내역 없음")
    if not editable:
        return
    n = money.round_of(f"_uctx_{unit['id']}")
    k = f"uctx_{unit['id']}_{n}"
    name = (ct or {}).get('customer_name') or ''
    c = st.columns([1.1, 0.8, 1.2, 1.5, 1.1, 1.1])
    d = c[0].date_input("날짜", value=date.today(), format="YYYY-MM-DD", key=f"{k}_d")
    ttype = c[1].selectbox("구분", ["입금", "출금"], key=f"{k}_t")
    item = c[2].selectbox("입금항목", [''] + cfg['payment_items'], key=f"{k}_i")
    with c[3]:
        amt = money.money_input("금액", key=f"{k}_a")
    dep = c[4].text_input("입금자", value=name, key=f"{k}_dep")
    acc = c[5].text_input("입금계좌", key=f"{k}_acc")
    c2 = st.columns(2)
    rsn = c2[0].text_input("출금사유", key=f"{k}_r")
    nts = c2[1].text_input("비고", key=f"{k}_n")
    if st.button("입출금 추가", key=f"{k}_save", icon=":material/add:"):
        if not amt:
            st.error("금액을 입력하세요.")
        elif ttype == '출금' and not rsn.strip():
            st.error("출금사유를 입력하세요.")
        else:
            db.add_transaction(site_id, str(d), depositor=dep.strip() or None, customer=name or None,
                               account=acc.strip() or None, amount=amt, tx_type=ttype, notes=nts.strip() or None,
                               unit_id=unit['id'], out_reason=(rsn.strip() or None) if ttype == '출금' else None,
                               item=item or None)
            money.next_round(f"_uctx_{unit['id']}")
            cm.flash(f"{ttype} {amt:,}원 추가")
            st.rerun()


def _history(unit):
    contracts = db.get_contracts(unit_id=unit['id'])
    cancels = db.get_cancellations(unit_id=unit['id'])
    if contracts:
        st.dataframe(pd.DataFrame([{
            '상태': c.get('status'), '구분': c.get('contract_type'), '계약자': c.get('customer_name'),
            '가계약일': c.get('pre_date') or '', '계약일': c.get('contract_date') or '',
            '해지일': c.get('cancelled_at') or '', '담당': f"{c.get('assigned_team') or ''} {c.get('assigned_staff') or ''}"}
            for c in contracts]), hide_index=True, placeholder="", width="stretch")
    if cancels:
        st.dataframe(pd.DataFrame([{
            '해지접수일': c.get('cancel_date'), '계약자': c.get('customer_name') or '(계약정보 없음)',
            '환불금액': c.get('refund_amount') or 0, '환불은행': c.get('bank') or '', '비고': c.get('notes') or ''}
            for c in cancels]), hide_index=True, placeholder="", width="stretch", column_config={'환불금액': cm.MONEY})
    if not contracts and not cancels:
        st.caption("이력 없음")
