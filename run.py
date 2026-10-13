"""
run.py — TAESUNG WEB 실행기 (바로가기·bat이 이 파일을 실행한다)

- 이미 실행 중이면 서버를 또 띄우지 않고 브라우저만 연다.
- 아니면 서버를 띄우고, 준비되면 브라우저를 연다.
- 이 창을 닫으면 앱이 종료된다.
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8501
URL = f"http://localhost:{PORT}"


_job = None   # 실행기가 끝나면(창 닫기·강제 종료 포함) 서버도 함께 끝나도록 묶는 Windows 작업 개체


def bind_to_launcher(proc):
    """서버 프로세스를 이 실행기와 수명을 같이하게 묶는다 (Windows Job Object, KILL_ON_JOB_CLOSE)."""
    global _job
    if os.name != 'nt':
        return
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ('r_ops', 'w_ops', 'o_ops', 'r_bytes', 'w_bytes', 'o_bytes')]

    class BASIC(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD)]

    class EXTENDED(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO_COUNTERS),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
    hproc = k32.OpenProcess(0x0101, False, proc.pid)        # PROCESS_SET_QUOTA | PROCESS_TERMINATE
    if job and hproc and k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(hproc)):
        _job = job                                          # 핸들을 쥐고 있어야 함 (닫히면 서버 종료)


def is_up():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def main():
    if is_up():
        print(f"TAESUNG WEB이 이미 실행 중입니다. 브라우저만 엽니다: {URL}")
        webbrowser.open(URL)
        time.sleep(3)
        return
    print("TAESUNG WEB 시작 중... (이 창을 닫으면 종료됩니다)")
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py",
                             "--server.port", str(PORT), "--server.headless", "true"], cwd=HERE)
    bind_to_launcher(proc)
    for _ in range(120):            # 최대 60초 대기
        if is_up():
            print(f"준비 완료: {URL}")
            webbrowser.open(URL)
            break
        if proc.poll() is not None:
            print("\n실행에 실패했습니다. 패키지가 없으면 아래를 실행하세요:")
            print(f'  "{sys.executable}" -m pip install -r requirements.txt')
            input("\n엔터를 누르면 창이 닫힙니다.")
            return
        time.sleep(0.5)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
