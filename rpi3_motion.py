# 수신측 코드
import threading
import time
import board
import neopixel
import serial
from typing import Optional, Tuple

# === 공통 설정 ===
BRIGHTNESS = 1.0
COLOR = (255, 0, 0)  # love/focus/healing 기본 컬러(밝기 제어용)

# 16픽셀 → D18, 24픽셀 → D19
pixels_c = neopixel.NeoPixel(board.D18, 16, brightness=BRIGHTNESS, auto_write=False)
pixels_d = neopixel.NeoPixel(board.D19, 24, brightness=BRIGHTNESS, auto_write=False)
strips = {'C': pixels_c, 'D': pixels_d}
remote_strips = [pixels_c, pixels_d]

# relief에서 사용할 색상 이름 → RGB
COLOR_MAP = {
    "yellow": (255, 255, 0),
    "blue":   (0,   0, 255),
    "red":    (255, 0,   0),
    "white":  (255, 255, 255),
}
OFF = (0, 0, 0)

ser = serial.Serial('/dev/serial0', 115200, timeout=0.1)

# === 글로벌 상태 ===
current_mode = None
mode_thread = None
stop_flag = False

# ===== 공용 유틸 =====
def scale_color(color, level):
    r, g, b = color
    return (int(r * level / 100), int(g * level / 100), int(b * level / 100))

def fill_strips(local_strips, level):
    color = scale_color(COLOR, level)
    for strip in local_strips:  
        for i in range(len(strip)):
            strip[i] = color
        strip.show()

def fill_strip(strip, level, index=None, color=None):
    if color is None:
        color = COLOR
    if index is None:
        _color = scale_color(color, level)
        for i in range(len(strip)):
            strip[i] = _color
    else:
        strip[index] = scale_color(color, level)
    strip.show()

def fill_strip_healing(strip, level, color):
    c=scale_color(color, level)
    for i in range(len(strip)):
        strip[i]=c
    strip.show()


def fill_strip_color(strip, color):
    """RGB 색상 전체 채우기"""
    for i in range(len(strip)):
        strip[i] = color
    strip.show()

def fade_healing(strip,start,end,duration=0.5,steps=50,color=(255,0,0)):
    delay=duration/max(1,steps)
    for i in range(steps+1):
        if stop_flag: return
        level=start+(end-start)*i/steps
        fill_strip_healing(strip, level, color)
        time.sleep(delay)

def clear_all():
    fill_strip(pixels_c, 0)
    fill_strip(pixels_d, 0)

# ===== LOVE 모드 =====

def run_love():
    global stop_flag
    print("LOVE 모드 시작")

    while not stop_flag:
        if ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            if "," in line:
                try:
                    strip_name, brightness_str = line.split(",")
                    brightness = int(brightness_str)
                    if strip_name in strips:  # 'C' or 'D'
                        fill_strip(strips[strip_name], brightness)
                except Exception as e:
                    print(f"[LOVE] 데이터 오류: {e}, 값: {line}")
    print("LOVE 모드 종료")


# ===== FOCUS 모드 =====
def circular_fill(strip, duration=0.2, color=None):
    if color is None: color = COLOR
    """순차 점등 → 순차 소등"""
    num_pixels = len(strip)
    for i in range(num_pixels):
        fill_strip(strip, 100, i, color)
        time.sleep(duration)
    for i in range(num_pixels):
        fill_strip(strip, 0, i, color)
        time.sleep(duration)

def run_focus():
    global stop_flag
    print("FOCUS 모드 시작")

    while not stop_flag:
        if ser.in_waiting > 0:
            line = ser.readline().decode().strip()
            if "," in line:
                try:
                    strip_name, brightness_str = line.split(',')
                    brightness = int(brightness_str)

                    if strip_name in strips and brightness > 0:
                        print(f"[FOCUS] {strip_name} 실행 요청 수신")
                        circular_fill(strips[strip_name])
                        # ✅ 실행 완료 후 라즈4에 완료 신호 보내기
                        ser.write(b"DONE\n")

                except Exception as e:
                    print(f"[FOCUS] 데이터 오류: {e}, 값: {line}")
        time.sleep(0.01)
    print("FOCUS 모드 종료")

# ===== HEALING 모드 (수정됨) =====
def _parse_healing_cmd(line: str) -> Optional[Tuple[str, int, str]]:
    """
    Healing 명령 파서
      입력 예:
        'C,100,yellow'
        'D|75|blue'
        'ALL,80,red'
        '*, 60 , white'
      반환:
        (target: 'C'|'D'|'ALL', max_level:int(0~100), color_name:str)
      파싱 실패 시:
        None
    """
    if not line:
        return None

    # 구분자 통일 및 토큰화
    s = line.strip().replace('|', ',')
    parts = [p.strip() for p in s.split(',') if p.strip()]
    if len(parts) < 3:
        return None

    # 대상 스트립
    raw_target = parts[0].upper()
    if raw_target in ('ALL', '*'):
        target = 'ALL'
    else:
        target = raw_target[:1]  # 'C' 또는 'D'
        if target not in ('C', 'D'):
            return None

    # 밝기 (0~100, %, 소수 허용)
    raw_level = parts[1]
    if raw_level.endswith('%'):
        raw_level = raw_level[:-1].strip()
    try:
        level = int(float(raw_level))
    except ValueError:
        return None
    level = max(0, min(100, level))  # 클램프

    # 색상 이름 (소문자 정규화)
    color_name = parts[2].lower()

    return (target, level, color_name)


def run_healing():
    """
    UART 라인 수신 시에만 1사이클(상승→하강) 실행:
      - 'C,100,yellow' → C 링만 0→100→0
      - 'D|75|blue'    → D 링만 0→75→0
      - 'ALL,80,red'   → C/D 모두 0→80→0
    """
    global stop_flag
    print("HEALING 모드 대기중 (UART 트리거 기반)", flush=True)

    while not stop_flag:
        if ser.in_waiting == 0:
            time.sleep(0.01)
            continue

        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            continue

        parsed = _parse_healing_cmd(line)
        if not parsed:
            print(f"[HEALING] 잘못된 명령: {line}", flush=True)
            continue

        target, max_level, color_name = parsed

        # 색상 확인 (없으면 흰색으로 동작하되 경고 출력)
        if color_name not in COLOR_MAP:
            print(f"[HEALING] 미지원 색상: {color_name} → white로 대체", flush=True)
        color = COLOR_MAP.get(color_name, (255, 255, 255))

        # 대상 스트립 선택
        if target in ('C', 'D'):
            if target not in strips:
                print(f"[HEALING] 미지의 스트립: {target}", flush=True)
                continue
            targets = [strips[target]]
        else:  # 'ALL'
            targets = list(strips.values())

        print(f"[HEALING] target={target}, level={max_level}, color={color_name}", flush=True)

        # 1사이클 실행 (상승 → 하강)
        for strip in targets:
            if stop_flag:
                break
            fade_healing(strip, 0,         max_level, 0.5, 50, color)
            if stop_flag:
                break
            fade_healing(strip, max_level, 0,         0.5, 50, color)

        # (선택) ACK 전송
        # try:
        #     ser.write(b"DONE\n")
        #     ser.flush()
        # except Exception:
        #     pass

    print("HEALING 모드 종료", flush=True)


# ===== RELIEF 유틸 =====
def _fade_in_pair_relief(pixels, p1, p2, color, max_brightness=1.0, steps=10, delay=0.05):
    r, g, b = color
    for step in range(steps):
        if stop_flag: return False
        level = max_brightness * (step + 1) / steps  # 0~1
        fade_color = (int(r * level), int(g * level), int(b * level))
        pixels[p1] = fade_color
        pixels[p2] = fade_color
        pixels.show()
        time.sleep(delay)
    return True

def _turn_off_pair_relief(pixels, p1, p2, steps=5, delay=0.05):
    r, g, b = pixels[p1]
    for step in range(steps):
        if stop_flag: return
        level = 1 - (step + 1) / steps
        faded_color = (int(r * level), int(g * level), int(b * level))
        pixels[p1] = faded_color
        pixels[p2] = faded_color
        pixels.show()
        time.sleep(delay)
    pixels[p1] = OFF
    pixels[p2] = OFF
    pixels.show()

def relief_pattern(strip, led_count, color):
    """양끝-대칭 페어 순차 페이드 인/아웃 → 역방향 반복(1사이클)"""
    num_pairs = led_count // 2
    pairs = [(i, led_count - 1 - i) for i in range(num_pairs)]
    # 정방향
    for idx, (p1, p2) in enumerate(pairs):
        if not _fade_in_pair_relief(strip, p1, p2, color, max_brightness=(idx + 1) / len(pairs)):
            return False
    for p1, p2 in pairs:
        if stop_flag: return False
        _turn_off_pair_relief(strip, p1, p2)
    # 역방향
    pairs_rev = [(led_count - 1 - i, i) for i in range(num_pairs)]
    for idx, (p1, p2) in enumerate(pairs_rev):
        if not _fade_in_pair_relief(strip, p1, p2, color, max_brightness=(idx + 1) / len(pairs_rev)):
            return False
    for p1, p2 in pairs_rev:
        if stop_flag: return False
        _turn_off_pair_relief(strip, p1, p2)
    return True

def _parse_relief_cmd(line: str):
    """
    'C,red'  → ('C','red')
    'D|blue' → ('D','blue')
    대소문자/공백 무시, 색상 이름은 COLOR_MAP 키여야 함.
    """
    s = line.strip()
    if not s:
        return None
    if '|' in s:
        left, _, color = s.partition('|')
        return (left.strip().upper()[:1], color.strip().lower())
    if ',' in s:
        left, _, color = s.partition(',')
        return (left.strip().upper()[:1], color.strip().lower())
    return None


# ===== RELIEF 모드 =====
def run_relief():
    """모드 전환 후: 'C,red' / 'D|blue' 수신 시 해당 링에서 relief 1사이클 실행"""
    global stop_flag
    print("RELIEF 모드 시작")
    while not stop_flag:
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors='ignore').strip()
            parsed = _parse_relief_cmd(line)
            if not parsed:
                continue
            strip_name, color_name = parsed
            if strip_name not in strips:
                continue
            color = COLOR_MAP.get(color_name)
            if not color:
                print(f"[RELIEF] 지원하지 않는 색상: {color_name}")
                continue
            print(f"[RELIEF] strip={strip_name}, color={color_name}")
            ok = relief_pattern(strips[strip_name], len(strips[strip_name]), color)
            if not ok:
                break
        time.sleep(0.005)
    print("RELIEF 모드 종료")

# ===== 에너지 함수 =====
def run_energy():
    """UART로 받은 C/D LED 제어"""
    print("ENERGY 모드 시작")
    while not stop_flag:
        if ser.in_waiting > 0:
            line = ser.readline().decode(errors="ignore").strip()
            if "," in line:
                try:
                    parts = line.split(",")
                    if len(parts) == 4:
                        strip_name, r, g, b = parts
                        if strip_name in strips:
                            color = (int(r), int(g), int(b))
                            fill_strip_color(strips[strip_name], color)  # ✅ 수정됨
                except Exception as e:
                    print(f"[UART ERROR] {e}, line={line}")
        time.sleep(0.01)
    clear_all()
    print("ENERGY 모드 종료")




# ===== 모드 관리 (수정됨) =====
def start_mode(mode):
    global current_mode, mode_thread, stop_flag
    stop_mode()
    stop_flag = False
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()

    except Exception:
        pass
    
    if mode == "love":
        mode_thread = threading.Thread(target=run_love, daemon=True)
    elif mode == "focus":
        mode_thread = threading.Thread(target=run_focus, daemon=True)
    elif mode == "healing":
        mode_thread = threading.Thread(target=run_healing, daemon=True)
    elif mode == "relief":
        mode_thread = threading.Thread(target=run_relief, daemon=True)
    elif mode == "energy":
        mode_thread = threading.Thread(target=run_energy, daemon=True)
    else:
        print(f"알 수 없는 모드: {mode}")
        return
       
    current_mode = mode
    mode_thread.start()

def stop_mode():
    global stop_flag, mode_thread, current_mode
    if mode_thread and mode_thread.is_alive():
        stop_flag = True
        mode_thread.join()
    clear_all()
    current_mode = None
    mode_thread = None

if __name__ == "__main__":
    try:
        print("UART 명령 대기중... (love/focus/healing/relief)", flush=True)
        while True:
            # ★ 모드가 없을 때만 모드 전환 라인을 읽는다 (경쟁 방지)
            if current_mode is None and ser.in_waiting > 0:
                line = ser.readline().decode(errors='ignore').strip().lower()

                # 'mode:healing' 같은 형태도 허용하려면:
                prefix, sep, rest = line.partition(':')
                if sep == ':':
                    cmd = rest.strip()
                else:
                    cmd = line

                if cmd in ["love", "focus", "healing", "relief", "energy"]:
                    print(f"모드 전환 요청: {cmd}", flush=True)
                    start_mode(cmd)
                else:
                    print(f"[MAIN] 알 수 없는 명령: {line}", flush=True)

            time.sleep(0.1)
    except KeyboardInterrupt:
        stop_mode()
        ser.close()
        print("LED OFF, UART 종료", flush=True)
