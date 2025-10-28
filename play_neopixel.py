import threading

# --- 모션 함수 임포트 ---
from healing_motion import healing_effect
from relief_motion import relief_effect
from energy_motion import energy_effect
from focus_motion  import focus_effect
from love_motion   import love_effect

# wanted_feeling -> 실행 함수 매핑
REGISTRY = {
    "healing": healing_effect,
     "relief": relief_effect,
     "energy": energy_effect,
     "focus":  focus_effect,
     "love":   love_effect,
}

# 내부 상태(딱 1개 스레드만 돌게 관리)
_motion_thread = None
_stop_evt = threading.Event()
_lock = threading.Lock()

def _run_effect(effect_fn, current_feeling, wanted_feeling, stop_evt):
    """
    모션 실행 러너. 각 모션 함수는 (current_feeling, wanted_feeling, stop_event) 시그니처 권장.
    """
    try:
        try:
            # 권장 시그니처
            if(wanted_feeling == "healing"):
                effect_fn(current_feeling, wanted_feeling, stop_evt)
            elif(wanted_feeling == "relief"):
                effect_fn(current_feeling, wanted_feeling, stop_evt)
            elif(wanted_feeling == "energy"):
                effect_fn()
            elif(wanted_feeling == "focus"):
                effect_fn()
            else:
                effect_fn()
        except TypeError:
            # 구(舊) 시그니처 호환: (current_feeling, wanted_feeling)만 받는 경우
            effect_fn(current_feeling, wanted_feeling)
    except Exception as e:
        print(f"[LED] motion '{wanted_feeling}' error: {e}")

def play_neopixel_effect(current_feeling: str, wanted_feeling: str):
    """
    메인에서 호출하는 '통합 진입점'.
    - 직전에 돌던 모션을 stop_event로 중단하고,
    - wanted_feeling에 맞는 효과를 새 스레드로 실행한다.
    """
    global _motion_thread, _stop_evt
    effect_fn = REGISTRY.get(wanted_feeling)
    if not effect_fn:
        print(f"[LED] Unknown or not-implemented motion: {wanted_feeling} (healing만 연결됨)")
        return

    with _lock:
        # 1) 이전 스레드 정지
        if _motion_thread and _motion_thread.is_alive():
            _stop_evt.set()
            _motion_thread.join(timeout=1.0)

        # 2) 새 stop 이벤트 생성
        _stop_evt = threading.Event()

        # 3) 새 모션 스레드 시작
        _motion_thread = threading.Thread(
            target=_run_effect,
            args=(effect_fn, current_feeling, wanted_feeling, _stop_evt),
            daemon=True
        )
        _motion_thread.start()

def stop_neopixel_effect():
    """
    외부(일시정지 버튼 등)에서 조명을 멈추고 싶을 때 호출.
    """
    global _motion_thread, _stop_evt
    with _lock:
        if _motion_thread and _motion_thread.is_alive():
            _stop_evt.set()
            _motion_thread.join(timeout=1.0)

def cleanup_neopixel():
    """
    프로그램 종료 시 호출 권장.
    """
    stop_neopixel_effect()
