"""
calc.py — 일비·숙소비 계산 로직
"""
import math
import calendar
from datetime import date, timedelta

import db


# ===================================================================
# 일비 계산
# ===================================================================

def _get_prev_term(year, month, term):
    """Return (year, month, term) of the immediately preceding term."""
    if term == 1:
        if month == 1:
            return year - 1, 12, 2
        return year, month - 1, 2
    return year, month, 1


def _calc_term(employee_id, year, month, term, depth=0, daily_rate=10000):
    """
    Recursively calculate daily-allowance for one term.

    depth 0  : the term the caller actually wants
    depth 1  : one term back (needed to determine carry-in for depth-0)
    depth 2  : two terms back (needed to correctly assess depth-1's carry-in)
               At depth 2 we assume no further carry-in (safe by the 1-carry rule).
    """
    if term == 1:
        period_start = date(year, month, 1)
        period_end = date(year, month, 15)
    else:
        last_day = calendar.monthrange(year, month)[1]
        period_start = date(year, month, 16)
        period_end = date(year, month, last_day)

    possible_days = (period_end - period_start).days + 1
    work_days = db.get_work_days_in_range(employee_id, period_start, period_end)
    threshold = math.ceil(possible_days * 0.7)

    # Determine carry-in from the previous term
    if depth < 2:
        py, pm, pt = _get_prev_term(year, month, term)
        prev = _calc_term(employee_id, py, pm, pt, depth + 1, daily_rate=daily_rate)
        carry_in = prev['status'] == '이월'
        carry_in_days = prev['work_days'] if carry_in else 0
    else:
        carry_in = False
        carry_in_days = 0

    pct = work_days / possible_days if possible_days > 0 else 0

    if pct >= 0.7:
        if work_days >= 11:
            status = '지급'
            pay_days = work_days + carry_in_days
        elif carry_in:
            # Cannot carry over twice in a row → carry-in days are lost
            status = '소멸'
            pay_days = 0
        else:
            status = '이월'
            pay_days = 0
    else:
        status = '미충족'
        pay_days = 0

    # 일비 집행일: 1차 → 당월 20일 / 2차 → 익월 5일
    if term == 1:
        exec_d = date(year, month, 20)
    else:
        exec_d = date(year + 1, 1, 5) if month == 12 else date(year, month + 1, 5)

    return {
        'period_start':   period_start,
        'period_end':     period_end,
        'execution_date': exec_d,
        'work_days':      work_days,
        'possible_days':  possible_days,
        'threshold':      threshold,
        'status':         status,
        'carry_over':     carry_in,
        'pay_days':       pay_days,
        'amount':         pay_days * daily_rate,
    }


def calc_daily_allowance(employee_id, year, month, term, site_id=None):
    """
    Calculate daily allowance for an employee for the given year/month/term.

    term: 1 (days 1-15) or 2 (days 16-end)
    site_id: if provided, uses the site's daily_allowance rate instead of default 10,000원
    """
    daily_rate = 10000
    if site_id:
        site = db.get_site(site_id)
        if site:
            daily_rate = int(site.get('daily_allowance') or 10000)
    return _calc_term(employee_id, year, month, term, depth=0, daily_rate=daily_rate)


# ===================================================================
# 숙소비 계산
# ===================================================================

def get_execution_date(period_end):
    """집행일 = 판정종료일 초과 이후 가장 가까운 5일 또는 20일."""
    y, m = period_end.year, period_end.month
    d5  = date(y, m, 5)
    d20 = date(y, m, 20)
    if period_end < d5:
        return d5
    elif period_end < d20:
        return d20
    else:
        return date(y + 1, 1, 5) if m == 12 else date(y, m + 1, 5)


def calc_housing(employee_id, execution_date, site_id=None):
    """
    집행일 기준으로 해당 직원의 숙소비 판정기간과 지급 여부를 계산한다.

    판정기간: 첫출근일 ~ 첫출근일+29 (30일), 이후 30일 반복
    집행일:   판정종료일 초과 이후 가장 가까운 5일 또는 20일

    site_id를 전달하면 현장별 숙소비 단가를 사용한다.
    """
    emp = db.get_employee(employee_id)
    if not emp or not emp.get('first_work_date'):
        return _empty_housing(execution_date)

    fwd = emp['first_work_date']
    if isinstance(fwd, str):
        fwd = date.fromisoformat(fwd)

    if site_id:
        site = db.get_site(site_id)
        if site:
            local_rate = int(site.get('housing_local') or 200000)
            other_rate = int(site.get('housing_other') or 300000)
        else:
            local_rate, other_rate = 200000, 300000
    else:
        local_rate, other_rate = 200000, 300000

    amount_base = local_rate if emp['housing_region'] == '해당지역' else other_rate

    period_start = None
    period_end = None
    is_target = False

    for k in range(300):
        ps = fwd + timedelta(days=30 * k)
        pe = ps + timedelta(days=29)
        expected = get_execution_date(pe)
        if expected == execution_date:
            period_start = ps
            period_end = pe
            is_target = True
            break
        if expected > execution_date:
            break

    if is_target and period_start:
        work_days = db.get_work_days_in_range(employee_id, period_start, period_end)
        is_qualified = work_days >= 25
        amount = amount_base if is_qualified else 0
    else:
        work_days = 0
        is_qualified = False
        amount = 0

    return {
        'period_start': period_start,
        'period_end': period_end,
        'work_days': work_days,
        'is_qualified': is_qualified,
        'execution_date': execution_date,
        'is_target': is_target,
        'amount': amount,
    }


def _empty_housing(execution_date):
    return {
        'period_start': None,
        'period_end': None,
        'work_days': 0,
        'is_qualified': False,
        'execution_date': execution_date,
        'is_target': False,
        'amount': 0,
    }


def get_housing_schedule(employee_id, periods=12):
    """직원의 향후 숙소비 집행 스케줄을 반환한다."""
    emp = db.get_employee(employee_id)
    if not emp or not emp.get('first_work_date'):
        return []

    fwd = emp['first_work_date']
    if isinstance(fwd, str):
        fwd = date.fromisoformat(fwd)

    schedules = []
    for k in range(periods):
        ps = fwd + timedelta(days=30 * k)
        pe = ps + timedelta(days=29)
        schedules.append({
            'period_start': ps,
            'period_end': pe,
            'execution_date': get_execution_date(pe),
        })
    return schedules
