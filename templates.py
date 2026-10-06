"""
templates.py — 현장별 계약 양식 (프리셋 + 설정 헬퍼)

현장마다 관리 항목이 다르다 (분양 / 민간임대 / 지역주택조합).
sites.config(JSON)에 아래 구조로 저장하고, 계약관리 표·현황판·입출금 화면이 이 설정을 따른다.

config = {
  "price_fields":  [{"key": "sale_price", "label": "분양가"}, ...],   # 호실 가격 항목
  "statuses":      [{"name": "가계약", "color": "#00A0E9"}, ...],     # 공실 외 상태 + 현황판 색
  "payment_items": ["1차 계약금", "업무대행비", ...],                 # 입금항목 (입출금 태그 → 납부현황)
  "docs":          ["가입계약서", "등본", ...],                        # 서류 체크
  "fields":        [{"label": "차수", "type": "select", "options": ["1차", "2차"]}, ...],  # 기타 항목
  "floor_groups":  [{"from": 1, "to": 3, "label": "1군"}, ...],       # 현황판 좌측 층 구간
}
"""
import copy
import json

# 호실 가격 항목 key: sale_price / rental_price 는 units 테이블 컬럼, 나머지는 units.extra(JSON)
UNIT_COLUMNS = ('sale_price', 'rental_price')
FIELD_TYPES = {'text': '글자', 'date': '날짜', 'number': '숫자', 'money': '금액', 'select': '선택', 'check': '체크'}

STATUS_PALETTE = ['#00A0E9', '#E00000', '#7F7F7F', '#F59E0B', '#8B5CF6', '#10B981']

PRESETS = {
    '분양': {
        'label': '분양 (아파트·오피스텔)',
        'price_fields': [{'key': 'sale_price', 'label': '분양가'}, {'key': 'rental_price', 'label': '계약금(기준)'}],
        'statuses': [{'name': '가계약', 'color': '#00A0E9'}, {'name': '계약', 'color': '#E00000'}],
        'payment_items': ['계약금', '중도금', '잔금', '기타'],
        'docs': ['계약서', '신분증 사본', '인감증명서'],
        'fields': [{'label': '계약서 발행', 'type': 'date'}, {'label': '사은품', 'type': 'text'}],
        'floor_groups': [],
    },
    '민간임대': {
        'label': '민간임대 (울산 호수공원형)',
        'price_fields': [{'key': 'sale_price', 'label': '임대가'}, {'key': 'conv_price', 'label': '분양전환가'}],
        'statuses': [{'name': '가계약', 'color': '#00A0E9'}, {'name': '계약', 'color': '#E00000'}],
        'payment_items': ['1차 납부', '2차 납부', '3차 납부', '기타'],
        'docs': ['동호예약증서', '가입계약서', '공증'],
        'fields': [{'label': '형태', 'type': 'select', 'options': ['공동주택', '오피스텔']},
                   {'label': '계약서 발행', 'type': 'date'}, {'label': '사은품', 'type': 'text'}],
        'floor_groups': [],
    },
    '지역주택조합': {
        'label': '지역주택조합 (사직 에듀센트럴형)',
        'price_fields': [{'key': 'sale_price', 'label': '분양가'}, {'key': 'agency_fee', 'label': '업무대행비'}],
        'statuses': [{'name': '가계약', 'color': '#00A0E9'}, {'name': '계약', 'color': '#E00000'},
                     {'name': '소송', 'color': '#7F7F7F'}],
        'payment_items': ['1차 계약금', '업무대행비', '2차 계약금', '3차 계약금', '기타'],
        'docs': ['가입계약서', '등본', '초본', '인감증명서', '도장'],
        'fields': [{'label': '차수', 'type': 'select', 'options': ['1차', '2차', '3차']},
                   {'label': '계약서 발행', 'type': 'date'}, {'label': '사은품', 'type': 'text'}],
        'floor_groups': [],
    },
}
DEFAULT_PRESET = '분양'


def preset_config(name):
    p = copy.deepcopy(PRESETS.get(name) or PRESETS[DEFAULT_PRESET])
    p.pop('label', None)
    return p


def load_config(site):
    """site dict → 완성된 config (빠진 키는 프리셋 기본값으로 채움)."""
    base = preset_config((site or {}).get('template') or DEFAULT_PRESET)
    raw = (site or {}).get('config')
    if raw:
        try:
            cfg = json.loads(raw) if isinstance(raw, str) else dict(raw)
            base.update({k: v for k, v in cfg.items() if k in base})
        except (ValueError, TypeError):
            pass
    return base


def dump_config(cfg):
    return json.dumps(cfg, ensure_ascii=False)


def status_names(cfg):
    return [s['name'] for s in cfg['statuses']]


def status_colors(cfg):
    """{상태: (배경, 글자)} — 공실 포함."""
    colors = {'공실': ('#FFFFFF', '#222222')}
    for s in cfg['statuses']:
        colors[s['name']] = (s.get('color') or '#999999', '#FFFFFF')
    return colors


def signed_statuses(cfg):
    """계약률에 넣는 상태 (소송 등 분쟁 상태는 제외하지 않는다 — 호실이 점유된 상태 전체)."""
    return status_names(cfg)


def price_label(cfg, key):
    return next((p['label'] for p in cfg['price_fields'] if p['key'] == key), key)
