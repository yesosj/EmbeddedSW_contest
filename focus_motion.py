import time
import board
import neopixel
import serial

# === LED 설정 ===
BRIGHTNESS = 1.0
COLOR = (255, 255, 0)

pixels_a = neopixel.NeoPixel(board.D12, 8, brightness=BRIGHTNESS, auto_write=False)
pixels_b = neopixel.NeoPixel(board.D13, 12, brightness=BRIGHTNESS, auto_write=False)
strips = {'A': pixels_a, 'B': pixels_b}

# === UART 설정 ===
ser = serial.Serial('/dev/serial0', 115200, timeout=0.1)

# ===== 유틸 함수 =====
def scale_color(color, level):
    r, g, b = color
    return (int(r * level / 100), int(g * level / 100), int(b * level / 100))

def fill_strip(strip, level, index=None):
    if index is None:
        color = scale_color(COLOR, level)
        for i in range(len(strip)):
            strip[i] = color
    else:
        strip[index] = scale_color(COLOR, level)
    strip.show()

def send_uart(strip_name):
    """라즈3로 LED 점등 명령 전송 후 완료 대기"""
    ser.write(f"{strip_name},100\n".encode())
    # ✅ 라즈3에서 DONE 수신 대기
    while True:
        line = ser.readline().decode().strip()
        if line == "DONE":
            break

def circular_fill(strip_name, strip, duration=0.08):
    """라즈4 스트립 순차 점등 → 순차 소등 (A는 반대 방향)"""
    num_pixels = len(strip)

    if strip_name == 'A':
        # A: 역방향 점등/소등
        # 점등
        for i in reversed(range(num_pixels)):
            fill_strip(strip, 100, i)
            time.sleep(duration)
        # 소등
        for i in reversed(range(num_pixels)):
            fill_strip(strip, 0, i)
            time.sleep(duration)
    else:
        # 기본: 정방향 점등/소등
        # 점등
        for i in range(num_pixels):
            fill_strip(strip, 100, i)
            time.sleep(duration)
        # 소등
        for i in range(num_pixels):
            fill_strip(strip, 0, i)
            time.sleep(duration)

# ===== 메인 실행 =====
def focus_effect():
    try:
        ser.write(b"focus\n")  # 라즈3 focus 모드 요청
        print("라즈3에 FOCUS 모드 요청 완료")

        while True:
            # 순서: D → C → B → A
            send_uart('D')                       # 라즈3 D 실행 (완료 대기)
            send_uart('C')                       # 라즈3 C 실행 (완료 대기)
            circular_fill('B', strips['B'], 0.2)  # 라즈4 B 실행
            circular_fill('A', strips['A'], 0.2)  # 라즈4 A 실행 (역방향)

    except KeyboardInterrupt:
        # 모두 OFF
        for strip in strips.values():
            fill_strip(strip, 0)
        ser.close()
        print("FOCUS 종료")
