# 영업부 관리 시스템 — 프로젝트 명세서

## 1. 시스템 개요

영업부 직원들의 출근을 기록하고, 일비와 숙소비를 자동 계산·정산하는 웹 앱.  
Python + Streamlit으로 구현, SQLite로 데이터 저장, Streamlit Cloud로 배포.

---

## 2. 기술 스택

```
Frontend  : Streamlit (Python)
Backend   : Python 3.11+
DB        : SQLite (sales_manager.db)
배포       : Streamlit Cloud (GitHub 연동)
라이브러리  : streamlit, pandas, openpyxl, sqlite3, datetime
```

---

## 3. DB 테이블 설계

### 3-1. 현장 (sites)
```sql
CREATE TABLE sites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,          -- 현장명 (예: 월하리 세종)
    region      TEXT NOT NULL,          -- 지역 (예: 세종, 경기광주)
    start_date  DATE,                   -- 현장 시작일
    status      TEXT DEFAULT '진행중',  -- 진행중 / 완료
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3-2. 직원 (employees)
```sql
CREATE TABLE employees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id         INTEGER REFERENCES sites(id),
    name            TEXT NOT NULL,
    team            TEXT,               -- 팀명 (예: 1팀, 2팀)
    phone           TEXT,
    first_work_date DATE,               -- 첫 출근일 (핵심)
    housing_region  TEXT DEFAULT '해당지역',  -- 해당지역 / 타지역 (숙소비 구분)
    status          TEXT DEFAULT '재직',     -- 재직 / 퇴직
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3-3. 출근기록 (attendance)
```sql
CREATE TABLE attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER REFERENCES employees(id),
    work_date   DATE NOT NULL,
    is_present  INTEGER DEFAULT 1,  -- 1=출근, 0=결근
    UNIQUE(employee_id, work_date)
);
```

### 3-4. 사용자/권한 (users)
```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,         -- sha256 해시
    role        TEXT NOT NULL,         -- admin / manager / viewer
    site_id     INTEGER REFERENCES sites(id),  -- manager는 담당 현장만
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3-5. 정산이력 (settlement_history)
```sql
CREATE TABLE settlement_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id         INTEGER REFERENCES sites(id),
    employee_id     INTEGER REFERENCES employees(id),
    settlement_type TEXT,    -- 'daily_allowance' / 'housing'
    execution_date  DATE,    -- 집행일
    period_start    DATE,    -- 판정기간 시작
    period_end      DATE,    -- 판정기간 종료
    work_days       INTEGER, -- 출근일수
    amount          INTEGER, -- 지급액
    status          TEXT DEFAULT '확정',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. 권한 구조

| 권한 | 가능한 작업 |
|------|------------|
| admin (관리자) | 전체 현장 조회·수정, 직원 등록·수정, 모든 정산 조회, 사용자 관리 |
| manager (현장담당자) | 담당 현장만 출근 입력, 담당 현장 정산 조회 |
| viewer (뷰어) | 전체 현장 열람만 가능 (수정 불가) |

---

## 5. 화면 구성 (Streamlit 페이지)

### 페이지 목록
```
pages/
├── 1_현장관리.py
├── 2_직원관리.py
├── 3_출근입력.py
├── 4_일비정산.py
├── 5_숙소비정산.py
└── 6_사용자관리.py (admin만)

app.py  ← 로그인 화면 + 메인 진입점
db.py   ← DB 연결·초기화·CRUD 함수 모음
calc.py ← 일비·숙소비 계산 로직
```

---

## 6. 일비 계산 로직 (calc.py에 구현)

### 6-1. 기본 규칙
- 출근 1일당 일비 **10,000원**
- 매월 **1차(1일~15일)**, **2차(16일~말일)** 로 구분
- 해당 구간 **70% 이상 + 11일 이상** 출근 시 지급
- 70% 충족하나 **11일 미만**이면 → 다음 차수로 **이월**
- 이월은 **1회만** 가능 (2회 연속 이월 불가 → 소멸)

### 6-2. 조회 방식
- **조회 집행월** (예: 5월)과 **차수** (1 또는 2) 선택
- 해당 차수 집행 대상자와 지급액 자동 계산

### 6-3. 이월 처리
```
예시: 4월 1차에 70% 충족했으나 8일만 출근 → 이월
      4월 2차에 15일 출근 → 이월분(8일) + 2차(15일) = 23일 합산 지급
```

### 6-4. 파이썬 계산 함수 구조
```python
def calc_daily_allowance(employee_id, year, month, term):
    """
    term: 1 or 2
    반환: {
        'work_days': int,       # 출근일수
        'possible_days': int,   # 가능일수
        'threshold': int,       # 기준일수 (올림)
        'status': str,          # '지급' / '이월' / '미충족'
        'carry_over': bool,     # 직전차수 이월 여부
        'pay_days': int,        # 지급 일수
        'amount': int           # 지급액
    }
    """
```

---

## 7. 숙소비 계산 로직 (calc.py에 구현)

### 7-1. 기본 규칙
- 해당지역: **200,000원** / 타지역: **300,000원** (직원별 설정)
- 첫출근일로부터 **30일간** 출근일수 산정
- **25일 이상** 출근 시 지급

### 7-2. 판정기간 계산

**첫출근일이 1일인 경우:**
- 판정기간 = 해당월 1일 ~ 말일 (반복)
- 집행일 = 판정종료 **익월 5일**
- 매달 반복 (5월1일~5월31일 → 6월5일 집행)

**첫출근일이 1일이 아닌 경우:**
- 판정기간 = 첫출근일 ~ 첫출근일+29일 (30일간, 반복)
- 집행일 계산:
  - 판정종료일이 **1일~4일** → 같은달 **5일** 집행
  - 판정종료일이 **5일~말일** → 같은달 **20일** 집행

### 7-3. 조회 집행일 기준 판정기간 역산

```
집행일이 5일인 경우:
  → 판정기간 = 전월 1일 ~ 전월 말일
  → 대상자: 첫출근일이 1일인 모든 직원

집행일이 20일인 경우:
  → 판정기간 = 개인별 (첫출근일 + 30*k) ~ (첫출근일 + 30*k + 29)
  → k = 조회집행월 - 첫출근월 - 1 (판정종료가 집행월 내에 오는 회차)
  → 대상자: 집행예정일이 조회집행일과 일치하는 직원
```

### 7-4. 파이썬 계산 함수 구조
```python
def calc_housing(employee_id, execution_date):
    """
    execution_date: datetime.date (집행일, 5일 또는 20일)
    반환: {
        'period_start': date,   # 판정기간 시작
        'period_end': date,     # 판정기간 종료
        'work_days': int,       # 출근일수
        'is_qualified': bool,   # 25일 이상 여부
        'execution_date': date, # 집행예정일
        'is_target': bool,      # 조회집행일 대상 여부
        'amount': int           # 지급액 (해당지역/타지역)
    }
    """
```

---

## 8. 화면별 상세 기능

### 8-1. 로그인 (app.py)
- 아이디/비밀번호 입력
- 로그인 성공 시 session_state에 user 정보 저장
- 권한에 따라 사이드바 메뉴 다르게 표시

### 8-2. 현장 관리
- 현장 목록 테이블 표시
- 현장 추가/수정/삭제 (admin만)
- 현장별 직원 수, 진행 상태 표시

### 8-3. 직원 관리
- 현장 선택 → 해당 현장 직원 목록
- 직원 추가: 이름, 팀, 연락처, 첫출근일, 지역구분
- 직원 수정/퇴직 처리
- 현장담당자는 담당 현장만 접근 가능

### 8-4. 출근 입력
- 현장 선택 → 월 선택
- 직원별 날짜 칸에 클릭으로 O/빈칸 토글
- 저장 버튼으로 DB 업데이트
- 주말 열 색상 다르게 표시

### 8-5. 일비 정산
- 조회: 연도, 월, 차수(1/2) 선택
- 결과: 직원별 출근일수, 가능일수, 충족여부, 이월여부, 지급액
- 이월 대상자 노란색 강조
- 하단: 총 지급액 합계
- 엑셀 다운로드 버튼

### 8-6. 숙소비 정산
- 조회: 집행일 날짜 입력 (예: 2026-06-05)
- 결과: 직원별 판정기간, 출근일수, 충족여부, 집행예정일, 지급액
- ★ 집행대상 강조 표시
- 하단: 총 지급액 합계
- 엑셀 다운로드 버튼

### 8-7. 사용자 관리 (admin만)
- 사용자 목록
- 사용자 추가: 아이디, 비밀번호, 권한, 담당현장
- 비밀번호 변경

---

## 9. 엑셀 다운로드 형식

일비 정산 엑셀:
```
컬럼: 구분 | 팀 | 이름 | 출근일수 | 가능일수 | 충족여부 | 이월여부 | 지급일수 | 지급액
```

숙소비 정산 엑셀:
```
컬럼: 구분 | 팀 | 이름 | 지역구분 | 첫출근일 | 판정시작 | 판정종료 | 출근일수 | 충족여부 | 집행예정일 | 지급액
```

---

## 10. 초기 실행 방법 (Claude Code에게 지시)

```bash
# 1. 패키지 설치
pip install streamlit pandas openpyxl

# 2. 앱 실행
streamlit run app.py

# 3. 브라우저에서 확인
http://localhost:8501
```

초기 관리자 계정:
- 아이디: admin
- 비밀번호: admin1234

---

## 11. 파일 구조 (최종)

```
sales_manager/
├── app.py              ← 메인 진입점, 로그인
├── db.py               ← DB 초기화, CRUD 함수
├── calc.py             ← 일비·숙소비 계산 로직
├── requirements.txt    ← 패키지 목록
├── sales_manager.db    ← SQLite DB (자동 생성)
├── .streamlit/
│   └── config.toml     ← Streamlit 설정
└── pages/
    ├── 1_현장관리.py
    ├── 2_직원관리.py
    ├── 3_출근입력.py
    ├── 4_일비정산.py
    ├── 5_숙소비정산.py
    └── 6_사용자관리.py
```

---

## 12. Claude Code 첫 지시문 (복사해서 사용)

```
requirements.md를 읽고 영업부 관리 시스템을 만들어줘.

순서:
1. db.py 먼저 만들어서 DB 초기화 및 CRUD 함수 구현
2. calc.py에 일비·숙소비 계산 로직 구현
3. app.py 로그인 화면 구현
4. pages/ 폴더에 각 화면 구현
5. 완성 후 streamlit run app.py 실행해서 확인

초기 데이터로 테스트 현장 1개, 직원 5명, 관리자 계정(admin/admin1234) 자동 생성해줘.
```
