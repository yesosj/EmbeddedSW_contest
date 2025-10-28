import time
import board
import neopixel
import serial

# === LED 설정 (라즈4 직접 제어 A/B) ===
BRIGHTNESS = 1.0
COLOR = (0,0,255)  # 예시 색상

pixels_a = neopixel.NeoPixel(board.D12, 8, brightness=BRIGHTNESS, auto_write=False)
pixels_b = neopixel.NeoPixel(board.D13, 12, brightness=BRIGHTNESS, auto_write=False)
local_strips = [pixels_a, pixels_b]

# === UART 설정 (라즈3로 데이터 전송 C/D) ===
ser = serial.Serial('/dev/serial0', 115200, timeout=0.1)

# OFF 색상
OFF = (0,0,0)

# ===== 유틸 함수 =====
def fill_strips(strips, color):
    for strip in strips:
        for i in range(len(strip)):
            strip[i] = color
        strip.show()

def send_uart(strip_name, color):
    """라즈3로 strip_name(C/D)과 RGB 색상 전송"""
    r, g, b = color
    ser.write(f"{strip_name},{r},{g},{b}\n".encode())

def energy_blink_all(color, blink_times=1000, delay=0.1):  
   
    for _ in range(blink_times):
        # A/B 직접 ON
        fill_strips(local_strips, color)
        # C/D UART ON
        send_uart("C", color)
        send_uart("D", color)
        time.sleep(delay)

        # A/B OFF
        fill_strips(local_strips, OFF)
        # C/D UART OFF
        send_uart("C", OFF)
        send_uart("D", OFF)
        time.sleep(delay)

# ===== 메인 실행 =====
def energy_effect():
    try:
        # 라즈3에 에너지 모드 요청
        ser.write(b"energy\n")
        print("라즈3에 ENERGY 모드 요청 완료")

        energy_blink_all(COLOR)

    except KeyboardInterrupt:
        fill_strips(local_strips, OFF)
        send_uart("C", OFF)
        send_uart("D", OFF)
        ser.close()
        print("ENERGY 종료")
