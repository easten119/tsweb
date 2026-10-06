"""
importer.py — 기존 엑셀 계약현황(main 시트 + 입출금 시트) 가져오기

1) 열 자동 매핑: 엑셀 헤더 이름 → 시스템 항목 (현장 계약 양식 기준). 화면에서 고칠 수 있다.
2) 미리보기: 호실 신규/갱신, 계약 신규/갱신, 납부(입출금) 생성 건수와 오류
3) 반영: 한 트랜잭션. 같은 파일을 다시 가져와도 중복 입출금이 생기지 않는다.
주민등록번호(등록번호) 열은 생년월일만 추출하고 나머지는 저장하지 않는다.
"""
import io
import re
from datetime import date, datetime, timedelta

import pandas as pd

import db
import templates

SKIP = '(사용 안 함)'
NO_NAME = '(계약자 미기재)'   # 상태만 있고 이름이 없는 행 (예: 소송 호실)
BASE_TARGETS = ['동', '호수', '동-호수', '타입', '층', '라인', '상태', '계약자명', '생년월일', '등록번호(생년월일만 추출)',
                '연락처', '주소', '가계약일', '계약예정일', '계약일', '담당팀', '담당자', '계약금', '비고1', '비고2']
ALIASES = {
    '동': ['동'], '호수': ['호수', '호'], '동-호수': ['동-호수', '동호수'], '타입': ['타입', 'type'],
    '층': ['층'], '라인': ['라인'], '상태': ['상태', '계약상태'], '계약자명': ['계약자명', '계약자', '고객명'],
    '생년월일': ['생년월일'], '등록번호(생년월일만 추출)': ['등록번호', '주민번호', '주민등록번호'],
    '연락처': ['연락처', '전화번호', '휴대폰'], '주소': ['주소'], '가계약일': ['가계약일자', '가계약일'],
    '계약예정일': ['계약예정일'], '계약일': ['계약일자', '계약일'], '담당팀': ['담당팀', '팀'],
    '담당자': ['담당자'], '계약금': ['계약금'], '비고1': ['비고1', '비고'], '비고2': ['비고2'],
}


def _key(s):
    return re.sub(r'\s+', '', str(s or '')).lower()


def targets(cfg):
    t = [SKIP] + BASE_TARGETS
    t += [f"가격: {p['label']}" for p in cfg['price_fields']]
    t += [f"기타: {f['label']}" for f in cfg['fields']]
    t += [f"서류: {d}" for d in cfg['docs']]
    for item in cfg['payment_items']:
        t += [f"납부액: {item}", f"납부일: {item}"]
    return t


def auto_map(headers, cfg):
    """헤더 → 대상 항목 자동 추정. 같은 이름 열이 두 번 나오면(예: 업무대행비 = 호실 가격 / 납부액)
    앞 열부터 가격 → 납부액 순으로 배정한다."""
    cands = {}

    def add(name, tgt):
        lst = cands.setdefault(_key(name), [])
        if tgt not in lst:
            lst.append(tgt)
    for tgt, names in ALIASES.items():
        for n in names:
            add(n, tgt)
    for p in cfg['price_fields']:
        add(p['label'], f"가격: {p['label']}")
    for f in cfg['fields']:
        add(f['label'], f"기타: {f['label']}")
    for d in cfg['docs']:
        add(d, f"서류: {d}")
    for item in cfg['payment_items']:
        add(item, f"납부액: {item}")
        add(item + '납부일', f"납부일: {item}")
        add(re.sub(r'\s*계약금$', '', item) + '납부일', f"납부일: {item}")   # '1차 계약금' → '1차납부일'
        add(item + '일', f"납부일: {item}")                                   # '1차 납부' → '1차 납부일'
    used, result = set(), {}
    for h in headers:
        base = re.sub(r'\.\d+$', '', str(h))          # pandas가 붙인 중복 열 접미사 '.1' 제거
        tgt = next((t for t in cands.get(_key(base), []) if t not in used), SKIP)
        result[h] = tgt
        if tgt != SKIP:
            used.add(tgt)
    return result


def read_sheet(file_bytes, sheet):
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=0, dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how='all')


def _txt(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    return s or None


def _num(v):
    s = _txt(v)
    if s is None:
        return None
    try:
        return int(float(s.replace(',', '')))
    except ValueError:
        return None


def _date(v):
    if v is None:
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return None if pd.isna(v) else v.strftime('%Y-%m-%d')
    if isinstance(v, date):
        return v.isoformat()
    s = _txt(v)
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(s.split(' ')[0], fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    try:
        serial = float(s)
        if 20000 < serial < 80000:
            return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()
    except ValueError:
        pass
    return None


def birth_from_rrn(v):
    """주민등록번호 → 생년월일 (뒷자리는 버린다)."""
    s = re.sub(r'\D', '', _txt(v) or '')
    if len(s) < 7:
        return None
    yy, mm, dd, g = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6]
    century = {'1': 1900, '2': 1900, '5': 1900, '6': 1900, '3': 2000, '4': 2000, '7': 2000, '8': 2000,
               '9': 1800, '0': 1800}.get(g)
    if not century:
        return None
    try:
        return date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None


def _truthy(v):
    s = _txt(v)
    return bool(s) and s not in ('0', 'X', 'x', 'N', 'n', '×', '미', '미제출')


def _bld_unit(row, m):
    dong = _txt(row.get(m.get('동'))) if m.get('동') else None
    ho = _txt(row.get(m.get('호수'))) if m.get('호수') else None
    if (not dong or not ho) and m.get('동-호수'):
        dh = _txt(row.get(m['동-호수'])) or ''
        if '-' in dh:
            dong, ho = dh.split('-', 1)
    if dong:
        dong = re.sub(r'동$', '', dong.strip())
    return dong, (ho.strip() if ho else None)


def analyze(df, mapping, cfg, site_id):
    """mapping: {엑셀열: 대상} → 미리보기 계획."""
    m = {}
    for col, tgt in mapping.items():
        if tgt and tgt != SKIP:
            m[tgt] = col
    statuses = set(templates.status_names(cfg))
    existing = {(str(u['building_no']), str(u['unit_no'])): u for u in db.get_units(site_id=site_id)}
    active = {c['unit_id']: c for c in db.get_contracts(site_id=site_id, active_only=True)}
    plan = {'units': [], 'errors': [], 'n_unit_new': 0, 'n_unit_upd': 0, 'n_ct_new': 0, 'n_ct_upd': 0, 'n_pay': 0}
    if not (('동' in m and '호수' in m) or '동-호수' in m):
        plan['errors'].append("동·호수(또는 동-호수) 열 매핑이 필요합니다.")
        return plan
    seen = set()
    for i, row in df.iterrows():
        rowd = row.to_dict()
        g = lambda t: rowd.get(m[t]) if t in m else None  # noqa: E731
        dong, ho = _bld_unit(rowd, m)
        line = f"{i + 2}행"
        if not dong or not ho:
            continue
        if (dong, ho) in seen:
            plan['errors'].append(f"{line}: {dong}동 {ho}호 중복 행 — 건너뜀")
            continue
        seen.add((dong, ho))
        unit = {'dong': dong, 'ho': ho, 'type': _txt(g('타입')), 'floor': _num(g('층')), 'line': _txt(g('라인')),
                'prices': {p['key']: _num(g(f"가격: {p['label']}")) for p in cfg['price_fields']
                           if f"가격: {p['label']}" in m}}
        ex = existing.get((dong, ho))
        plan['n_unit_upd' if ex else 'n_unit_new'] += 1
        status = _txt(g('상태'))
        name = _txt(g('계약자명'))
        contract = None
        if status and status != '공실':
            if status not in statuses:
                plan['errors'].append(f"{line} {dong}-{ho}: 상태 '{status}'가 양식에 없음 (설정 > 계약 양식에서 추가)")
            else:
                if not name:
                    name = NO_NAME
                    plan['no_name'] = plan.get('no_name', 0) + 1
                birth = _date(g('생년월일')) or birth_from_rrn(g('등록번호(생년월일만 추출)'))
                fields = {}
                for f in cfg['fields']:
                    v = g(f"기타: {f['label']}")
                    v = _date(v) if f.get('type') == 'date' else (_num(v) if f.get('type') in ('number', 'money')
                                                                  else _txt(v))
                    if v not in (None, ''):
                        fields[f['label']] = v
                docs = {d: True for d in cfg['docs'] if _truthy(g(f"서류: {d}"))}
                contract = {
                    'customer_name': name, 'phone': _txt(g('연락처')), 'birth_date': birth,
                    'address': _txt(g('주소')), 'contract_type': status, 'pre_date': _date(g('가계약일')),
                    'planned_date': _date(g('계약예정일')), 'contract_date': _date(g('계약일')),
                    'assigned_team': _txt(g('담당팀')), 'assigned_staff': _txt(g('담당자')),
                    'deposit_total': _num(g('계약금')) or 0, 'notes': _txt(g('비고1')), 'notes2': _txt(g('비고2')),
                    'extra': {'fields': fields, 'docs': docs},
                }
                plan['n_ct_upd' if ex and ex['id'] in active else 'n_ct_new'] += 1
        pays = []
        for item in cfg['payment_items']:
            amt = _num(g(f"납부액: {item}"))
            if amt:
                pays.append({'item': item, 'amount': amt, 'date': _date(g(f"납부일: {item}"))})
        plan['n_pay'] += len(pays)
        plan['units'].append({'unit': unit, 'contract': contract, 'pays': pays, 'line': line})
    return plan


def apply(site_id, plan, tx_rows=None):
    """계획 반영 (한 트랜잭션). tx_rows: 입출금 시트 행 [{dong, ho, date, type, amount, ...}]"""
    stats = {'unit_new': 0, 'unit_upd': 0, 'ct_new': 0, 'ct_upd': 0, 'pay': 0, 'tx': 0}
    with db.connect() as conn:
        cx = conn.execute("SELECT id FROM complexes WHERE site_id=? ORDER BY complex_no LIMIT 1", (site_id,)).fetchone()
        cx_id = cx[0] if cx else conn.execute(
            "INSERT INTO complexes (site_id, complex_no, complex_name) VALUES (?, 1, '1단지')", (site_id,)).lastrowid
        bcache = {}

        def unit_id_for(dong, ho, create=None):
            if dong not in bcache:
                r = conn.execute("SELECT id FROM buildings WHERE site_id=? AND building_no=?", (site_id, dong)).fetchone()
                bcache[dong] = r[0] if r else conn.execute(
                    "INSERT INTO buildings (site_id, complex_id, building_no) VALUES (?, ?, ?)",
                    (site_id, cx_id, dong)).lastrowid
            r = conn.execute("SELECT id, extra FROM units WHERE building_id=? AND unit_no=?", (bcache[dong], ho)).fetchone()
            if r or create is None:
                return r
            u = create
            cols = {'sale_price': u['prices'].get('sale_price') or 0, 'rental_price': u['prices'].get('rental_price') or 0}
            extra = {k: v for k, v in u['prices'].items() if k not in templates.UNIT_COLUMNS and v is not None}
            uid = conn.execute("""INSERT INTO units (site_id, complex_id, building_id, unit_no, type, floor, line,
                                  sale_price, rental_price, status, extra) VALUES (?,?,?,?,?,?,?,?,?, '공실', ?)""",
                               (site_id, cx_id, bcache[dong], ho, u['type'], u['floor'], u['line'],
                                cols['sale_price'], cols['rental_price'], db._jdump(extra))).lastrowid
            stats['unit_new'] += 1
            return conn.execute("SELECT id, extra FROM units WHERE id=?", (uid,)).fetchone()

        for item in plan['units']:
            u = item['unit']
            row = unit_id_for(u['dong'], u['ho'])
            if row:
                extra = db._jload(row['extra'])
                for k, v in u['prices'].items():
                    if v is None:
                        continue
                    if k in templates.UNIT_COLUMNS:
                        conn.execute(f"UPDATE units SET {k}=? WHERE id=?", (v, row['id']))
                    else:
                        extra[k] = v
                conn.execute("""UPDATE units SET type=COALESCE(?, type), floor=COALESCE(?, floor),
                                line=COALESCE(?, line), extra=? WHERE id=?""",
                             (u['type'], u['floor'], u['line'], db._jdump(extra), row['id']))
                stats['unit_upd'] += 1
            else:
                row = unit_id_for(u['dong'], u['ho'], create=u)
            uid = row['id']
            ct = item['contract']
            if ct:
                cur = conn.execute(f"SELECT id FROM contracts WHERE unit_id=? AND status='{db.CONTRACT_ACTIVE}'",
                                   (uid,)).fetchone()
                if cur:
                    db._update_contract(conn, cur['id'], ct)
                    stats['ct_upd'] += 1
                else:
                    db._insert_contract(conn, uid, site_id, ct)
                    stats['ct_new'] += 1
            for p in item['pays']:
                dup = conn.execute("""SELECT 1 FROM transactions WHERE unit_id=? AND item=? AND amount=?
                                      AND date=? AND type='입금'""",
                                   (uid, p['item'], p['amount'], p['date'] or '')).fetchone()
                if not dup:
                    conn.execute("""INSERT INTO transactions (unit_id, site_id, date, customer, amount, type, item, notes)
                                    VALUES (?, ?, ?, ?, ?, '입금', ?, '엑셀 가져오기')""",
                                 (uid, site_id, p['date'] or '', (ct or {}).get('customer_name'), p['amount'], p['item']))
                    stats['pay'] += 1
        for t in tx_rows or []:
            row = unit_id_for(t['dong'], t['ho']) if t.get('dong') and t.get('ho') else None
            uid = row['id'] if row else None
            dup = conn.execute("""SELECT 1 FROM transactions WHERE site_id=? AND IFNULL(unit_id,0)=IFNULL(?,0)
                                  AND date=? AND amount=? AND type=? AND IFNULL(depositor,'')=IFNULL(?,'')""",
                               (site_id, uid, t['date'], t['amount'], t['type'], t.get('depositor'))).fetchone()
            if dup:
                continue
            conn.execute("""INSERT INTO transactions (unit_id, site_id, date, depositor, customer, account, amount,
                            type, item, out_reason, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                         (uid, site_id, t['date'], t.get('depositor'), t.get('customer'), t.get('account'),
                          t['amount'], t['type'], t.get('item'), t.get('out_reason'), t.get('notes')))
            stats['tx'] += 1
    return stats


def parse_tx_sheet(df):
    """엑셀 '입출금' 시트 → 거래 목록 (동-호수 / 동·호, 날짜, 입금자명, 고객명, 입금계좌, 입금항목, 입금액, 출금액, 출금사유, 비고)."""
    cols = {_key(c): c for c in df.columns}

    def col(*names):
        for n in names:
            if _key(n) in cols:
                return cols[_key(n)]
        return None
    c_dh, c_d, c_h = col('동-호수'), col('동'), col('호', '호수')
    c_date, c_in, c_out = col('날짜', '입금일'), col('입금액'), col('출금액')
    rows = []
    for _, r in df.iterrows():
        dong = ho = None
        if c_dh and _txt(r[c_dh]) and '-' in _txt(r[c_dh]):
            dong, ho = _txt(r[c_dh]).split('-', 1)
        elif c_d and c_h:
            dong, ho = _txt(r[c_d]), _txt(r[c_h])
        d = _date(r[c_date]) if c_date else None
        for kind, c in (('입금', c_in), ('출금', c_out)):
            amt = _num(r[c]) if c else None
            if amt and d:
                rows.append({'dong': re.sub(r'동$', '', dong) if dong else None, 'ho': ho, 'date': d, 'type': kind,
                             'amount': amt,
                             'depositor': _txt(r[col('입금자명')]) if col('입금자명') else None,
                             'customer': _txt(r[col('고객명')]) if col('고객명') else None,
                             'account': _txt(r[col('입금계좌')]) if col('입금계좌') else None,
                             'item': _txt(r[col('입금항목')]) if col('입금항목') else None,
                             'out_reason': _txt(r[col('출금사유')]) if (kind == '출금' and col('출금사유')) else None,
                             'notes': _txt(r[col('비고')]) if col('비고') else None})
    return rows
