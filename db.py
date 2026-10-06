"""
db.py — SQLite 연결, 스키마 마이그레이션, CRUD 전체

설계 원칙
- 직원·호실·계약은 항상 id로 식별한다 (이름 매칭 금지 — 동명이인 사고 방지).
- 여러 테이블을 함께 바꾸는 작업(계약+호실상태, 해지+계약상태 등)은 한 트랜잭션으로 처리한다.
- 정산 이력은 지급 증빙이므로 직원 삭제로 함께 지워지지 않는다.
"""
import os
import sqlite3
import hashlib
import hmac
import secrets
import calendar
from contextlib import contextmanager
from datetime import date

DB_PATH = os.environ.get('TSWEB_DB_PATH') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'sales_manager.db')

DEFAULT_ADMIN_PASSWORD = 'admin1234'
SCHEMA_VERSION = 2

CONTRACT_ACTIVE = '유효'
CONTRACT_CANCELLED = '해지'


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect():
    """with connect() as conn: ... — 정상 종료 시 commit, 예외 시 rollback."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _one(cur):
    r = cur.fetchone()
    return dict(r) if r else None


# ===================================================================
# 비밀번호 (PBKDF2-SHA256 + salt, 구버전 SHA-256 자동 업그레이드)
# ===================================================================

_PBKDF2_PREFIX = 'pbkdf2_sha256'
_PBKDF2_ITER = 200_000


def hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), _PBKDF2_ITER).hex()
    return f"{_PBKDF2_PREFIX}${_PBKDF2_ITER}${salt}${dk}"


def verify_password(password, stored):
    if not stored:
        return False
    if stored.startswith(_PBKDF2_PREFIX + '$'):
        try:
            _, iters, salt, dk = stored.split('$')
            calc = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iters)).hex()
            return hmac.compare_digest(calc, dk)
        except (ValueError, TypeError):
            return False
    # 구버전: 솔트 없는 SHA-256
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def _is_legacy_hash(stored):
    return not (stored or '').startswith(_PBKDF2_PREFIX + '$')


# ===================================================================
# 스키마 / 마이그레이션
# ===================================================================

def _add_column(cur, table, col_sql):
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_sql}")
    except sqlite3.OperationalError:
        pass  # 이미 존재


def _try(cur, sql):
    try:
        cur.execute(sql)
        return True
    except sqlite3.DatabaseError:
        return False


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS sites (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            region      TEXT NOT NULL,
            start_date  DATE,
            status      TEXT DEFAULT '진행중',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS employees (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id         INTEGER REFERENCES sites(id),
            name            TEXT NOT NULL,
            division        TEXT,
            team            TEXT,
            phone           TEXT,
            first_work_date DATE,
            housing_region  TEXT DEFAULT '해당지역',
            status          TEXT DEFAULT '재직',
            sort_order      INTEGER,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER REFERENCES employees(id),
            work_date   DATE NOT NULL,
            is_present  INTEGER DEFAULT 1,
            UNIQUE(employee_id, work_date)
        );

        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL,
            site_id     INTEGER REFERENCES sites(id),
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settlement_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id         INTEGER REFERENCES sites(id),
            employee_id     INTEGER REFERENCES employees(id),
            settlement_type TEXT,
            execution_date  DATE,
            period_start    DATE,
            period_end      DATE,
            work_days       INTEGER,
            amount          INTEGER,
            status          TEXT DEFAULT '확정',
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS complexes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id      INTEGER NOT NULL REFERENCES sites(id),
            complex_no   INTEGER NOT NULL,
            complex_name TEXT NOT NULL,
            total_units  INTEGER DEFAULT 0,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS buildings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id      INTEGER NOT NULL REFERENCES sites(id),
            complex_id   INTEGER NOT NULL REFERENCES complexes(id),
            building_no  TEXT NOT NULL,
            total_floors INTEGER DEFAULT 0,
            total_units  INTEGER DEFAULT 0,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS units (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id       INTEGER NOT NULL REFERENCES sites(id),
            complex_id    INTEGER NOT NULL REFERENCES complexes(id),
            building_id   INTEGER NOT NULL REFERENCES buildings(id),
            unit_no       TEXT NOT NULL,
            type          TEXT,
            floor         INTEGER,
            line          TEXT,
            rental_price  INTEGER DEFAULT 0,
            sale_price    INTEGER DEFAULT 0,
            status        TEXT DEFAULT '공실',
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contracts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id         INTEGER NOT NULL REFERENCES units(id),
            site_id         INTEGER NOT NULL REFERENCES sites(id),
            customer_name   TEXT NOT NULL,
            phone           TEXT,
            address         TEXT,
            contract_type   TEXT NOT NULL,
            contract_date   DATE,
            deposit_total   INTEGER DEFAULT 0,
            assigned_team   TEXT,
            assigned_staff  TEXT,
            notes           TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id     INTEGER REFERENCES units(id),
            site_id     INTEGER NOT NULL REFERENCES sites(id),
            date        DATE NOT NULL,
            depositor   TEXT,
            customer    TEXT,
            account     TEXT,
            amount      INTEGER DEFAULT 0,
            type        TEXT NOT NULL,
            notes       TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cancellations (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id        INTEGER NOT NULL REFERENCES units(id),
            contract_id    INTEGER REFERENCES contracts(id),
            cancel_date    DATE,
            refund_amount  INTEGER DEFAULT 0,
            bank           TEXT,
            account_no     TEXT,
            status         TEXT DEFAULT '해지',
            notes          TEXT,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_sites (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            site_id INTEGER NOT NULL REFERENCES sites(id),
            UNIQUE(user_id, site_id)
        );
    """)

    # ── 컬럼 추가 (idempotent) ─────────────────────────────────
    _add_column(cur, 'employees', 'division TEXT')
    _add_column(cur, 'employees', 'sort_order INTEGER')
    _add_column(cur, 'employees', 'notes TEXT')
    _add_column(cur, 'sites', 'daily_allowance INTEGER DEFAULT 10000')
    _add_column(cur, 'sites', 'housing_local INTEGER DEFAULT 200000')
    _add_column(cur, 'sites', 'housing_other INTEGER DEFAULT 300000')
    _add_column(cur, 'contracts', f"status TEXT DEFAULT '{CONTRACT_ACTIVE}'")
    _add_column(cur, 'contracts', 'cancelled_at DATE')
    _add_column(cur, 'transactions', 'out_reason TEXT')

    # ── 인덱스 ────────────────────────────────────────────────
    _try(cur, """CREATE UNIQUE INDEX IF NOT EXISTS idx_settlement_unique
                 ON settlement_history(employee_id, settlement_type, execution_date)""")
    _try(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_complex_unique ON complexes(site_id, complex_no)")
    _try(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_building_unique ON buildings(complex_id, building_no)")
    _try(cur, "CREATE UNIQUE INDEX IF NOT EXISTS idx_unit_unique ON units(building_id, unit_no)")
    _try(cur, "CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(work_date)")
    _try(cur, "CREATE INDEX IF NOT EXISTS idx_contract_unit ON contracts(unit_id, status)")
    _try(cur, "CREATE INDEX IF NOT EXISTS idx_tx_site_date ON transactions(site_id, date)")
    _try(cur, "CREATE INDEX IF NOT EXISTS idx_emp_site ON employees(site_id, status)")

    # users.site_id → user_sites (구버전 호환)
    _try(cur, """INSERT OR IGNORE INTO user_sites (user_id, site_id)
                 SELECT id, site_id FROM users WHERE site_id IS NOT NULL""")

    # ── 1회성 데이터 마이그레이션 (PRAGMA user_version) ──────────
    version = cur.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        # 계약 상태: 해지 내역이 가리키는 계약은 '해지'
        cur.execute(f"""
            UPDATE contracts SET status='{CONTRACT_CANCELLED}',
                   cancelled_at=(SELECT MAX(cl.cancel_date) FROM cancellations cl WHERE cl.contract_id=contracts.id)
            WHERE id IN (SELECT contract_id FROM cancellations WHERE contract_id IS NOT NULL)
        """)
        cur.execute(f"UPDATE contracts SET status='{CONTRACT_ACTIVE}' WHERE status IS NULL")
        # 출금 비고 'A | B' → 출금사유 A / 비고 B 분리
        for r in cur.execute("SELECT id, notes FROM transactions WHERE type='출금' AND out_reason IS NULL").fetchall():
            notes = r['notes'] or ''
            if ' | ' in notes:
                rsn, nts = notes.split(' | ', 1)
            else:
                rsn, nts = notes, ''
            cur.execute("UPDATE transactions SET out_reason=?, notes=? WHERE id=?",
                        (rsn or None, nts or None, r['id']))
        # 호실 상태를 유효 계약 기준으로 재동기화 ('해지' 상태 호실은 공실로)
        _resync_unit_status(cur)
        cur.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # ── 최초 실행: 관리자 계정만 생성 (데모 데이터 없음) ─────────
    if not cur.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        cur.execute("INSERT INTO users (username, password, role) VALUES ('admin', ?, 'admin')",
                    (hash_password(DEFAULT_ADMIN_PASSWORD),))

    conn.commit()
    conn.close()


def _resync_unit_status(cur, unit_ids=None):
    """호실 상태 = 유효 계약의 계약구분 (없으면 공실)."""
    where = ""
    params = []
    if unit_ids:
        where = f"WHERE id IN ({','.join('?' * len(unit_ids))})"
        params = list(unit_ids)
    cur.execute(f"""
        UPDATE units SET status = COALESCE(
            (SELECT ct.contract_type FROM contracts ct
              WHERE ct.unit_id = units.id AND ct.status = '{CONTRACT_ACTIVE}'
              ORDER BY ct.created_at DESC, ct.id DESC LIMIT 1),
            '공실')
        {where}
    """, params)


# ===================================================================
# SITES
# ===================================================================

def get_all_sites():
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT s.*, COUNT(e.id) AS employee_count
            FROM sites s
            LEFT JOIN employees e ON e.site_id = s.id AND e.status = '재직'
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """))


def get_site(site_id):
    with connect() as conn:
        return _one(conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)))


def get_site_rates(site_id):
    """(일비 단가, 해당지역 숙소비, 타지역 숙소비)"""
    site = get_site(site_id) if site_id else None
    if not site:
        return 10000, 200000, 300000
    return (int(site.get('daily_allowance') or 10000),
            int(site.get('housing_local') or 200000),
            int(site.get('housing_other') or 300000))


def add_site(name, region, start_date, status='진행중',
             daily_allowance=10000, housing_local=200000, housing_other=300000):
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO sites (name, region, start_date, status,
                   daily_allowance, housing_local, housing_other)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, region, start_date, status, daily_allowance, housing_local, housing_other))
        return cur.lastrowid


def update_site(site_id, name, region, start_date, status,
                daily_allowance=10000, housing_local=200000, housing_other=300000):
    with connect() as conn:
        conn.execute(
            """UPDATE sites SET name=?, region=?, start_date=?, status=?,
                   daily_allowance=?, housing_local=?, housing_other=?
               WHERE id=?""",
            (name, region, start_date, status, daily_allowance, housing_local, housing_other, site_id))


def site_name_exists(name, exclude_id=None):
    with connect() as conn:
        r = conn.execute("SELECT id FROM sites WHERE name=? AND id IS NOT ?", (name, exclude_id)).fetchone()
        return r is not None


def delete_site(site_id):
    with connect() as conn:
        checks = [
            ("SELECT COUNT(*) FROM employees WHERE site_id=?", "직원 {}명"),
            ("SELECT COUNT(*) FROM complexes WHERE site_id=?", "단지 {}개"),
            ("SELECT COUNT(*) FROM transactions WHERE site_id=?", "입출금 {}건"),
            ("SELECT COUNT(*) FROM settlement_history WHERE site_id=?", "정산이력 {}건"),
        ]
        blockers = []
        for sql, label in checks:
            n = conn.execute(sql, (site_id,)).fetchone()[0]
            if n:
                blockers.append(label.format(n))
        if blockers:
            return False, f"{', '.join(blockers)}이(가) 남아 있어 삭제할 수 없습니다."
        conn.execute("DELETE FROM user_sites WHERE site_id=?", (site_id,))
        conn.execute("UPDATE users SET site_id=NULL WHERE site_id=?", (site_id,))
        conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
    return True, "삭제되었습니다."


# ===================================================================
# EMPLOYEES
# ===================================================================

_EMP_ORDER = " ORDER BY (sort_order IS NULL), sort_order ASC, division, team, name, id"


def get_employees(site_id=None, include_retired=False):
    query = "SELECT * FROM employees WHERE 1=1"
    params = []
    if site_id:
        query += " AND site_id=?"
        params.append(site_id)
    if not include_retired:
        query += " AND status='재직'"
    with connect() as conn:
        return _rows(conn.execute(query + _EMP_ORDER, params))


def get_employees_for_period(site_id, start_date, end_date):
    """정산 대상: 재직자 + 해당 기간에 출근 기록이 있는 퇴직자."""
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT * FROM employees e
            WHERE e.site_id = ?
              AND (e.status = '재직' OR EXISTS (
                    SELECT 1 FROM attendance a
                    WHERE a.employee_id = e.id AND a.is_present = 1
                      AND a.work_date >= ? AND a.work_date <= ?))
        """ + _EMP_ORDER, (site_id, str(start_date), str(end_date))))


def get_employee(emp_id):
    with connect() as conn:
        return _one(conn.execute("SELECT * FROM employees WHERE id=?", (emp_id,)))


def find_employees(site_id, name):
    with connect() as conn:
        return _rows(conn.execute(
            "SELECT * FROM employees WHERE site_id=? AND name=? ORDER BY id", (site_id, name)))


def add_employee(site_id, name, division, team, phone, first_work_date,
                 housing_region='해당지역', status='재직', notes=None):
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO employees (site_id, name, division, team, phone, first_work_date,
                                   housing_region, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (site_id, name, division, team, phone, first_work_date, housing_region, status, notes))
        return cur.lastrowid


def update_employee(emp_id, name, division, team, phone, first_work_date, housing_region, status,
                    notes=None):
    with connect() as conn:
        conn.execute("""
            UPDATE employees
            SET name=?, division=?, team=?, phone=?, first_work_date=?, housing_region=?, status=?,
                notes=?
            WHERE id=?
        """, (name, division, team, phone, first_work_date, housing_region, status, notes, emp_id))


def apply_employee_upload(emp_plan, att_plan):
    """엑셀 업로드 반영 (한 트랜잭션).
    emp_plan: [{'action': 'insert'|'update', 'emp_id', 'fields': {...}}]
    att_plan: [{'target': ('plan', 인덱스) | ('emp', 직원id), 'dates': {'YYYY-MM-DD': 0|1}}]
    빈 값(None)은 기존값을 유지한다. 반환: (신규, 갱신, 출근 칸 수)"""
    new_ids = {}
    with connect() as conn:
        for pi, item in enumerate(emp_plan):
            f = item['fields']
            if item['action'] == 'insert':
                eid = conn.execute("""
                    INSERT INTO employees (site_id, name, division, team, phone, first_work_date,
                                           housing_region, status, notes, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (f['site_id'], f['name'], f['division'], f['team'], f['phone'], f['first_work_date'],
                      f['housing_region'] or '해당지역', f['status'] or '재직', f['notes'],
                      f.get('sort_order'))).lastrowid
            else:
                eid = item['emp_id']
                conn.execute("""
                    UPDATE employees SET
                        division=COALESCE(?, division), team=COALESCE(?, team), phone=COALESCE(?, phone),
                        first_work_date=COALESCE(?, first_work_date), housing_region=COALESCE(?, housing_region),
                        status=COALESCE(?, status), notes=COALESCE(?, notes), sort_order=COALESCE(?, sort_order)
                    WHERE id=?
                """, (f['division'], f['team'], f['phone'], f['first_work_date'], f['housing_region'],
                      f['status'], f['notes'], f.get('sort_order'), eid))
            new_ids[pi] = eid
        records = []
        for item in att_plan:
            kind, ref = item['target']
            eid = new_ids.get(ref) if kind == 'plan' else ref
            if eid:
                records += [(eid, d, p) for d, p in item['dates'].items()]
        conn.executemany("""
            INSERT INTO attendance (employee_id, work_date, is_present) VALUES (?, ?, ?)
            ON CONFLICT(employee_id, work_date) DO UPDATE SET is_present=excluded.is_present
        """, records)
    n_ins = sum(1 for x in emp_plan if x['action'] == 'insert')
    return n_ins, len(emp_plan) - n_ins, len(records)


def count_employee_settlements(emp_id):
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM settlement_history WHERE employee_id=?",
                            (emp_id,)).fetchone()[0]


def delete_employee(emp_id):
    """정산 이력이 있는 직원은 삭제하지 않는다 (퇴직 처리로 유도)."""
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM settlement_history WHERE employee_id=?",
                         (emp_id,)).fetchone()[0]
        if n:
            return False, f"정산 이력 {n}건이 있어 삭제할 수 없습니다. '퇴직'으로 처리하세요."
        conn.execute("DELETE FROM attendance WHERE employee_id=?", (emp_id,))
        conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    return True, "삭제되었습니다."


def set_sort_order(emp_id, sort_order):
    with connect() as conn:
        conn.execute("UPDATE employees SET sort_order=? WHERE id=?", (sort_order, emp_id))


# ===================================================================
# ATTENDANCE
# ===================================================================

def get_attendance_dates(employee_id, year, month):
    """출근일 'YYYY-MM-DD' 집합."""
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    with connect() as conn:
        return {r[0] for r in conn.execute("""
            SELECT work_date FROM attendance
            WHERE employee_id=? AND work_date >= ? AND work_date <= ? AND is_present=1
        """, (employee_id, start, end))}


def get_site_attendance(site_id, start_date, end_date):
    """{employee_id: set(date_str)} — 현장 전체를 한 번에 조회."""
    result = {}
    with connect() as conn:
        for r in conn.execute("""
            SELECT a.employee_id, a.work_date FROM attendance a
            JOIN employees e ON a.employee_id = e.id
            WHERE e.site_id=? AND a.is_present=1 AND a.work_date >= ? AND a.work_date <= ?
        """, (site_id, str(start_date), str(end_date))):
            result.setdefault(r[0], set()).add(r[1])
    return result


def get_work_days_in_range(employee_id, start_date, end_date):
    with connect() as conn:
        return conn.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE employee_id=? AND work_date >= ? AND work_date <= ? AND is_present=1
        """, (employee_id, str(start_date), str(end_date))).fetchone()[0]


def save_attendance_month(employee_id, year, month, work_dates_set):
    """한 달 전체 출근 기록을 덮어쓴다 (화면 입력용)."""
    last_day = calendar.monthrange(year, month)[1]
    records = []
    for day in range(1, last_day + 1):
        d = f"{year}-{month:02d}-{day:02d}"
        records.append((employee_id, d, 1 if d in work_dates_set else 0))
    save_attendance_records(records)


def save_attendance_records(records):
    """[(employee_id, 'YYYY-MM-DD', is_present)] 를 한 트랜잭션으로 upsert.
    지정된 날짜만 바뀌고 나머지 날짜는 그대로 둔다."""
    if not records:
        return 0
    with connect() as conn:
        conn.executemany("""
            INSERT INTO attendance (employee_id, work_date, is_present)
            VALUES (?, ?, ?)
            ON CONFLICT(employee_id, work_date) DO UPDATE SET is_present=excluded.is_present
        """, records)
    return len(records)


def get_daily_attendance_counts(site_id, start_date, end_date):
    """{date_str: 출근인원}"""
    with connect() as conn:
        return {r[0]: r[1] for r in conn.execute("""
            SELECT a.work_date, COUNT(*) AS cnt
            FROM attendance a
            JOIN employees e ON a.employee_id = e.id
            WHERE e.site_id = ? AND a.is_present = 1
              AND a.work_date >= ? AND a.work_date <= ?
            GROUP BY a.work_date
        """, (site_id, str(start_date), str(end_date)))}


# ===================================================================
# USERS
# ===================================================================

def get_user_by_username(username):
    with connect() as conn:
        return _one(conn.execute("SELECT * FROM users WHERE username=?", (username,)))


def get_user_sites(user_id):
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT site_id FROM user_sites WHERE user_id=?", (user_id,))]


def authenticate_user(username, password):
    user = get_user_by_username((username or '').strip())
    if not user or not verify_password(password, user['password']):
        return None
    if _is_legacy_hash(user['password']):
        update_user_password(user['id'], password)  # 로그인 성공 시 새 해시로 자동 전환
    user = dict(user)
    user.pop('password', None)
    user['site_ids'] = get_user_sites(user['id'])
    user['must_change_password'] = (password == DEFAULT_ADMIN_PASSWORD)
    return user


def get_all_users():
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT u.id, u.username, u.role, u.created_at,
                   GROUP_CONCAT(s.name, ', ') AS site_name,
                   GROUP_CONCAT(us.site_id, ',') AS site_ids_str
            FROM users u
            LEFT JOIN user_sites us ON u.id = us.user_id
            LEFT JOIN sites s ON us.site_id = s.id
            GROUP BY u.id
            ORDER BY u.created_at
        """))


def count_admins():
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]


def add_user(username, password, role, site_id_list=None):
    try:
        with connect() as conn:
            cur = conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                               (username, hash_password(password), role))
            user_id = cur.lastrowid
            for sid in (site_id_list or []):
                conn.execute("INSERT OR IGNORE INTO user_sites (user_id, site_id) VALUES (?, ?)", (user_id, sid))
        return True, user_id
    except sqlite3.IntegrityError:
        return False, "이미 존재하는 아이디입니다."


def update_user_password(user_id, new_password):
    with connect() as conn:
        conn.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_password), user_id))


def update_user(user_id, role, site_id_list=None):
    with connect() as conn:
        cur_role = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if cur_role and cur_role[0] == 'admin' and role != 'admin':
            n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
            if n <= 1:
                return False, "마지막 관리자의 권한은 변경할 수 없습니다."
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        conn.execute("DELETE FROM user_sites WHERE user_id=?", (user_id,))
        for sid in (site_id_list or []):
            conn.execute("INSERT OR IGNORE INTO user_sites (user_id, site_id) VALUES (?, ?)", (user_id, sid))
    return True, "변경되었습니다."


def delete_user(user_id):
    with connect() as conn:
        r = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if r and r[0] == 'admin':
            n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
            if n <= 1:
                return False, "마지막 관리자 계정은 삭제할 수 없습니다."
        conn.execute("DELETE FROM user_sites WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    return True, "삭제되었습니다."


# ===================================================================
# SETTLEMENT HISTORY
# ===================================================================

def save_settlement(site_id, employee_id, settlement_type,
                    execution_date, period_start, period_end, work_days, amount):
    """동일 (employee_id, settlement_type, execution_date) 중복 시 갱신."""
    with connect() as conn:
        conn.execute("""
            INSERT INTO settlement_history
                (site_id, employee_id, settlement_type, execution_date,
                 period_start, period_end, work_days, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, settlement_type, execution_date)
            DO UPDATE SET
                site_id=excluded.site_id,
                period_start=excluded.period_start,
                period_end=excluded.period_end,
                work_days=excluded.work_days,
                amount=excluded.amount
        """, (site_id, employee_id, settlement_type, str(execution_date),
              str(period_start) if period_start else None,
              str(period_end) if period_end else None,
              work_days, amount))


def save_settlements(items):
    """여러 건을 한 트랜잭션으로 저장. items: dict(site_id, employee_id, settlement_type, execution_date,
    period_start, period_end, work_days, amount)"""
    if not items:
        return 0
    with connect() as conn:
        conn.executemany("""
            INSERT INTO settlement_history
                (site_id, employee_id, settlement_type, execution_date,
                 period_start, period_end, work_days, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, settlement_type, execution_date)
            DO UPDATE SET
                site_id=excluded.site_id,
                period_start=excluded.period_start,
                period_end=excluded.period_end,
                work_days=excluded.work_days,
                amount=excluded.amount
        """, [(i['site_id'], i['employee_id'], i['settlement_type'], str(i['execution_date']),
               str(i['period_start']) if i.get('period_start') else None,
               str(i['period_end']) if i.get('period_end') else None,
               i['work_days'], i['amount']) for i in items])
    return len(items)


def get_settlements(site_id=None, settlement_type=None, limit=None, site_ids=None,
                    execution_date=None):
    """site_ids: 접근 가능한 현장 목록으로 제한 (manager용). None이면 제한 없음."""
    query = """
        SELECT sh.*,
               e.name AS employee_name,
               e.division AS employee_division,
               e.team AS employee_team,
               e.phone AS employee_phone,
               s.name AS site_name
        FROM settlement_history sh
        JOIN employees e ON sh.employee_id = e.id
        JOIN sites s ON sh.site_id = s.id
        WHERE 1=1
    """
    params = []
    if site_id:
        query += " AND sh.site_id=?"
        params.append(site_id)
    if site_ids is not None:
        if not site_ids:
            return []
        query += f" AND sh.site_id IN ({','.join('?' * len(site_ids))})"
        params.extend(site_ids)
    if settlement_type:
        query += " AND sh.settlement_type=?"
        params.append(settlement_type)
    if execution_date:
        query += " AND sh.execution_date=?"
        params.append(str(execution_date))
    query += " ORDER BY sh.execution_date DESC, sh.created_at DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    with connect() as conn:
        return _rows(conn.execute(query, params))


def delete_settlements(settlement_ids, allowed_site_ids=None):
    """다건 삭제. allowed_site_ids가 주어지면 그 현장 이력만 삭제된다."""
    if not settlement_ids:
        return 0
    ids = [int(i) for i in settlement_ids]
    sql = f"DELETE FROM settlement_history WHERE id IN ({','.join('?' * len(ids))})"
    params = list(ids)
    if allowed_site_ids is not None:
        if not allowed_site_ids:
            return 0
        sql += f" AND site_id IN ({','.join('?' * len(allowed_site_ids))})"
        params.extend(allowed_site_ids)
    with connect() as conn:
        return conn.execute(sql, params).rowcount


def delete_settlement(settlement_id):
    return delete_settlements([settlement_id])


def expected_daily_execution_date(period_start):
    """일비 판정기간 시작일 → 규칙상 집행일 (1차: 당월 20일 / 2차: 익월 5일)."""
    ps = date.fromisoformat(str(period_start))
    if ps.day <= 15:
        return date(ps.year, ps.month, 20)
    return date(ps.year + 1, 1, 5) if ps.month == 12 else date(ps.year, ps.month + 1, 5)


def find_settlement_anomalies():
    """데이터 점검용: 정산 이력의 의심 건 목록."""
    issues = []
    with connect() as conn:
        rows = _rows(conn.execute("""
            SELECT sh.*, e.name AS employee_name, s.name AS site_name
            FROM settlement_history sh
            JOIN employees e ON sh.employee_id = e.id
            JOIN sites s ON sh.site_id = s.id
            ORDER BY sh.execution_date, sh.id
        """))
        for r in rows:
            if r['settlement_type'] == 'daily_allowance' and r['period_start']:
                exp = str(expected_daily_execution_date(r['period_start']))
                if r['execution_date'] != exp:
                    issues.append({**r, 'issue': 'exec_date', 'expected': exp,
                                   'desc': f"일비 집행일 {r['execution_date']} → 규칙상 {exp}"})
            if r['period_start'] and r['period_end']:
                n = conn.execute("""
                    SELECT COUNT(*) FROM attendance
                    WHERE employee_id=? AND is_present=1 AND work_date>=? AND work_date<=?
                """, (r['employee_id'], r['period_start'], r['period_end'])).fetchone()[0]
                if n == 0 and (r['amount'] or 0) > 0:
                    issues.append({**r, 'issue': 'no_attendance', 'expected': None,
                                   'desc': f"판정기간 출근 0일인데 {r['amount']:,}원 지급 기록"})
                elif r['settlement_type'] == 'daily_allowance' and r['work_days'] is not None and n != r['work_days']:
                    issues.append({**r, 'issue': 'work_days_mismatch', 'expected': None,
                                   'desc': f"저장 출근일수 {r['work_days']}일 ≠ 현재 기록 {n}일"})
    return issues


def fix_daily_execution_dates():
    """규칙과 다른 일비 집행일을 바로잡는다. 같은 키가 이미 있으면 건너뛴다."""
    fixed, skipped = 0, 0
    with connect() as conn:
        rows = _rows(conn.execute("""
            SELECT id, employee_id, execution_date, period_start FROM settlement_history
            WHERE settlement_type='daily_allowance' AND period_start IS NOT NULL
        """))
        for r in rows:
            exp = str(expected_daily_execution_date(r['period_start']))
            if r['execution_date'] == exp:
                continue
            dup = conn.execute("""
                SELECT 1 FROM settlement_history
                WHERE employee_id=? AND settlement_type='daily_allowance' AND execution_date=?
            """, (r['employee_id'], exp)).fetchone()
            if dup:
                skipped += 1
                continue
            conn.execute("UPDATE settlement_history SET execution_date=? WHERE id=?", (exp, r['id']))
            fixed += 1
    return fixed, skipped


# ===================================================================
# COMPLEXES / BUILDINGS / UNITS
# ===================================================================

def get_complexes(site_id):
    with connect() as conn:
        return _rows(conn.execute("SELECT * FROM complexes WHERE site_id=? ORDER BY complex_no", (site_id,)))


def get_complex(complex_id):
    with connect() as conn:
        return _one(conn.execute("SELECT * FROM complexes WHERE id=?", (complex_id,)))


def get_buildings(site_id=None, complex_id=None):
    query = """
        SELECT b.*, c.complex_name, c.complex_no
        FROM buildings b JOIN complexes c ON b.complex_id = c.id
        WHERE 1=1
    """
    params = []
    if site_id:
        query += " AND b.site_id=?"
        params.append(site_id)
    if complex_id:
        query += " AND b.complex_id=?"
        params.append(complex_id)
    query += " ORDER BY c.complex_no, CAST(b.building_no AS INTEGER), b.building_no"
    with connect() as conn:
        return _rows(conn.execute(query, params))


def get_building(building_id):
    with connect() as conn:
        return _one(conn.execute("SELECT * FROM buildings WHERE id=?", (building_id,)))


_UNIT_SELECT = """
    SELECT u.*, c.complex_name, c.complex_no, b.building_no
    FROM units u
    JOIN complexes c ON u.complex_id = c.id
    JOIN buildings b ON u.building_id = b.id
"""


def get_units(site_id=None, complex_id=None, building_id=None, status=None):
    query = _UNIT_SELECT + " WHERE 1=1"
    params = []
    for col, val in (("u.site_id", site_id), ("u.complex_id", complex_id),
                     ("u.building_id", building_id), ("u.status", status)):
        if val:
            query += f" AND {col}=?"
            params.append(val)
    query += " ORDER BY c.complex_no, b.building_no, u.floor, u.unit_no"
    with connect() as conn:
        return _rows(conn.execute(query, params))


def get_unit(unit_id):
    with connect() as conn:
        return _one(conn.execute(_UNIT_SELECT + " WHERE u.id=?", (unit_id,)))


def update_unit_status(unit_id, status):
    with connect() as conn:
        conn.execute("UPDATE units SET status=? WHERE id=?", (status, unit_id))


def resync_unit_status(site_id=None):
    """호실 상태를 유효 계약 기준으로 다시 맞춘다. 바뀐 호실 수 반환."""
    with connect() as conn:
        before = dict(conn.execute("SELECT id, status FROM units").fetchall())
        ids = None
        if site_id:
            ids = [r[0] for r in conn.execute("SELECT id FROM units WHERE site_id=?", (site_id,))]
        _resync_unit_status(conn.cursor(), ids)
        after = dict(conn.execute("SELECT id, status FROM units").fetchall())
    return sum(1 for k, v in after.items() if before.get(k) != v)


def find_unit_status_mismatches():
    """호실 상태가 유효 계약과 맞지 않는 호실."""
    with connect() as conn:
        rows = _rows(conn.execute(f"""
            SELECT u.id, u.unit_no, u.status, b.building_no, s.name AS site_name,
                   (SELECT ct.contract_type FROM contracts ct
                     WHERE ct.unit_id=u.id AND ct.status='{CONTRACT_ACTIVE}'
                     ORDER BY ct.created_at DESC, ct.id DESC LIMIT 1) AS expected
            FROM units u
            JOIN buildings b ON u.building_id=b.id
            JOIN sites s ON u.site_id=s.id
        """))
    return [r for r in rows if (r['expected'] or '공실') != r['status']]


def get_unit_status_summary(site_id):
    with connect() as conn:
        return {r['status']: r['cnt'] for r in conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM units WHERE site_id=? GROUP BY status", (site_id,))}


def get_all_site_unit_summary():
    """{site_id: {status: count}}"""
    result = {}
    with connect() as conn:
        for r in conn.execute("SELECT site_id, status, COUNT(*) AS cnt FROM units GROUP BY site_id, status"):
            result.setdefault(r['site_id'], {})[r['status']] = r['cnt']
    return result


def get_cancel_counts_by_site():
    with connect() as conn:
        return {r[0]: r[1] for r in conn.execute("""
            SELECT u.site_id, COUNT(*) FROM cancellations cl JOIN units u ON cl.unit_id=u.id
            GROUP BY u.site_id
        """)}


# ===================================================================
# CONTRACTS
# ===================================================================

_CONTRACT_SELECT = """
    SELECT ct.*,
           u.unit_no, u.status AS unit_status, u.type AS unit_type, u.sale_price,
           c.complex_name, c.complex_no,
           b.building_no
    FROM contracts ct
    JOIN units u ON ct.unit_id = u.id
    JOIN complexes c ON u.complex_id = c.id
    JOIN buildings b ON u.building_id = b.id
"""


def get_contracts(site_id=None, unit_id=None, contract_type=None, active_only=False):
    query = _CONTRACT_SELECT + " WHERE 1=1"
    params = []
    if site_id:
        query += " AND ct.site_id=?"
        params.append(site_id)
    if unit_id:
        query += " AND ct.unit_id=?"
        params.append(unit_id)
    if contract_type:
        query += " AND ct.contract_type=?"
        params.append(contract_type)
    if active_only:
        query += f" AND ct.status='{CONTRACT_ACTIVE}'"
    query += " ORDER BY ct.contract_date DESC, ct.created_at DESC, ct.id DESC"
    with connect() as conn:
        return _rows(conn.execute(query, params))


def get_active_contract(unit_id):
    """호실의 현재 유효 계약 (없으면 None)."""
    with connect() as conn:
        return _one(conn.execute(
            _CONTRACT_SELECT + f" WHERE ct.unit_id=? AND ct.status='{CONTRACT_ACTIVE}'"
            " ORDER BY ct.created_at DESC, ct.id DESC LIMIT 1", (unit_id,)))


def get_contract(contract_id):
    with connect() as conn:
        return _one(conn.execute(_CONTRACT_SELECT + " WHERE ct.id=?", (contract_id,)))


def add_contract(unit_id, site_id, customer_name, phone=None, address=None,
                 contract_type='가계약', contract_date=None, deposit_total=0,
                 assigned_team=None, assigned_staff=None, notes=None, sale_price=None):
    """신규 계약. 유효 계약이 이미 있으면 ValueError."""
    with connect() as conn:
        dup = conn.execute(f"SELECT id FROM contracts WHERE unit_id=? AND status='{CONTRACT_ACTIVE}'",
                           (unit_id,)).fetchone()
        if dup:
            raise ValueError("이미 유효한 계약이 있는 호실입니다.")
        cur = conn.execute(f"""
            INSERT INTO contracts
                (unit_id, site_id, customer_name, phone, address,
                 contract_type, contract_date, deposit_total,
                 assigned_team, assigned_staff, notes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{CONTRACT_ACTIVE}')
        """, (unit_id, site_id, customer_name, phone, address,
              contract_type, contract_date, deposit_total,
              assigned_team, assigned_staff, notes))
        new_id = cur.lastrowid
        if sale_price is not None:
            conn.execute("UPDATE units SET sale_price=? WHERE id=?", (sale_price, unit_id))
        conn.execute("UPDATE units SET status=? WHERE id=?", (contract_type, unit_id))
        return new_id


def update_contract(contract_id, customer_name, phone=None, address=None,
                    contract_type='가계약', contract_date=None, deposit_total=0,
                    assigned_team=None, assigned_staff=None, notes=None, sale_price=None):
    with connect() as conn:
        conn.execute("""
            UPDATE contracts
            SET customer_name=?, phone=?, address=?,
                contract_type=?, contract_date=?, deposit_total=?,
                assigned_team=?, assigned_staff=?, notes=?
            WHERE id=?
        """, (customer_name, phone, address,
              contract_type, contract_date, deposit_total,
              assigned_team, assigned_staff, notes, contract_id))
        row = conn.execute("SELECT unit_id, status FROM contracts WHERE id=?", (contract_id,)).fetchone()
        if row:
            if sale_price is not None:
                conn.execute("UPDATE units SET sale_price=? WHERE id=?", (sale_price, row[0]))
            if row[1] == CONTRACT_ACTIVE:
                conn.execute("UPDATE units SET status=? WHERE id=?", (contract_type, row[0]))


def delete_contract(contract_id):
    with connect() as conn:
        row = conn.execute("SELECT unit_id FROM contracts WHERE id=?", (contract_id,)).fetchone()
        conn.execute("UPDATE cancellations SET contract_id=NULL WHERE contract_id=?", (contract_id,))
        conn.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
        if row:
            _resync_unit_status(conn.cursor(), [row[0]])


# ===================================================================
# TRANSACTIONS
# ===================================================================

_TX_SELECT = """
    SELECT t.*, u.unit_no, c.complex_name, b.building_no
    FROM transactions t
    LEFT JOIN units u ON t.unit_id = u.id
    LEFT JOIN complexes c ON u.complex_id = c.id
    LEFT JOIN buildings b ON u.building_id = b.id
"""


def get_transactions(site_id=None, unit_id=None, tx_type=None, start_date=None, end_date=None):
    query = _TX_SELECT + " WHERE 1=1"
    params = []
    if site_id:
        query += " AND t.site_id=?"
        params.append(site_id)
    if unit_id:
        query += " AND t.unit_id=?"
        params.append(unit_id)
    if tx_type:
        query += " AND t.type=?"
        params.append(tx_type)
    if start_date:
        query += " AND t.date>=?"
        params.append(str(start_date))
    if end_date:
        query += " AND t.date<=?"
        params.append(str(end_date))
    query += " ORDER BY t.date DESC, t.created_at DESC"
    with connect() as conn:
        return _rows(conn.execute(query, params))


def get_transaction(tx_id):
    with connect() as conn:
        return _one(conn.execute(_TX_SELECT + " WHERE t.id=?", (tx_id,)))


def add_transaction(site_id, date, depositor=None, customer=None, account=None,
                    amount=0, tx_type='입금', notes=None, unit_id=None, out_reason=None):
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO transactions
                (unit_id, site_id, date, depositor, customer, account, amount, type, notes, out_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (unit_id, site_id, date, depositor, customer, account, amount, tx_type, notes, out_reason))
        return cur.lastrowid


def update_transaction(tx_id, date, depositor=None, customer=None, account=None,
                       amount=0, tx_type='입금', notes=None, unit_id=None, out_reason=None):
    with connect() as conn:
        conn.execute("""
            UPDATE transactions
            SET unit_id=?, date=?, depositor=?, customer=?,
                account=?, amount=?, type=?, notes=?, out_reason=?
            WHERE id=?
        """, (unit_id, date, depositor, customer, account, amount, tx_type, notes, out_reason, tx_id))


def delete_transaction(tx_id):
    with connect() as conn:
        conn.execute("DELETE FROM transactions WHERE id=?", (tx_id,))


def get_transaction_summary(site_id):
    with connect() as conn:
        return {r['type']: r['total'] or 0 for r in conn.execute(
            "SELECT type, SUM(amount) AS total FROM transactions WHERE site_id=? GROUP BY type", (site_id,))}


# ===================================================================
# CANCELLATIONS
# ===================================================================

def get_cancellations(site_id=None, unit_id=None):
    query = """
        SELECT cl.*,
               u.unit_no, u.type AS unit_type, u.site_id,
               c.complex_name, b.building_no,
               ct.customer_name, ct.contract_type, ct.phone, ct.contract_date
        FROM cancellations cl
        JOIN units u ON cl.unit_id = u.id
        JOIN complexes c ON u.complex_id = c.id
        JOIN buildings b ON u.building_id = b.id
        LEFT JOIN contracts ct ON cl.contract_id = ct.id
        WHERE 1=1
    """
    params = []
    if site_id:
        query += " AND u.site_id=?"
        params.append(site_id)
    if unit_id:
        query += " AND cl.unit_id=?"
        params.append(unit_id)
    query += " ORDER BY cl.cancel_date DESC, cl.created_at DESC"
    with connect() as conn:
        return _rows(conn.execute(query, params))


def get_cancellation(cancel_id):
    with connect() as conn:
        return _one(conn.execute("""
            SELECT cl.*, u.site_id, u.unit_no, b.building_no, ct.customer_name
            FROM cancellations cl
            JOIN units u ON cl.unit_id = u.id
            JOIN buildings b ON u.building_id = b.id
            LEFT JOIN contracts ct ON cl.contract_id = ct.id
            WHERE cl.id=?""", (cancel_id,)))


def cancel_contract(contract_id, cancel_date=None, refund_amount=0, bank=None,
                    account_no=None, notes=None):
    """해지 처리: 해지내역 저장 + 계약 '해지' + 호실 공실 — 한 트랜잭션."""
    with connect() as conn:
        ct = conn.execute("SELECT unit_id, status FROM contracts WHERE id=?", (contract_id,)).fetchone()
        if not ct:
            raise ValueError("계약을 찾을 수 없습니다.")
        if ct['status'] != CONTRACT_ACTIVE:
            raise ValueError("이미 해지된 계약입니다.")
        cur = conn.execute("""
            INSERT INTO cancellations
                (unit_id, contract_id, cancel_date, refund_amount, bank, account_no, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, '해지', ?)
        """, (ct['unit_id'], contract_id, cancel_date, refund_amount, bank, account_no, notes))
        new_id = cur.lastrowid
        conn.execute(f"UPDATE contracts SET status='{CONTRACT_CANCELLED}', cancelled_at=? WHERE id=?",
                     (cancel_date, contract_id))
        _resync_unit_status(conn.cursor(), [ct['unit_id']])
        return new_id


def add_cancellation(unit_id, contract_id=None, cancel_date=None,
                     refund_amount=0, bank=None, account_no=None,
                     status='해지', notes=None):
    """구버전 호환용 — 계약이 지정되면 cancel_contract로 처리."""
    if contract_id:
        return cancel_contract(contract_id, cancel_date, refund_amount, bank, account_no, notes)
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO cancellations (unit_id, contract_id, cancel_date, refund_amount,
                                       bank, account_no, status, notes)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
        """, (unit_id, cancel_date, refund_amount, bank, account_no, status, notes))
        return cur.lastrowid


def update_cancellation(cancel_id, cancel_date=None, refund_amount=0,
                        bank=None, account_no=None, status='해지', notes=None):
    with connect() as conn:
        conn.execute("""
            UPDATE cancellations
            SET cancel_date=?, refund_amount=?, bank=?, account_no=?, status=?, notes=?
            WHERE id=?
        """, (cancel_date, refund_amount, bank, account_no, status, notes, cancel_id))
        row = conn.execute("SELECT contract_id FROM cancellations WHERE id=?", (cancel_id,)).fetchone()
        if row and row[0]:
            conn.execute("UPDATE contracts SET cancelled_at=? WHERE id=?", (cancel_date, row[0]))


def delete_cancellation(cancel_id):
    """해지 취소: 해지내역 삭제 + 원 계약 복구.
    그 사이 같은 호실에 새 유효 계약이 생겼다면 복구할 수 없으므로 거부한다."""
    with connect() as conn:
        cl = conn.execute("SELECT unit_id, contract_id FROM cancellations WHERE id=?", (cancel_id,)).fetchone()
        if not cl:
            return False, "해지 내역을 찾을 수 없습니다."
        if cl['contract_id']:
            other = conn.execute(f"""
                SELECT id FROM contracts WHERE unit_id=? AND status='{CONTRACT_ACTIVE}' AND id<>?
            """, (cl['unit_id'], cl['contract_id'])).fetchone()
            if other:
                return False, "해당 호실에 이미 새 계약이 있어 해지를 취소할 수 없습니다."
            conn.execute(f"UPDATE contracts SET status='{CONTRACT_ACTIVE}', cancelled_at=NULL WHERE id=?",
                         (cl['contract_id'],))
        conn.execute("DELETE FROM cancellations WHERE id=?", (cancel_id,))
        _resync_unit_status(conn.cursor(), [cl['unit_id']])
    if cl['contract_id']:
        return True, "해지가 취소되어 원 계약이 복구되었습니다."
    return True, "해지 내역이 삭제되었습니다."


def find_orphan_cancellations():
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT cl.id, cl.cancel_date, cl.contract_id, u.unit_no, b.building_no, s.name AS site_name
            FROM cancellations cl
            JOIN units u ON cl.unit_id=u.id
            JOIN buildings b ON u.building_id=b.id
            JOIN sites s ON u.site_id=s.id
            LEFT JOIN contracts ct ON cl.contract_id=ct.id
            WHERE ct.id IS NULL
        """))


# ===================================================================
# BULK UPLOAD (단지/동/호실)
# ===================================================================

def _clean_text(v):
    """엑셀 셀 값 → 깔끔한 문자열 (NaN/None → None, 101.0 → '101')."""
    if v is None:
        return None
    try:
        if v != v:  # NaN
            return None
    except Exception:
        pass
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip()
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def _clean_int(v, default=None):
    s = _clean_text(v)
    if s is None:
        return default
    try:
        return int(float(s.replace(',', '')))
    except ValueError:
        return default


def bulk_upload_units(site_id, rows):
    """
    단지/동/호실 일괄 upsert (한 트랜잭션).
    rows: dict(complex_no, complex_name, building_no, unit_no, type_, floor, line, sale_price, rental_price)
    빈 셀은 기존값을 유지한다. 반환: (단지 수, 동 수, 신규 호실 수, 갱신 호실 수)
    """
    with connect() as conn:
        complex_cache, building_cache = {}, {}
        n_new = n_upd = 0
        for row in rows:
            complex_no = _clean_int(row['complex_no'])
            complex_name = _clean_text(row['complex_name']) or f"{complex_no}단지"
            building_no = _clean_text(row['building_no'])
            unit_no = _clean_text(row['unit_no'])
            if complex_no is None or not building_no or not unit_no:
                raise ValueError(f"필수값 누락: 단지번호={row.get('complex_no')}, 동={row.get('building_no')}, 호수={row.get('unit_no')}")
            type_ = _clean_text(row.get('type_'))
            floor = _clean_int(row.get('floor'))
            line = _clean_text(row.get('line'))
            sale_price = _clean_int(row.get('sale_price'))      # 빈칸이면 None → 기존값 유지
            rental_price = _clean_int(row.get('rental_price'))

            if complex_no not in complex_cache:
                r = conn.execute("SELECT id FROM complexes WHERE site_id=? AND complex_no=?",
                                 (site_id, complex_no)).fetchone()
                if r:
                    conn.execute("UPDATE complexes SET complex_name=? WHERE id=?", (complex_name, r[0]))
                    complex_cache[complex_no] = r[0]
                else:
                    complex_cache[complex_no] = conn.execute(
                        "INSERT INTO complexes (site_id, complex_no, complex_name) VALUES (?, ?, ?)",
                        (site_id, complex_no, complex_name)).lastrowid
            complex_id = complex_cache[complex_no]

            bk = (complex_id, building_no)
            if bk not in building_cache:
                r = conn.execute("SELECT id FROM buildings WHERE complex_id=? AND building_no=?",
                                 (complex_id, building_no)).fetchone()
                building_cache[bk] = r[0] if r else conn.execute(
                    "INSERT INTO buildings (site_id, complex_id, building_no) VALUES (?, ?, ?)",
                    (site_id, complex_id, building_no)).lastrowid
            building_id = building_cache[bk]

            r = conn.execute("SELECT id FROM units WHERE building_id=? AND unit_no=?",
                             (building_id, unit_no)).fetchone()
            if r:
                conn.execute("""UPDATE units SET type=COALESCE(?, type), floor=COALESCE(?, floor),
                                       line=COALESCE(?, line), sale_price=COALESCE(?, sale_price),
                                       rental_price=COALESCE(?, rental_price)
                                WHERE id=?""", (type_, floor, line, sale_price, rental_price, r[0]))
                n_upd += 1
            else:
                conn.execute("""INSERT INTO units
                                   (site_id, complex_id, building_id, unit_no, type, floor, line,
                                    sale_price, rental_price, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '공실')""",
                             (site_id, complex_id, building_id, unit_no, type_, floor, line,
                              sale_price or 0, rental_price or 0))
                n_new += 1
        return len(complex_cache), len(building_cache), n_new, n_upd


# ===================================================================
# 데이터 점검 (관리자)
# ===================================================================

def find_duplicate_employee_names():
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT s.name AS site_name, e.name, COUNT(*) AS cnt, GROUP_CONCAT(e.id) AS ids
            FROM employees e JOIN sites s ON e.site_id=s.id
            GROUP BY e.site_id, e.name HAVING COUNT(*) > 1
        """))


def find_employees_without_first_date():
    with connect() as conn:
        return _rows(conn.execute("""
            SELECT e.id, e.name, e.team, s.name AS site_name
            FROM employees e JOIN sites s ON e.site_id=s.id
            WHERE e.status='재직' AND (e.first_work_date IS NULL OR e.first_work_date='')
        """))


def backup_database(dest_path):
    """온라인 백업 (sqlite backup API)."""
    src = get_conn()
    dst = sqlite3.connect(dest_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

