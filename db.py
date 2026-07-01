import os
import sqlite3
import hashlib
import calendar

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sales_manager.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


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

    # Migrate: add division column if not exists
    try:
        cur.execute("ALTER TABLE employees ADD COLUMN division TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: add sort_order column if not exists
    try:
        cur.execute("ALTER TABLE employees ADD COLUMN sort_order INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: unique index for settlement deduplication
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_settlement_unique
            ON settlement_history(employee_id, settlement_type, execution_date)
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Migrate: add rate columns to sites
    for _col_sql in [
        "ALTER TABLE sites ADD COLUMN daily_allowance INTEGER DEFAULT 10000",
        "ALTER TABLE sites ADD COLUMN housing_local INTEGER DEFAULT 200000",
        "ALTER TABLE sites ADD COLUMN housing_other INTEGER DEFAULT 300000",
    ]:
        try:
            cur.execute(_col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Migrate: populate user_sites from users.site_id (idempotent)
    try:
        cur.execute("""
            INSERT OR IGNORE INTO user_sites (user_id, site_id)
            SELECT id, site_id FROM users WHERE site_id IS NOT NULL
        """)
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Insert initial data only if admin does not yet exist
    cur.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO sites (name, region, start_date, status)
            VALUES ('월하리 세종', '세종', '2026-01-01', '진행중')
        """)
        site_id = cur.lastrowid

        employees = [
            (site_id, '홍길동', None, '1팀', '010-1234-5678', '2026-05-01', '해당지역'),
            (site_id, '김영수', None, '1팀', '010-2345-6789', '2026-05-01', '타지역'),
            (site_id, '이민정', None, '2팀', '010-3456-7890', '2026-05-15', '해당지역'),
            (site_id, '박준호', None, '2팀', '010-4567-8901', '2026-06-01', '타지역'),
            (site_id, '최수진', None, '1팀', '010-5678-9012', '2026-06-10', '해당지역'),
        ]
        cur.executemany("""
            INSERT INTO employees (site_id, name, division, team, phone, first_work_date, housing_region)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, employees)

        cur.execute("""
            INSERT INTO users (username, password, role, site_id)
            VALUES ('admin', ?, 'admin', NULL)
        """, (hash_password('admin1234'),))

        conn.commit()

    conn.close()


# ===== SITES =====

def get_all_sites():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, COUNT(e.id) AS employee_count
        FROM sites s
        LEFT JOIN employees e ON e.site_id = s.id AND e.status = '재직'
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_site(site_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_site(name, region, start_date, status='진행중',
             daily_allowance=10000, housing_local=200000, housing_other=300000):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO sites (name, region, start_date, status,
               daily_allowance, housing_local, housing_other)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, region, start_date, status, daily_allowance, housing_local, housing_other),
    )
    conn.commit()
    site_id = cur.lastrowid
    conn.close()
    return site_id


def update_site(site_id, name, region, start_date, status,
                daily_allowance=10000, housing_local=200000, housing_other=300000):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE sites SET name=?, region=?, start_date=?, status=?,
               daily_allowance=?, housing_local=?, housing_other=?
           WHERE id=?""",
        (name, region, start_date, status, daily_allowance, housing_local, housing_other, site_id),
    )
    conn.commit()
    conn.close()


def delete_site(site_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM employees WHERE site_id=?", (site_id,))
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return False, f"직원 {count}명이 등록된 현장은 삭제할 수 없습니다."
    cur.execute("DELETE FROM sites WHERE id=?", (site_id,))
    conn.commit()
    conn.close()
    return True, "삭제되었습니다."


# ===== EMPLOYEES =====

def get_employees(site_id=None, include_retired=False):
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM employees WHERE 1=1"
    params = []
    if site_id:
        query += " AND site_id=?"
        params.append(site_id)
    if not include_retired:
        query += " AND status='재직'"
    query += " ORDER BY (sort_order IS NULL), sort_order ASC, division, team, name"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_employee(emp_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM employees WHERE id=?", (emp_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_employee(site_id, name, division, team, phone, first_work_date, housing_region='해당지역'):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO employees (site_id, name, division, team, phone, first_work_date, housing_region)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (site_id, name, division, team, phone, first_work_date, housing_region))
    conn.commit()
    emp_id = cur.lastrowid
    conn.close()
    return emp_id


def update_employee(emp_id, name, division, team, phone, first_work_date, housing_region, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE employees
        SET name=?, division=?, team=?, phone=?, first_work_date=?, housing_region=?, status=?
        WHERE id=?
    """, (name, division, team, phone, first_work_date, housing_region, status, emp_id))
    conn.commit()
    conn.close()


def upsert_employee(site_id, name, division, team, phone, first_work_date, housing_region, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM employees WHERE site_id=? AND name=?", (site_id, name))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE employees
            SET division=?, team=?, phone=?, first_work_date=?, housing_region=?, status=?
            WHERE id=?
        """, (division, team, phone, first_work_date, housing_region, status, row[0]))
        action = 'updated'
    else:
        cur.execute("""
            INSERT INTO employees (site_id, name, division, team, phone, first_work_date, housing_region, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (site_id, name, division, team, phone, first_work_date, housing_region, status))
        action = 'inserted'
    conn.commit()
    conn.close()
    return action


def delete_employee(emp_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM attendance WHERE employee_id=?", (emp_id,))
    cur.execute("DELETE FROM settlement_history WHERE employee_id=?", (emp_id,))
    cur.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    conn.commit()
    conn.close()


def set_sort_order(emp_id, sort_order):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE employees SET sort_order=? WHERE id=?", (sort_order, emp_id))
    conn.commit()
    conn.close()


# ===== ATTENDANCE =====

def get_attendance_dates(employee_id, year, month):
    """Returns a set of date strings 'YYYY-MM-DD' where the employee was present."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT work_date FROM attendance
        WHERE employee_id=?
          AND strftime('%Y', work_date)=?
          AND strftime('%m', work_date)=?
          AND is_present=1
    """, (employee_id, str(year), f"{month:02d}"))
    rows = {r[0] for r in cur.fetchall()}
    conn.close()
    return rows


def get_work_days_in_range(employee_id, start_date, end_date):
    """Count of days where is_present=1 between start_date and end_date inclusive."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM attendance
        WHERE employee_id=? AND work_date >= ? AND work_date <= ? AND is_present=1
    """, (employee_id, str(start_date), str(end_date)))
    count = cur.fetchone()[0]
    conn.close()
    return count


def save_attendance_month(employee_id, year, month, work_dates_set):
    """Overwrite the entire month's attendance for an employee."""
    conn = get_conn()
    cur = conn.cursor()
    last_day = calendar.monthrange(year, month)[1]
    present_count = 0
    for day in range(1, last_day + 1):
        work_date = f"{year}-{month:02d}-{day:02d}"
        is_present = 1 if work_date in work_dates_set else 0
        if is_present:
            present_count += 1
        cur.execute("""
            INSERT INTO attendance (employee_id, work_date, is_present)
            VALUES (?, ?, ?)
            ON CONFLICT(employee_id, work_date) DO UPDATE SET is_present=excluded.is_present
        """, (employee_id, work_date, is_present))
    conn.commit()
    print(f"[DB] committed: emp={employee_id} {year}/{month:02d} → {present_count}일 출근 / {last_day}일 전체")
    conn.close()


# ===== USERS =====

def get_user_by_username(username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_sites(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT site_id FROM user_sites WHERE user_id=?", (user_id,))
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def save_user_sites(user_id, site_id_list):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_sites WHERE user_id=?", (user_id,))
    for sid in (site_id_list or []):
        cur.execute("INSERT OR IGNORE INTO user_sites (user_id, site_id) VALUES (?, ?)", (user_id, sid))
    conn.commit()
    conn.close()


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if user and user['password'] == hash_password(password):
        user = dict(user)
        user['site_ids'] = get_user_sites(user['id'])
        return user
    return None


def get_all_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.*,
               GROUP_CONCAT(s.name, ', ') AS site_name,
               GROUP_CONCAT(us.site_id, ',') AS site_ids_str
        FROM users u
        LEFT JOIN user_sites us ON u.id = us.user_id
        LEFT JOIN sites s ON us.site_id = s.id
        GROUP BY u.id
        ORDER BY u.created_at
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_user(username, password, role, site_id_list=None):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (username, password, role)
            VALUES (?, ?, ?)
        """, (username, hash_password(password), role))
        conn.commit()
        user_id = cur.lastrowid
        for sid in (site_id_list or []):
            cur.execute("INSERT OR IGNORE INTO user_sites (user_id, site_id) VALUES (?, ?)", (user_id, sid))
        conn.commit()
        conn.close()
        return True, user_id
    except sqlite3.IntegrityError:
        conn.close()
        return False, "이미 존재하는 아이디입니다."


def update_user_password(user_id, new_password):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password=? WHERE id=?", (hash_password(new_password), user_id))
    conn.commit()
    conn.close()


def update_user(user_id, role, site_id_list=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
    cur.execute("DELETE FROM user_sites WHERE user_id=?", (user_id,))
    for sid in (site_id_list or []):
        cur.execute("INSERT OR IGNORE INTO user_sites (user_id, site_id) VALUES (?, ?)", (user_id, sid))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_sites WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


# ===== SETTLEMENT HISTORY =====

def save_settlement(site_id, employee_id, settlement_type,
                    execution_date, period_start, period_end, work_days, amount):
    """동일 (employee_id, settlement_type, execution_date) 중복 시 업데이트."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
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
    conn.commit()
    conn.close()


def get_daily_attendance_counts(site_id, start_date, end_date):
    """Returns {date_str: count} of present employees per day for a site."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.work_date, COUNT(*) AS cnt
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        WHERE e.site_id = ?
          AND e.status = '재직'
          AND a.is_present = 1
          AND a.work_date >= ?
          AND a.work_date <= ?
        GROUP BY a.work_date
        ORDER BY a.work_date
    """, (site_id, str(start_date), str(end_date)))
    rows = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()
    return rows


def get_settlements(site_id=None, settlement_type=None, limit=200):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT sh.*,
               e.name AS employee_name,
               e.division AS employee_division,
               e.team AS employee_team,
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
    if settlement_type:
        query += " AND sh.settlement_type=?"
        params.append(settlement_type)
    query += " ORDER BY sh.created_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_settlement(settlement_id):
    """settlement_history 단건 삭제."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM settlement_history WHERE id=?", (settlement_id,))
    conn.commit()
    conn.close()


def delete_settlements(settlement_ids):
    """settlement_history 다건 삭제."""
    if not settlement_ids:
        return
    conn = get_conn()
    cur = conn.cursor()
    placeholders = ','.join('?' * len(settlement_ids))
    cur.execute(f"DELETE FROM settlement_history WHERE id IN ({placeholders})", settlement_ids)
    conn.commit()
    conn.close()


# ===== COMPLEXES (단지) =====

def get_complexes(site_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM complexes WHERE site_id=? ORDER BY complex_no", (site_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_complex(complex_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM complexes WHERE id=?", (complex_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_complex(site_id, complex_no, complex_name, total_units=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO complexes (site_id, complex_no, complex_name, total_units) VALUES (?, ?, ?, ?)",
        (site_id, complex_no, complex_name, total_units),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_complex(complex_id, complex_no, complex_name, total_units):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE complexes SET complex_no=?, complex_name=?, total_units=? WHERE id=?",
        (complex_no, complex_name, total_units, complex_id),
    )
    conn.commit()
    conn.close()


def delete_complex(complex_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM buildings WHERE complex_id=?", (complex_id,))
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return False, f"동 {count}개가 등록된 단지는 삭제할 수 없습니다."
    cur.execute("DELETE FROM complexes WHERE id=?", (complex_id,))
    conn.commit()
    conn.close()
    return True, "삭제되었습니다."


# ===== BUILDINGS (동) =====

def get_buildings(site_id=None, complex_id=None):
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM buildings WHERE 1=1"
    params = []
    if site_id:
        query += " AND site_id=?"
        params.append(site_id)
    if complex_id:
        query += " AND complex_id=?"
        params.append(complex_id)
    query += " ORDER BY building_no"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_building(building_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM buildings WHERE id=?", (building_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_building(site_id, complex_id, building_no, total_floors=0, total_units=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO buildings (site_id, complex_id, building_no, total_floors, total_units) VALUES (?, ?, ?, ?, ?)",
        (site_id, complex_id, building_no, total_floors, total_units),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_building(building_id, building_no, total_floors, total_units):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE buildings SET building_no=?, total_floors=?, total_units=? WHERE id=?",
        (building_no, total_floors, total_units, building_id),
    )
    conn.commit()
    conn.close()


def delete_building(building_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM units WHERE building_id=?", (building_id,))
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return False, f"호실 {count}개가 등록된 동은 삭제할 수 없습니다."
    cur.execute("DELETE FROM buildings WHERE id=?", (building_id,))
    conn.commit()
    conn.close()
    return True, "삭제되었습니다."


# ===== UNITS (호실) =====

def get_units(site_id=None, complex_id=None, building_id=None, status=None):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT u.*,
               c.complex_name, c.complex_no,
               b.building_no
        FROM units u
        JOIN complexes c ON u.complex_id = c.id
        JOIN buildings b ON u.building_id = b.id
        WHERE 1=1
    """
    params = []
    if site_id:
        query += " AND u.site_id=?"
        params.append(site_id)
    if complex_id:
        query += " AND u.complex_id=?"
        params.append(complex_id)
    if building_id:
        query += " AND u.building_id=?"
        params.append(building_id)
    if status:
        query += " AND u.status=?"
        params.append(status)
    query += " ORDER BY c.complex_no, b.building_no, u.floor, u.unit_no"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_unit(unit_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.*,
               c.complex_name, c.complex_no,
               b.building_no
        FROM units u
        JOIN complexes c ON u.complex_id = c.id
        JOIN buildings b ON u.building_id = b.id
        WHERE u.id=?
    """, (unit_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_unit(site_id, complex_id, building_id, unit_no, type_=None,
             floor=None, line=None, rental_price=0, sale_price=0, status='공실'):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO units
            (site_id, complex_id, building_id, unit_no, type, floor, line,
             rental_price, sale_price, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (site_id, complex_id, building_id, unit_no, type_, floor, line,
          rental_price, sale_price, status))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_unit(unit_id, unit_no, type_=None, floor=None, line=None,
                rental_price=0, sale_price=0, status='공실'):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE units
        SET unit_no=?, type=?, floor=?, line=?,
            rental_price=?, sale_price=?, status=?
        WHERE id=?
    """, (unit_no, type_, floor, line, rental_price, sale_price, status, unit_id))
    conn.commit()
    conn.close()


def update_unit_status(unit_id, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE units SET status=? WHERE id=?", (status, unit_id))
    conn.commit()
    conn.close()


def delete_unit(unit_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM contracts WHERE unit_id=?", (unit_id,))
    count = cur.fetchone()[0]
    if count > 0:
        conn.close()
        return False, f"계약 {count}건이 있는 호실은 삭제할 수 없습니다."
    cur.execute("DELETE FROM units WHERE id=?", (unit_id,))
    conn.commit()
    conn.close()
    return True, "삭제되었습니다."


def get_unit_status_summary(site_id):
    """현장별 호실 상태 요약 반환."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT status, COUNT(*) AS cnt
        FROM units
        WHERE site_id=?
        GROUP BY status
    """, (site_id,))
    rows = {r['status']: r['cnt'] for r in cur.fetchall()}
    conn.close()
    return rows


def get_all_site_unit_summary():
    """전체 현장의 호실 상태 집계를 한 번의 쿼리로 반환.
    반환: {site_id: {status: count, ...}}
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT site_id, status, COUNT(*) AS cnt
        FROM units
        GROUP BY site_id, status
    """)
    result = {}
    for r in cur.fetchall():
        sid = r['site_id']
        if sid not in result:
            result[sid] = {}
        result[sid][r['status']] = r['cnt']
    conn.close()
    return result


# ===== CONTRACTS (계약) =====

def get_contracts(site_id=None, unit_id=None, contract_type=None, active_only=False):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT ct.*,
               u.unit_no, u.status AS unit_status,
               c.complex_name,
               b.building_no
        FROM contracts ct
        JOIN units u ON ct.unit_id = u.id
        JOIN complexes c ON u.complex_id = c.id
        JOIN buildings b ON u.building_id = b.id
        WHERE 1=1
    """
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
        query += " AND u.status IN ('가계약', '계약')"
    query += " ORDER BY ct.contract_date DESC, ct.created_at DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_contract(contract_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT ct.*,
               u.unit_no, u.status AS unit_status,
               c.complex_name,
               b.building_no
        FROM contracts ct
        JOIN units u ON ct.unit_id = u.id
        JOIN complexes c ON u.complex_id = c.id
        JOIN buildings b ON u.building_id = b.id
        WHERE ct.id=?
    """, (contract_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_contract(unit_id, site_id, customer_name, phone=None, address=None,
                 contract_type='가계약', contract_date=None, deposit_total=0,
                 assigned_team=None, assigned_staff=None, notes=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contracts
            (unit_id, site_id, customer_name, phone, address,
             contract_type, contract_date, deposit_total,
             assigned_team, assigned_staff, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (unit_id, site_id, customer_name, phone, address,
          contract_type, contract_date, deposit_total,
          assigned_team, assigned_staff, notes))
    # 호실 상태 동기화
    cur.execute("UPDATE units SET status=? WHERE id=?", (contract_type, unit_id))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_contract(contract_id, customer_name, phone=None, address=None,
                    contract_type='가계약', contract_date=None, deposit_total=0,
                    assigned_team=None, assigned_staff=None, notes=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE contracts
        SET customer_name=?, phone=?, address=?,
            contract_type=?, contract_date=?, deposit_total=?,
            assigned_team=?, assigned_staff=?, notes=?
        WHERE id=?
    """, (customer_name, phone, address,
          contract_type, contract_date, deposit_total,
          assigned_team, assigned_staff, notes, contract_id))
    # 호실 상태 동기화
    cur.execute("SELECT unit_id FROM contracts WHERE id=?", (contract_id,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE units SET status=? WHERE id=?", (contract_type, row[0]))
    conn.commit()
    conn.close()


def delete_contract(contract_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT unit_id FROM contracts WHERE id=?", (contract_id,))
    row = cur.fetchone()
    cur.execute("DELETE FROM contracts WHERE id=?", (contract_id,))
    if row:
        cur.execute("UPDATE units SET status='공실' WHERE id=?", (row[0],))
    conn.commit()
    conn.close()


# ===== TRANSACTIONS (입출금) =====

def get_transactions(site_id=None, unit_id=None, tx_type=None):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT t.*,
               u.unit_no,
               c.complex_name,
               b.building_no
        FROM transactions t
        LEFT JOIN units u ON t.unit_id = u.id
        LEFT JOIN complexes c ON u.complex_id = c.id
        LEFT JOIN buildings b ON u.building_id = b.id
        WHERE 1=1
    """
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
    query += " ORDER BY t.date DESC, t.created_at DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_transaction(tx_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_transaction(site_id, date, depositor=None, customer=None, account=None,
                    amount=0, tx_type='입금', notes=None, unit_id=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions
            (unit_id, site_id, date, depositor, customer, account, amount, type, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (unit_id, site_id, date, depositor, customer, account, amount, tx_type, notes))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_transaction(tx_id, date, depositor=None, customer=None, account=None,
                       amount=0, tx_type='입금', notes=None, unit_id=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE transactions
        SET unit_id=?, date=?, depositor=?, customer=?,
            account=?, amount=?, type=?, notes=?
        WHERE id=?
    """, (unit_id, date, depositor, customer, account, amount, tx_type, notes, tx_id))
    conn.commit()
    conn.close()


def delete_transaction(tx_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()


def get_transaction_summary(site_id):
    """현장별 입출금 합계 반환."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT type, SUM(amount) AS total
        FROM transactions
        WHERE site_id=?
        GROUP BY type
    """, (site_id,))
    rows = {r['type']: r['total'] or 0 for r in cur.fetchall()}
    conn.close()
    return rows


# ===== CANCELLATIONS (해지) =====

def get_cancellations(site_id=None, unit_id=None):
    conn = get_conn()
    cur = conn.cursor()
    query = """
        SELECT cl.*,
               u.unit_no,
               u.type  AS unit_type,
               c.complex_name,
               b.building_no,
               ct.customer_name, ct.contract_type, ct.phone
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
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_cancellation(cancel_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cancellations WHERE id=?", (cancel_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_cancellation(unit_id, contract_id=None, cancel_date=None,
                     refund_amount=0, bank=None, account_no=None,
                     status='해지', notes=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cancellations
            (unit_id, contract_id, cancel_date, refund_amount,
             bank, account_no, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (unit_id, contract_id, cancel_date, refund_amount,
          bank, account_no, status, notes))
    # 호실 상태를 '해지'로 변경
    cur.execute("UPDATE units SET status='해지' WHERE id=?", (unit_id,))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_cancellation(cancel_id, cancel_date=None, refund_amount=0,
                        bank=None, account_no=None, status='해지', notes=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE cancellations
        SET cancel_date=?, refund_amount=?, bank=?,
            account_no=?, status=?, notes=?
        WHERE id=?
    """, (cancel_date, refund_amount, bank, account_no, status, notes, cancel_id))
    conn.commit()
    conn.close()


def delete_cancellation(cancel_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT unit_id FROM cancellations WHERE id=?", (cancel_id,))
    row = cur.fetchone()
    cur.execute("DELETE FROM cancellations WHERE id=?", (cancel_id,))
    if row:
        cur.execute("UPDATE units SET status='공실' WHERE id=?", (row[0],))
    conn.commit()
    conn.close()


# ===== BULK UPLOAD =====

def bulk_upload_units(site_id, rows):
    """
    단지/동/호실 일괄 upsert.
    rows: list of dicts (complex_no, complex_name, building_no, unit_no,
                         type_, floor, line, sale_price, rental_price)
    Returns (n_complexes, n_buildings, n_units) — distinct counts processed.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        complex_cache = {}   # complex_no -> complex_id
        building_cache = {}  # (complex_id, building_no) -> building_id

        for row in rows:
            complex_no = int(row['complex_no'])
            complex_name = str(row['complex_name']).strip()
            building_no = str(row['building_no']).strip()
            unit_no = str(row['unit_no']).strip()
            type_ = str(row.get('type_') or '').strip() or None
            try:
                floor = int(row['floor']) if row.get('floor') is not None else None
            except (ValueError, TypeError):
                floor = None
            line = str(row.get('line') or '').strip() or None
            try:
                sale_price = int(float(row.get('sale_price') or 0))
            except (ValueError, TypeError):
                sale_price = 0
            try:
                rental_price = int(float(row.get('rental_price') or 0))
            except (ValueError, TypeError):
                rental_price = 0

            # Upsert complex
            if complex_no not in complex_cache:
                cur.execute(
                    "SELECT id FROM complexes WHERE site_id=? AND complex_no=?",
                    (site_id, complex_no),
                )
                r = cur.fetchone()
                if r:
                    cur.execute(
                        "UPDATE complexes SET complex_name=? WHERE id=?",
                        (complex_name, r[0]),
                    )
                    complex_cache[complex_no] = r[0]
                else:
                    cur.execute(
                        "INSERT INTO complexes (site_id, complex_no, complex_name) VALUES (?, ?, ?)",
                        (site_id, complex_no, complex_name),
                    )
                    complex_cache[complex_no] = cur.lastrowid

            complex_id = complex_cache[complex_no]

            # Upsert building
            bk = (complex_id, building_no)
            if bk not in building_cache:
                cur.execute(
                    "SELECT id FROM buildings WHERE site_id=? AND complex_id=? AND building_no=?",
                    (site_id, complex_id, building_no),
                )
                r = cur.fetchone()
                if r:
                    building_cache[bk] = r[0]
                else:
                    cur.execute(
                        "INSERT INTO buildings (site_id, complex_id, building_no) VALUES (?, ?, ?)",
                        (site_id, complex_id, building_no),
                    )
                    building_cache[bk] = cur.lastrowid

            building_id = building_cache[bk]

            # Upsert unit
            cur.execute(
                "SELECT id FROM units WHERE site_id=? AND building_id=? AND unit_no=?",
                (site_id, building_id, unit_no),
            )
            r = cur.fetchone()
            if r:
                cur.execute(
                    """UPDATE units SET type=?, floor=?, line=?, sale_price=?, rental_price=?
                       WHERE id=?""",
                    (type_, floor, line, sale_price, rental_price, r[0]),
                )
            else:
                cur.execute(
                    """INSERT INTO units
                           (site_id, complex_id, building_id, unit_no, type, floor, line,
                            sale_price, rental_price, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '공실')""",
                    (site_id, complex_id, building_id, unit_no, type_, floor, line,
                     sale_price, rental_price),
                )

        conn.commit()
        return len(complex_cache), len(building_cache), len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
