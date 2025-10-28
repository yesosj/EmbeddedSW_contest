# ====== 라즈4 코드 (pi4_love.py) ======
import time
import board
import neopixel
import serial

# === LED 설정 (라즈4 직접 제어 A, B) ===
BRIGHTNESS = 1.0
COLOR = (255, 0, 0)

pixels_a = neopixel.NeoPixel(board.D12, 8, brightness=BRIGHTNESS, auto_write=False)
pixels_b = neopixel.NeoPixel(board.D13, 12, brightness=BRIGHTNESS, auto_write=False)
local_strips = [pixels_a, pixels_b]

# === UART 설정 (라즈3로 데이터 전송) ===
ser = serial.Serial('/dev/serial0', 115200, timeout=0.1)

# ===== 유틸 함수 =====
def scale_color(color, level):
    r, g, b = color
    return (int(r * level / 100), int(g * level / 100), int(b * level / 100))

def fill_strips(strips, level):
    color = scale_color(COLOR, level)
    for strip in strips:
        for i in range(len(strip)):
            strip[i] = color
        strip.show()

def send_uart(level):
    """라즈3으로 밝기 전달"""
    ser.write(f"C,{level}\n".encode())
    ser.write(f"D,{level}\n".encode())

def fade(level_start, level_end, duration=0.2, steps=20):
    delay = duration / steps
    for i in range(steps + 1):
        level = int(level_start + (level_end - level_start) * i / steps)
        fill_strips(local_strips, level)   # A, B 직접 제어
        send_uart(level)                   # C, D는 UART 전송
        time.sleep(delay)

def heartbeat():
    fade(0, 100, duration=0.01)
    fade(100, 0, duration=0.01)
    fade(0, 100, duration=0.01)
    fade(100, 0, duration=0.33)
    time.sleep(0.2)

# ===== 메인 실행 =====
def love_effect():
    try:
        # 실행 시작 시 라즈3에 모드 전송
        ser.write(b"love\n")
        print("라즈3에 LOVE 모드 요청 완료")

        while True:
            heartbeat()

    except KeyboardInterrupt:
        fill_strips(local_strips, 0)
        send_uart(0)
        ser.close()
        print("LOVE 종료")
