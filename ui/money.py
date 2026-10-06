"""ui/money.py — 입력하는 동안 천단위 쉼표가 찍히는 금액 입력칸 (st.components.v2)

    amount = money.money_input("입금액", key="tx_amt", value=0)

- 숫자 외 문자는 무시하고, 입력 중에 바로 1,000,000 형태로 보여준다.
- 아래에 '1억 2,000만원'처럼 한글 금액을 함께 보여준다.
- 값은 입력을 멈추고 0.35초 뒤(또는 칸을 벗어날 때) 파이썬으로 전달된다.
- st.form 안에서는 쓰지 않는다 (폼은 제출 전까지 값을 보내지 않음).
"""
import streamlit as st

CSS = """
.mi { font-family: 'Noto Sans KR', sans-serif; }
.mi label { display:block; font-size:14px; color:#1F2937; margin-bottom:6px; }
.mi input { width:100%; box-sizing:border-box; height:40px; padding:0 12px; font-size:15px; text-align:right;
            font-family:inherit; color:#111827; background:#E9EDF2; border:1px solid #D5DBE3; border-radius:4px;
            outline:none; font-variant-numeric: tabular-nums; }
.mi input:focus { border-color:#1F4E8C; background:#fff; }
.mi .hint { font-size:12px; color:#6B7686; margin-top:3px; min-height:16px; text-align:right; }
"""

JS = """
function fmt(n) { return n ? Number(n).toLocaleString('ko-KR') : ''; }
function korean(n) {
    n = Number(n || 0);
    if (!n) return '';
    const eok = Math.floor(n / 100000000), man = Math.floor((n % 100000000) / 10000), won = n % 10000;
    const parts = [];
    if (eok) parts.push(eok.toLocaleString('ko-KR') + '억');
    if (man) parts.push(man.toLocaleString('ko-KR') + '만');
    if (won) parts.push(won.toLocaleString('ko-KR'));
    return parts.join(' ') + '원';
}
export default function(component) {
    const { data, setStateValue, parentElement } = component;
    let box = parentElement.querySelector('.mi');
    if (!box) {
        box = document.createElement('div');
        box.className = 'mi';
        box.innerHTML = '<label></label><input inputmode="numeric" autocomplete="off"><div class="hint"></div>';
        parentElement.appendChild(box);
        const input = box.querySelector('input'), hint = box.querySelector('.hint');
        let timer = null;
        const send = () => { clearTimeout(timer); setStateValue('value', Number(input.dataset.raw || 0)); };
        input.addEventListener('input', () => {
            const digits = input.value.replace(/[^0-9]/g, '').replace(/^0+(?=\\d)/, '');
            const fromEnd = input.value.length - input.selectionStart;
            input.dataset.raw = digits;
            input.value = fmt(digits);
            const pos = Math.max(0, input.value.length - fromEnd);
            input.setSelectionRange(pos, pos);
            hint.textContent = korean(digits);
            clearTimeout(timer);
            timer = setTimeout(send, 350);
        });
        input.addEventListener('blur', send);
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
        const v = String(data.value || '');
        input.dataset.raw = v === '0' ? '' : v;
        input.value = fmt(input.dataset.raw);
        hint.textContent = korean(input.dataset.raw);
    }
    box.querySelector('label').textContent = data.label || '';
    box.querySelector('input').placeholder = data.placeholder || '';
    box.querySelector('input').disabled = !!data.disabled;
}
"""


def _component():
    # 매 실행 등록 (같은 정의면 경고 없이 덮어씀)
    return st.components.v2.component("ts_money_input", css=CSS, js=JS)


def money_input(label, key, value=0, placeholder="0", disabled=False):
    """금액(int)을 반환. 초기화하려면 key를 바꾼다 (예: 저장 후 카운터 증가)."""
    res = _component()(data={'label': label, 'value': int(value or 0), 'placeholder': placeholder,
                             'disabled': disabled},
                       default={'value': int(value or 0)}, key=key, on_value_change=lambda: None)
    try:
        return int(getattr(res, 'value', 0) or 0)
    except (TypeError, ValueError):
        return 0


def next_round(name):
    """입력칸 묶음을 비우기 위한 키 카운터."""
    st.session_state[name] = st.session_state.get(name, 0) + 1


def round_of(name):
    return st.session_state.get(name, 0)
