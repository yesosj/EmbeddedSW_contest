import time
import board
import neopixel
import serial
import threading
from typing import Optional

BRIGHTNESS = 1.0
pixels_a = neopixel.NeoPixel(board.D12, 8,  brightness=BRIGHTNESS, auto_write=False)
pixels_b = neopixel.NeoPixel(board.D13, 12, brightness=BRIGHTNESS, auto_write=False)

# 라즈3(UART) 통신
ser = serial.Serial('/dev/serial0', 115200, timeout=0.1)

# 감정 → 색상
COLOR_BY_FEELING = {
    "happy": (255, 255, 0),  # yellow
    "sad":   (0,   0, 255),  # blue
    "angry": (255, 0,   0),  # red
}
_FEELING_TO_NAME = {
    "happy" : "yellow",
    "sad" : "blue",
    "angry" : "red",
}
DEFAULT_COLOR = (255, 255, 255)
_DEFAULT_NAME = "white"
def _scale_color(color, level):
    r, g, b = color
    return (int(r * level / 100), int(g * level / 100), int(b * level / 100))

def _fill_strip(strip, level, color):
    c = _scale_color(color, max(0, min(100, int(level))))
    for i in range(len(strip)):
        strip[i] = c
    strip.show()

def _fade(strip, start, end, duration=0.5, steps=50, color=(255,0,0), stop_event: Optional[threading.Event] = None) -> bool:
    steps = max(1, int(steps))
    delay = duration / steps
    for i in range(steps + 1):
        if stop_event and stop_event.is_set():
            return False
        level = start + (end - start) * i / steps
        _fill_strip(strip, level, color)
        time.sleep(delay)
    return True

def _send_to_raspi3(name: str, brightness: int, color_name: str):
    try:
        command = f"{name},{int(brightness)},{color_name}\n".encode()
        ser.write(command)
        ser.flush()
    except Exception as e:
        print(f"UART write error: {e}")
        pass

def _sleep_check(sec: float, stop_event: Optional[threading.Event] = None) -> None:
    end = time.time() + sec
    while time.time() < end:
        if stop_event and stop_event.is_set():
            break
        time.sleep(0.01)

def healing_effect(current_feeling: str, wanted_feeling: str = "healing", stop_event: Optional[threading.Event] = None) -> None:
    """
    라즈4: A/B 페이드, 라즈3: C/D 밝기 명령 전송
    current_feeling에 따라 색상 지정
    """
    color_rgb = COLOR_BY_FEELING.get(current_feeling, DEFAULT_COLOR)
    color_name = _FEELING_TO_NAME.get(current_feeling, _DEFAULT_NAME)

    try:
        ser.write(b"healing\n")
        _sleep_check(0.2,stop_event)
        while not (stop_event and stop_event.is_set()):
            if not _fade(pixels_a, 0, 100, duration=0.5, steps=50, color=color_rgb, stop_event=stop_event): break
            if not _fade(pixels_a, 100, 0, duration=0.5, steps=50, color=color_rgb, stop_event=stop_event): break
            if not _fade(pixels_b, 0, 100, duration=0.5, steps=50, color=color_rgb, stop_event=stop_event): break
            if not _fade(pixels_b, 100, 0, duration=0.5, steps=50, color=color_rgb, stop_event=stop_event): break

            _send_to_raspi3('C', 100, color_name); #_sleep_check(5, stop_event)
            _send_to_raspi3('C', 0, color_name);   _sleep_check(2, stop_event)

            _send_to_raspi3('D', 100, color_name); #_sleep_check(5, stop_event)
            _send_to_raspi3('D', 0, color_name);   _sleep_check(1.5, stop_event)
    finally:
        # 안전 종료
        _fill_strip(pixels_a, 0, color_rgb)
        _fill_strip(pixels_b, 0, color_rgb)
        _send_to_raspi3('C', 0 , color_name)
        _send_to_raspi3('D', 0, color_name)

def cleanup():
    """프로그램 종료 시 호출 권장"""
    try:
        _send_to_raspi3('C', 0, _DEFAULT_NAME)
        _send_to_raspi3('D', 0 , _DEFAULT_NAME)
    except Exception:
        pass
    try:
        ser.close()
    except Exception:
        pass

stop_event = threading.Event()

if __name__ == "__main__":
    print("Healing test")
    healing_effect(current_feeling = "sad" , stop_event = stop_event)
