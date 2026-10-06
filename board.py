"""
board.py — 동호수 현황판 (엑셀 '계약현황판' 구도)

제목줄 · 상태별 건수 배지 · 층별 호실(상태 색은 현장 양식 설정) · 특수층 이름(스카이라운지·근린생활시설 등)
· ✕(피난층 등 호실 없는 층) · 라인 번호 · 타입 색상 행 · 동 번호 · 좌측 층 구간(1군~8군 등)
클릭은 st.components.v2 컴포넌트로 받아 iframe 없이 처리한다 (로그인 유지).
"""
import html
import math
from datetime import datetime

import streamlit as st

DEFAULT_COLORS = {'계약': ('#E00000', '#FFFFFF'), '가계약': ('#00A0E9', '#FFFFFF'), '공실': ('#FFFFFF', '#222222')}
TYPE_PALETTE = ['#1E7BE6', '#22C55E', '#F27BA0', '#A57BE8', '#F59E0B', '#14B8A6', '#EF4444', '#84CC16',
                '#0EA5E9', '#D946EF']
ROW_H = 17      # 호실 행 높이(px) — 좌측 층 구간 칸과 맞추기 위해 고정
TYPE_H = 24

CSS = f"""
.tsb {{ font-family: 'Malgun Gothic', 'Noto Sans KR', sans-serif; color:#222; background:#fff; padding:8px;
        border:1px solid #DDE2E9; border-radius:4px; }}
.tsb .title {{ background:#0B1F4D; color:#fff; text-align:center; font-weight:800; font-size:17px;
              padding:7px 0; letter-spacing:1px; }}
.tsb .summary {{ display:flex; align-items:center; gap:16px; padding:8px 4px 12px; flex-wrap:wrap; font-size:13px; }}
.tsb .badge {{ display:inline-block; color:#fff; font-weight:700; padding:2px 10px; margin-right:5px; font-size:12px; }}
.tsb .cnt {{ font-weight:800; font-size:16px; }}
.tsb .stamp {{ margin-left:auto; color:#666; font-size:11px; }}
.tsb .rows {{ display:flex; flex-direction:column; gap:24px; overflow-x:auto; }}
.tsb .row {{ display:flex; gap:30px; align-items:flex-end; }}
.tsb table {{ border-collapse:collapse; table-layout:fixed; flex-shrink:0; }}
.tsb td {{ border:1px solid #9a9a9a; width:46px; min-width:46px; height:{ROW_H}px; padding:0; text-align:center;
          font-size:10.5px; white-space:nowrap; overflow:hidden; line-height:{ROW_H}px; }}
.tsb td.u {{ cursor:pointer; }}
.tsb td.u:hover {{ outline:2px solid #111; outline-offset:-2px; }}
.tsb td.sel {{ outline:3px solid #FFC400; outline-offset:-3px; font-weight:800; }}
.tsb td.dim {{ opacity:.22; }}
.tsb td.x {{ background-color:#fff;
            background-image:linear-gradient(to top right, transparent calc(50% - .6px), #555 50%, transparent calc(50% + .6px)),
                             linear-gradient(to bottom right, transparent calc(50% - .6px), #555 50%, transparent calc(50% + .6px)); }}
.tsb td.lbl {{ background:#fff; }}
.tsb tr.gap td {{ border:none; height:8px; }}
.tsb td.line {{ font-size:10px; }}
.tsb td.type {{ font-weight:700; color:#111; height:{TYPE_H}px; line-height:{TYPE_H}px; }}
.tsb td.bno {{ font-weight:800; font-size:12px; border-top:2px solid #333; }}
.tsb table.gut td {{ border:1px solid transparent; width:34px; min-width:34px; overflow:visible; }}
.tsb table.gut td.g {{ background:#F3F5F8; border-left:1px solid #9a9a9a; border-right:1px solid #9a9a9a;
                      font-weight:700; font-size:11px; }}
.tsb table.gut td.gt {{ border-top:1px solid #9a9a9a; }}
.tsb table.gut td.gb {{ border-bottom:1px solid #9a9a9a; }}
.tsb table.gut tr.gap td {{ border:none; }}
.tsb table.gut td.bt {{ border-top:2px solid transparent; }}
.tsb .legend {{ display:flex; gap:12px; font-size:11px; color:#555; margin-top:12px; flex-wrap:wrap; }}
.tsb .legend i {{ display:inline-block; width:12px; height:12px; border:1px solid #999; vertical-align:-2px; margin-right:3px; }}
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

def _get_component():
    # 매 실행마다 등록한다: 정의가 같으면 경고 없이 덮어쓰고, 런타임 레지스트리가 초기화돼도 안전하다.
    return st.components.v2.component("ts_unit_board", css=CSS, js=JS)


def parse_unit_no(unit_no):
    """'4601' → (46, 1). 숫자 3자리 이상만 인식."""
    s = str(unit_no).strip()
    if len(s) >= 3 and s.isdigit():
        return int(s[:-2]), int(s[-2:])
    return None, None


def type_colors(units):
    types = sorted({u['type'] for u in units if u.get('type')})
    return {t: TYPE_PALETTE[i % len(TYPE_PALETTE)] for i, t in enumerate(types)}


def _top_floor(units, labels):
    floors = [f for u in units for f, _ in [parse_unit_no(u['unit_no'])] if f is not None]
    return max(floors + list(labels or {}) + [0])


def _building_table(bld, units, labels, customers, sel_uid, type_filter, tcolors, colors, top):
    e = html.escape
    parsed = [(f, l, u) for u in units for f, l in [parse_unit_no(u['unit_no'])] if f is not None]
    if not parsed:
        return f'<table><tr><td class="lbl" style="width:190px">{e(str(bld["building_no"]))}동 · 호실 없음</td></tr></table>'
    lines = sorted({l for _, l, _ in parsed})
    umap = {(f, l): u for f, l, u in parsed}
    unit_floors = {f for f, _, _ in parsed}
    my_top = max(max(unit_floors), max(labels) if labels else 0)
    n = len(lines)
    rows = []
    for f in range(my_top, 0, -1):
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
            bg, fg = colors.get(u['status'], colors.get('공실', ('#fff', '#222')))
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


def _gutter(top, groups):
    """좌측 층 구간 표시 (예: 1~3층 '1군'). 층마다 한 칸씩 그려 동 표와 행 높이를 정확히 맞춘다."""
    e = html.escape
    by_floor = {}
    for g in groups:
        lo, hi = int(g['from']), int(g['to'])
        for f in range(lo, hi + 1):
            by_floor[f] = (g['label'], lo, hi)
    rows = []
    for f in range(top, 0, -1):
        g = by_floor.get(f)
        if not g:
            rows.append('<tr><td></td></tr>')
            continue
        label, lo, hi = g
        cls = 'g' + (' gt' if f == min(hi, top) else '') + (' gb' if f == lo else '')
        mid = (min(hi, top) + lo) // 2
        rows.append(f'<tr><td class="{cls}" title="{lo}~{hi}층">{e(label) if f == mid else ""}</td></tr>')
    rows.append('<tr class="gap"><td></td></tr><tr><td></td></tr>'
                f'<tr><td style="height:{TYPE_H}px"></td></tr><tr><td class="bt"></td></tr>')
    return '<table class="gut">' + ''.join(rows) + '</table>'


def board_html(site, buildings, units, labels_by_bld, customers, sel_uid=None, type_filter=None,
               standalone=False, colors=None, statuses=None, floor_groups=None):
    e = html.escape
    colors = colors or DEFAULT_COLORS
    statuses = statuses or ['계약', '가계약']
    by_bld = {}
    for u in units:
        by_bld.setdefault(u['building_id'], []).append(u)
    tcolors = type_colors(units)
    counts = {s: sum(1 for u in units if u['status'] == s) for s in statuses}
    total = len(units)
    signed = sum(counts.values())
    rate = f"{signed / total * 100:.1f}%" if total else "-"

    n = len(buildings)
    per_row = n if n <= 4 else math.ceil(n / 2)   # 4개 동 이하 1줄, 5개 이상 2줄
    row_html = []
    for i in range(0, n, per_row):
        group = buildings[i:i + per_row]
        top = max(_top_floor(by_bld.get(b['id'], []), labels_by_bld.get(b['id'], {})) for b in group)
        tables = [_building_table(b, by_bld.get(b['id'], []), labels_by_bld.get(b['id'], {}), customers,
                                  sel_uid, type_filter, tcolors, colors, top) for b in group]
        gut = _gutter(top, floor_groups) if floor_groups else ''
        row_html.append('<div class="row">' + gut + ''.join(tables) + '</div>')

    # 계약 → 가계약 → 기타 순으로 배지
    order = sorted(statuses, key=lambda s: (s != '계약', s != '가계약'))
    badges = ''.join(
        f'<span><span class="badge" style="background:{colors.get(s, ("#999",))[0]}">'
        f'{"정계약" if s == "계약" else e(s)}</span><span class="cnt">{counts[s]}</span> 건</span>' for s in order)
    legend = ''.join(f'<span><i style="background:{c}"></i>{e(t)}</span>' for t, c in tcolors.items())
    body = (
        f'<div class="tsb"><div class="title">{e(site["name"])} 동호수현황판</div>'
        f'<div class="summary">{badges}'
        f'<span>공실 <b>{total - signed}</b> / 총 {total}세대 · 계약률 <b>{rate}</b></span>'
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


def render_board(site, buildings, units, labels_by_bld, customers, sel_uid=None, type_filter=None, key="board",
                 **opts):
    """현황판을 그리고, 이번 실행에서 클릭된 호실 id(int)를 반환 (없으면 None)."""
    body = board_html(site, buildings, units, labels_by_bld, customers, sel_uid, type_filter, **opts)
    result = _get_component()(data=body, key=key, on_clicked_change=lambda: None)
    clicked = getattr(result, 'clicked', None)
    try:
        return int(clicked) if clicked else None
    except (TypeError, ValueError):
        return None
