"""
calc.py — 일비·숙소비 계산 로직

일비
- 1차(1~15일) → 당월 20일 집행 / 2차(16~말일) → 익월 5일 집행
- 가능일수 70% 이상 + 11일 이상 출근 → 지급
- 70% 충족 + 11일 미만 → 다음 차수로 이월 (1회만), 이월 후 미충족 시 소멸
  ※ 15~16일짜리 차수는 70%를 넘으면 자동으로 11일 이상이 되므로,
    실제로 이월이 생기는 차수는 2월 2차(13~14일)뿐이다.

숙소비
- 판정기간: 첫출근일 ~ +29일 (30일간), 이후 30일 단위 반복
- 25일 이상 출근 시 지급
- 집행일 = 판정종료일 다음 날 이후 가장 가까운 5일 또는 20일 (판정종료일 당일 집행 불가)
"""
import math
import calendar
from datetime import date, timedelta

import db


# ===================================================================
# 차수 / 집행일 헬퍼
# ===================================================================

def term_period(year, month, term):
    """(판정시작일, 판정종료일)"""
    if term == 1:
        return date(year, month, 1), date(year, month, 15)
    return date(year, month, 16), date(year, month, calendar.monthrange(year, month)[1])


def daily_execution_date(year, month, term):
    if term == 1:
        return date(year, month, 20)
    return date(year + 1, 1, 5) if month == 12 else date(year, month + 1, 5)


def daily_term_for_execution(exec_date):
    """집행일 → 그날 지급되는 일비 차수 (year, month, term). 5일/20일이 아니면 None."""
    if exec_date.day == 20:
        return exec_date.year, exec_date.month, 1
    if exec_date.day == 5:
        if exec_date.month == 1:
            return exec_date.year - 1, 12, 2
        return exec_date.year, exec_date.month - 1, 2
    return None


def nearest_execution_dates(base=None, count=6):
    """base 기준 앞뒤로 가까운 집행일(5일/20일) 목록 — 화면 선택지용."""
    base = base or date.today()
    y, m = base.year, base.month
    dates = []
    for k in range(-count, count + 1):
        mm = m + k
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        dates += [date(yy, mm, 5), date(yy, mm, 20)]
    return sorted(dates)


def default_execution_date(base=None):
    """오늘 이후 가장 가까운 집행일 (오늘 포함)."""
    base = base or date.today()
    return next(d for d in nearest_execution_dates(base) if d >= base)


def load_attendance(site_id, start_date, end_date):
    """현장 출근 기록을 한 번에 읽어 {employee_id: set('YYYY-MM-DD')} 로 반환.
    정산 화면에서 직원마다 DB를 조회하지 않도록 미리 읽어 calc 함수에 att=로 넘긴다."""
    return db.get_site_attendance(site_id, start_date, end_date)


def daily_attendance_range(year, month, term):
    """일비 계산(이월 판단용 직전 2차수 포함)에 필요한 출근 기록 범위."""
    py, pm, pt = _get_prev_term(year, month, term)
    ppy, ppm, ppt = _get_prev_term(py, pm, pt)
    return term_period(ppy, ppm, ppt)[0], term_period(year, month, term)[1]


def _work_days(employee_id, start, end, att=None):
    if att is None:
        return db.get_work_days_in_range(employee_id, start, end)
    s, e = str(start), str(end)
    return sum(1 for d in att.get(employee_id, ()) if s <= d <= e)


def _get_prev_term(year, month, term):
    if term == 1:
        return (year - 1, 12, 2) if month == 1 else (year, month - 1, 2)
    return year, month, 1


# ===================================================================
# 일비
# ===================================================================

def _calc_term(employee_id, year, month, term, depth=0, daily_rate=10000, att=None):
    """
    depth 0: 요청 차수 / depth 1: 직전 차수(이월 여부 판단) / depth 2: 그 전 차수.
    depth 2에서는 이월이 없다고 본다 (이월은 1회만 가능하므로 안전).
    """
    period_start, period_end = term_period(year, month, term)
    possible_days = (period_end - period_start).days + 1
    work_days = _work_days(employee_id, period_start, period_end, att)
    threshold = math.ceil(possible_days * 0.7)

    if depth < 2:
        py, pm, pt = _get_prev_term(year, month, term)
        prev = _calc_term(employee_id, py, pm, pt, depth + 1, daily_rate=daily_rate, att=att)
        carry_in = prev['status'] == '이월'
        carry_in_days = prev['work_days'] if carry_in else 0
    else:
        carry_in, carry_in_days = False, 0

    if work_days >= threshold:
        if work_days >= 11:
            status, pay_days = '지급', work_days + carry_in_days
        elif carry_in:
            status, pay_days = '소멸', 0   # 2회 연속 이월 불가
        else:
            status, pay_days = '이월', 0
    else:
        status, pay_days = '미충족', 0

    return {
        'period_start':   period_start,
        'period_end':     period_end,
        'execution_date': daily_execution_date(year, month, term),
        'work_days':      work_days,
        'possible_days':  possible_days,
        'threshold':      threshold,
        'status':         status,
        'carry_over':     carry_in,
        'carry_in_days':  carry_in_days,
        'pay_days':       pay_days,
        'amount':         pay_days * daily_rate,
    }


def calc_daily_allowance(employee_id, year, month, term, site_id=None, daily_rate=None, att=None):
    """term: 1 (1~15일) / 2 (16~말일). 단가는 현장 설정값.
    att: load_attendance()로 미리 읽은 출근 기록 (daily_attendance_range 범위 이상)."""
    if daily_rate is None:
        daily_rate = db.get_site_rates(site_id)[0]
    return _calc_term(employee_id, year, month, term, depth=0, daily_rate=daily_rate, att=att)


# ===================================================================
# 숙소비
# ===================================================================

def get_execution_date(period_end):
    """판정종료일 → 집행일 (종료일 당일 제외, 이후 가장 가까운 5일/20일)."""
    y, m = period_end.year, period_end.month
    if period_end < date(y, m, 5):
        return date(y, m, 5)
    if period_end < date(y, m, 20):
        return date(y, m, 20)
    return date(y + 1, 1, 5) if m == 12 else date(y, m + 1, 5)


def _first_work_date(emp):
    fwd = emp.get('first_work_date') if emp else None
    if not fwd:
        return None
    if isinstance(fwd, str):
        try:
            return date.fromisoformat(fwd[:10])
        except ValueError:
            return None
    return fwd


HOUSING_LOOKBACK_DAYS = 46  # 집행일 기준 판정기간 시작일은 최대 이만큼 앞


def calc_housing(employee_id, execution_date, site_id=None, emp=None, rates=None, att=None):
    """집행일 기준 해당 직원의 숙소비 판정기간과 지급 여부.
    att: 집행일 - HOUSING_LOOKBACK_DAYS ~ 집행일 범위 이상의 출근 기록."""
    emp = emp or db.get_employee(employee_id)
    fwd = _first_work_date(emp)
    if not fwd:
        return _empty_housing(execution_date, reason='첫출근일 없음')

    _, local_rate, other_rate = rates or db.get_site_rates(site_id or emp.get('site_id'))
    amount_base = local_rate if emp.get('housing_region') == '해당지역' else other_rate

    # 집행일로부터 역산: 판정종료일은 집행일 직전 반달 구간 안에 있다
    k = max(0, ((execution_date - fwd).days - 29 - 31) // 30)
    period_start = period_end = None
    while True:
        ps = fwd + timedelta(days=30 * k)
        pe = ps + timedelta(days=29)
        expected = get_execution_date(pe)
        if expected == execution_date:
            period_start, period_end = ps, pe
            break
        if expected > execution_date:
            break
        k += 1

    if not period_start:
        return _empty_housing(execution_date, reason='이번 집행일 비대상')

    work_days = _work_days(employee_id, period_start, period_end, att)
    is_qualified = work_days >= 25
    return {
        'period_start': period_start,
        'period_end': period_end,
        'work_days': work_days,
        'is_qualified': is_qualified,
        'execution_date': execution_date,
        'is_target': True,
        'amount': amount_base if is_qualified else 0,
        'reason': '' if is_qualified else '25일 미만',
    }


def _empty_housing(execution_date, reason=''):
    return {
        'period_start': None,
        'period_end': None,
        'work_days': 0,
        'is_qualified': False,
        'execution_date': execution_date,
        'is_target': False,
        'amount': 0,
        'reason': reason,
    }


def get_housing_schedule(employee_id, periods=12, emp=None, from_date=None):
    """직원의 숙소비 집행 스케줄 (from_date 이후 판정기간부터)."""
    emp = emp or db.get_employee(employee_id)
    fwd = _first_work_date(emp)
    if not fwd:
        return []
    k0 = 0
    if from_date and from_date > fwd:
        k0 = max(0, (from_date - fwd).days // 30 - 1)
    schedules = []
    for k in range(k0, k0 + periods):
        ps = fwd + timedelta(days=30 * k)
        pe = ps + timedelta(days=29)
        schedules.append({'period_start': ps, 'period_end': pe, 'execution_date': get_execution_date(pe)})
    return schedules
