import time
import threading
from typing import Optional

import board
import neopixel
import serial

# ================================
# 라즈4 로컬 스트립 (8픽셀, 12픽셀)
#  - 8  → board.D12
#  - 12 → board.D13
# ================================
LED_CONFIGS = {
    "8":  {"pin": board.D12, "count": 8},   # 변경됨
    "12": {"pin": board.D13, "count": 12},  # 변경됨
}

# 로컬(8/12) → 원격(C/D) 매핑
#  - C: RPi3의 16픽셀 링
#  - D: RPi3의 24픽셀 링
_LOCAL_TO_REMOTE = {"8": "C", "12": "D"}

# current_feeling → 색상/이름 매핑
_FEELING_TO_COLOR = {
    "happy": (255, 255, 0),   # yellow
    "sad":   (0,   0, 255),   # blue
    "angry": (255, 0,   0),   # red
}
_FEELING_TO_NAME = {
    "happy": "yellow",
    "sad":   "blue",
    "angry": "red",
}
_DEFAULT_COLOR = (255, 255, 255)
_DEFAULT_NAME  = "white"
_OFF = (0, 0, 0)

# === 송신 포맷 옵션 ===
# - False: rpi3의 현재 파서와 100% 호환 (권장: "relief\n" → "C,red\n")
# - True : "mode|payload" 한 줄도 허용(= "relief|C,red\n")
INLINE_MODE_PREFIX = False  # 필요 시 True

# UART (라즈3와 동일 속도 사용)
_uart = serial.Serial("/dev/serial0", 115200, timeout=1)

# 네오픽셀 인스턴스 (모듈 로드시 1회 생성)
_pixels_dict = {
    name: neopixel.NeoPixel(cfg["pin"], cfg["count"], brightness=1.0, auto_write=False)
    for name, cfg in LED_CONFIGS.items()
}

# ---------------- 유틸 ----------------
def _safe_sleep(sec: float, stop_event: Optional[threading.Event]) -> None:
    end = time.time() + sec
    while time.time() < end:
        if stop_event and stop_event.is_set():
            break
        time.sleep(0.01)

def _fade_in_pair(pixels, p1: int, p2: int, color, max_brightness=1.0,
                  steps=10, delay=0.05, stop_event: Optional[threading.Event] = None) -> bool:
    r, g, b = color
    for step in range(steps):
        if stop_event and stop_event.is_set():
            return False
        level = max_brightness * (step + 1) / steps
        fade_color = (int(r * level), int(g * level), int(b * level))
        pixels[p1] = fade_color
        pixels[p2] = fade_color
        pixels.show()
        _safe_sleep(delay, stop_event)
    return True

def _turn_off_pair(pixels, p1: int, p2: int, steps=5, delay=0.05,
                   stop_event: Optional[threading.Event] = None) -> None:
    r, g, b = pixels[p1]
    for step in range(steps):
        if stop_event and stop_event.is_set():
            break
        level = 1 - (step + 1) / steps
        faded_color = (int(r * level), int(g * level), int(b * level))
        pixels[p1] = faded_color
        pixels[p2] = faded_color
        pixels.show()
        _safe_sleep(delay, stop_event)
    pixels[p1] = _OFF
    pixels[p2] = _OFF
    pixels.show()

def _relief_pattern(pixels, led_count: int, color, stop_event: Optional[threading.Event]) -> bool:
    """로컬(8/12) 링에서 대칭 페어 페이드 인/아웃 → 역방향"""
    num_pairs = led_count // 2
    pairs = [(i, led_count - 1 - i) for i in range(num_pairs)]
    # 정방향
    for idx, (p1, p2) in enumerate(pairs):
        if not _fade_in_pair(pixels, p1, p2, color,
                             max_brightness=(idx + 1) / len(pairs),
                             steps=10, delay=0.05, stop_event=stop_event):
            return False
    for p1, p2 in pairs:
        _turn_off_pair(pixels, p1, p2, steps=5, delay=0.05, stop_event=stop_event)
        if stop_event and stop_event.is_set():
            return False
    # 역방향
    pairs_reverse = [(led_count - 1 - i, i) for i in range(num_pairs)]
    for idx, (p1, p2) in enumerate(pairs_reverse):
        if not _fade_in_pair(pixels, p1, p2, color,
                             max_brightness=(idx + 1) / len(pairs_reverse),
                             steps=10, delay=0.05, stop_event=stop_event):
            return False
    for p1, p2 in pairs_reverse:
        _turn_off_pair(pixels, p1, p2, steps=5, delay=0.05, stop_event=stop_event)
        if stop_event and stop_event.is_set():
            return False
    return True

# ---------------- 송신 헬퍼 ----------------
def _send_relief_to_rpi3(local_seg: str, color_name: str) -> None:
    """
    로컬 세그먼트(8/12)가 끝난 뒤 → RPi3의 대응 링(C/D)을 켜도록 트리거 전송.
    - 권장: 2줄 ("relief" → "C,red")
    - INLINE_MODE_PREFIX=True면 1줄 ("relief|C,red")
    """
    strip = _LOCAL_TO_REMOTE.get(local_seg)  # '8'→'C', '12'→'D'
    if not strip:
        return
    try:
        if INLINE_MODE_PREFIX:
            _uart.write(f"{strip},{color_name}\n".encode())
        else:
            _uart.write(b"relief\n")
            _uart.write(f"{strip},{color_name}\n".encode())
    except Exception as e:
        print(f"[relief] UART write error: {e}")

# (선택) 필요 시 포커스 트리거도 같은 맵으로 보낼 수 있게 헬퍼 유지
def _send_focus_to_rpi3(local_seg: str, color_name: str, brightness: int = 1) -> None:
    strip = _LOCAL_TO_REMOTE.get(local_seg)
    if not strip:
        return
    try:
        if INLINE_MODE_PREFIX:
            _uart.write(f"focus|{strip},{int(brightness)},{color_name}\n".encode())
        else:
            _uart.write(b"focus\n")
            _uart.write(f"{strip},{int(brightness)},{color_name}\n".encode())
    except Exception as e:
        print(f"[focus] UART write error: {e}")

# ---------------- 엔트리포인트 ----------------
def relief_effect(
    current_feeling: str,
    wanted_feeling: str = "relief",
    stop_event: Optional[threading.Event] = None
) -> None:
    """
    RPi4: 로컬 8→12 순서로 relief 패턴 실행
    RPi3: 각 로컬 구간 완료 시 C(16) → D(24) 순서로 트리거 전송
    """
    color = _FEELING_TO_COLOR.get(current_feeling, _DEFAULT_COLOR)
    color_name = _FEELING_TO_NAME.get(current_feeling, _DEFAULT_NAME)

    try:
        while not (stop_event and stop_event.is_set()):
            # 순서를 보장하기 위해 명시적으로 8 → 12 순회

            _uart.write(b"relief\n")
            _safe_sleep(0.02, stop_event)

            pixels8 = _pixels_dict["8"]
            ok = _relief_pattern(pixels8, LED_CONFIGS["8"]["count"], color, stop_event)
            if not ok or (stop_event and stop_event.is_set()):
                break

            pixels12 = _pixels_dict["12"]
            ok = _relief_pattern(pixels12, LED_CONFIGS["12"]["count"], color, stop_event)
            if not ok or (stop_event and stop_event.is_set()):
                break
            _safe_sleep(0.5, stop_event)
            _send_relief_to_rpi3("8", color_name)
            _safe_sleep(13, stop_event)
            _send_relief_to_rpi3("12", color_name)
            _safe_sleep(21, stop_event)

    finally:
        # 안전 종료: 모든 로컬 픽셀 Off
        for pixels in _pixels_dict.values():
            for i in range(len(pixels)):
                pixels[i] = _OFF
            pixels.show()

def cleanup() -> None:
    """프로그램 종료 시 호출 권장 (UART 닫기 등)"""
    try:
        for pixels in _pixels_dict.values():
            for i in range(len(pixels)):
                pixels[i] = _OFF
            pixels.show()
    except Exception:
        pass
    try:
        _uart.close()
    except Exception:
        pass

stop_event = threading.Event()

if __name__ == "__main__":

    print("'happy' mode active")
    relief_effect(current_feeling = "happy" , stop_event=stop_event)
