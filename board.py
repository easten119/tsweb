"""
board.py — 동호수 현황판 (엑셀 '계약현황판' 구도)

제목줄 · 정계약/가계약 건수 배지 · 층별 호실(계약 빨강 / 가계약 파랑)
· 특수층 이름(스카이라운지·옥상정원·근린생활시설 등) · ✕(피난층 등 호실 없는 층)
· 라인 번호 · 타입 색상 행 · 동 번호
클릭은 st.components.v2 컴포넌트로 받아 iframe 없이 처리한다 (로그인 유지).
"""
import html
import math
from datetime import datetime

import streamlit as st

STATUS_COLOR = {'계약': ('#E00000', '#FFFFFF'), '가계약': ('#00A0E9', '#FFFFFF'), '공실': ('#FFFFFF', '#222222')}
TYPE_PALETTE = ['#1E7BE6', '#22C55E', '#F27BA0', '#A57BE8', '#F59E0B', '#14B8A6', '#EF4444', '#84CC16',
                '#0EA5E9', '#D946EF']

CSS = """
.tsb { font-family: 'Malgun Gothic', -apple-system, sans-serif; color:#222; background:#fff; padding:6px; }
.tsb .title { background:#0B1F4D; color:#fff; text-align:center; font-weight:800; font-size:18px;
              padding:8px 0; letter-spacing:1px; }
.tsb .summary { display:flex; align-items:center; gap:18px; padding:8px 4px 12px; flex-wrap:wrap; font-size:13px; }
.tsb .badge { display:inline-block; color:#fff; font-weight:700; padding:3px 12px; margin-right:6px; font-size:12px; }
.tsb .cnt { font-weight:800; font-size:16px; }
.tsb .stamp { margin-left:auto; color:#666; font-size:11px; }
.tsb .rows { display:flex; flex-direction:column; gap:24px; overflow-x:auto; }
.tsb .row { display:flex; gap:36px; align-items:flex-end; }
.tsb table { border-collapse:collapse; table-layout:fixed; flex-shrink:0; }
.tsb td { border:1px solid #9a9a9a; width:46px; min-width:46px; height:17px; padding:0; text-align:center;
          font-size:10.5px; white-space:nowrap; overflow:hidden; line-height:17px; }
.tsb td.u { cursor:pointer; }
.tsb td.u:hover { outline:2px solid #111; outline-offset:-2px; }
.tsb td.sel { outline:3px solid #FFC400; outline-offset:-3px; font-weight:800; }
.tsb td.dim { opacity:.22; }
.tsb td.x { background-color:#fff;
            background-image:linear-gradient(to top right, transparent calc(50% - .6px), #555 50%, transparent calc(50% + .6px)),
                             linear-gradient(to bottom right, transparent calc(50% - .6px), #555 50%, transparent calc(50% + .6px)); }
.tsb td.lbl { background:#fff; }
.tsb tr.gap td { border:none; height:8px; }
.tsb td.line { font-size:10px; }
.tsb td.type { font-weight:700; color:#111; height:24px; line-height:24px; }
.tsb td.bno { font-weight:800; font-size:12px; border-top:2px solid #333; }
.tsb .legend { display:flex; gap:12px; font-size:11px; color:#555; margin-top:12px; flex-wrap:wrap; }
.tsb .legend i { display:inline-block; width:12px; height:12px; border:1px solid #999; vertical-align:-2px; margin-right:3px; }
"""

JS = """
export default function(component) {
    const { data, setTriggerValue, parentElement } = component;
    let root = parentElement.querySelector('.tsb-root');
    if (!root) { root = document.createElement('div'); root.className = 'tsb-root'; parentElement.appendChild(root); }
    root.innerHTML = data;
    root.querySelectorAll('td[data-uid]').forEach((td) => {
        td.onclick = () => setTriggerValue('clicked', td.getAttribute('data-uid'));
    });
}
"""

_component = None


def _get_component():
    global _component
    if _component is None:
        _component = st.components.v2.component("ts_unit_board", css=CSS, js=JS)
    return _component


def parse_unit_no(unit_no):
    """'4601' → (46, 1). 숫자 3자리 이상만 인식."""
    s = str(unit_no).strip()
    if len(s) >= 3 and s.isdigit():
        return int(s[:-2]), int(s[-2:])
    return None, None


def type_colors(units):
    types = sorted({u['type'] for u in units if u.get('type')})
    return {t: TYPE_PALETTE[i % len(TYPE_PALETTE)] for i, t in enumerate(types)}


def _building_table(bld, units, labels, customers, sel_uid, type_filter, tcolors):
    e = html.escape
    parsed = [(f, l, u) for u in units for f, l in [parse_unit_no(u['unit_no'])] if f is not None]
    if not parsed:
        return f'<table><tr><td class="lbl" style="width:190px">{e(str(bld["building_no"]))}동 · 호실 없음</td></tr></table>'
    lines = sorted({l for _, l, _ in parsed})
    umap = {(f, l): u for f, l, u in parsed}
    unit_floors = {f for f, _, _ in parsed}
    top = max(max(unit_floors), max(labels) if labels else 0)
    n = len(lines)
    rows = []
    for f in range(top, 0, -1):
        if f not in unit_floors:
            if f in labels:
                rows.append(f'<tr><td class="lbl" colspan="{n}" title="{f}층">{e(labels[f])}</td></tr>')
            else:
                rows.append('<tr>' + f'<td class="x" title="{f}층"></td>' * n + '</tr>')
            continue
        cells = []
        for l in lines:
            u = umap.get((f, l))
            if not u:
                cells.append('<td class="x"></td>')
                continue
            bg, fg = STATUS_COLOR.get(u['status'], STATUS_COLOR['공실'])
            cls = ['u']
            if sel_uid and u['id'] == sel_uid:
                cls.append('sel')
            if type_filter and u.get('type') != type_filter:
                cls.append('dim')
            tip = f"{bld['building_no']}-{u['unit_no']} · {u.get('type') or '-'} · {u['status']}"
            if customers.get(u['id']):
                tip += f" · {customers[u['id']]}"
            bold = "font-weight:700;" if u['status'] != '공실' else ""
            cells.append(f'<td class="{" ".join(cls)}" data-uid="{u["id"]}" title="{e(tip)}" '
                         f'style="background:{bg};color:{fg};{bold}">{e(str(u["unit_no"]))}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')

    rows.append('<tr class="gap">' + '<td></td>' * n + '</tr>')
    rows.append('<tr>' + ''.join(f'<td class="line">{l}</td>' for l in lines) + '</tr>')
    type_cells = []
    for l in lines:
        ts = []
        for f in sorted(unit_floors, reverse=True):
            t = (umap.get((f, l)) or {}).get('type')
            if t and t not in ts:
                ts.append(t)
        color = tcolors.get(ts[0], '#ddd') if ts else '#fff'
        type_cells.append(f'<td class="type" style="background:{color}">{e("/".join(ts[:2]))}</td>')
    rows.append('<tr>' + ''.join(type_cells) + '</tr>')
    rows.append(f'<tr><td class="bno" colspan="{n}">{e(str(bld["building_no"]))}</td></tr>')
    return '<table>' + ''.join(rows) + '</table>'


def board_html(site, buildings, units, labels_by_bld, customers, sel_uid=None, type_filter=None,
               standalone=False):
    e = html.escape
    by_bld = {}
    for u in units:
        by_bld.setdefault(u['building_id'], []).append(u)
    tcolors = type_colors(units)
    n_ct = sum(1 for u in units if u['status'] == '계약')
    n_pre = sum(1 for u in units if u['status'] == '가계약')
    total = len(units)
    rate = f"{(n_ct + n_pre) / total * 100:.1f}%" if total else "-"

    n = len(buildings)
    per_row = n if n <= 4 else math.ceil(n / 2)   # 4개 동 이하 1줄, 5개 이상 2줄
    row_html = []
    for i in range(0, n, per_row):
        tables = [_building_table(b, by_bld.get(b['id'], []), labels_by_bld.get(b['id'], {}), customers,
                                  sel_uid, type_filter, tcolors) for b in buildings[i:i + per_row]]
        row_html.append('<div class="row">' + ''.join(tables) + '</div>')

    legend = ''.join(f'<span><i style="background:{c}"></i>{e(t)}</span>' for t, c in tcolors.items())
    body = (
        f'<div class="tsb"><div class="title">{e(site["name"])} 동호수현황판</div>'
        f'<div class="summary">'
        f'<span><span class="badge" style="background:#E00000">정계약</span><span class="cnt">{n_ct}</span> 건</span>'
        f'<span><span class="badge" style="background:#00A0E9">가계약</span><span class="cnt">{n_pre}</span> 건</span>'
        f'<span>공실 <b>{total - n_ct - n_pre}</b> / 총 {total}세대 · 계약률 <b>{rate}</b></span>'
        f'<span class="stamp">{datetime.now():%Y-%m-%d %H:%M}</span></div>'
        f'<div class="rows">{"".join(row_html)}</div>'
        f'<div class="legend"><span>✕ 호실 없는 층(피난층 등)</span>{legend}</div>'
        f'</div>'
    )
    if standalone:
        return (f'<!doctype html><html><head><meta charset="utf-8"><title>{e(site["name"])} 동호수현황판</title>'
                f'<style>body{{margin:12px}} @page{{size:A4 portrait;margin:6mm}} '
                f'@media print{{.tsb td{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}}} {CSS}</style>'
                f'</head><body>{body}</body></html>')
    return body


def render_board(site, buildings, units, labels_by_bld, customers, sel_uid=None, type_filter=None, key="board"):
    """현황판을 그리고, 이번 실행에서 클릭된 호실 id(int)를 반환 (없으면 None)."""
    body = board_html(site, buildings, units, labels_by_bld, customers, sel_uid, type_filter)
    result = _get_component()(data=body, key=key, on_clicked_change=lambda: None)
    clicked = getattr(result, 'clicked', None)
    try:
        return int(clicked) if clicked else None
    except (TypeError, ValueError):
        return None
