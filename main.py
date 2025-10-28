import RPi.GPIO as GPIO
from music_select import select_random_music_path
from play_neopixel import play_neopixel_effect
from pathlib import Path
import signal
import board
import neopixel
import math

import subprocess
import time
import threading


# Pin definitions
START_PIN = 17
STOP_PIN = 16
LED_RED_PIN = 21
LED_YELLOW_PIN = 26
LED_GREEN_PIN = 20
LED_emotion_happy = 27
LED_emotion_sad = 22
LED_emotion_angry = 12

feeling_buttons = {
    5: "healing",
    6: "relief",
    23: "energy",
    24: "focus",
    25: "love"
}

stop_neopixel = threading.Event()
neo_thread = None

# GPIO setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

GPIO.setup(LED_RED_PIN,GPIO.OUT)
GPIO.output(LED_RED_PIN, GPIO.LOW)
GPIO.setup(LED_GREEN_PIN,GPIO.OUT)
GPIO.output(LED_GREEN_PIN, GPIO.LOW)
GPIO.setup(LED_YELLOW_PIN,GPIO.OUT)
GPIO.output(LED_YELLOW_PIN, GPIO.LOW)
GPIO.setup(LED_emotion_happy,GPIO.OUT)
GPIO.output(LED_emotion_happy, GPIO.LOW)
GPIO.setup(LED_emotion_sad,GPIO.OUT)
GPIO.output(LED_emotion_sad, GPIO.LOW)
GPIO.setup(LED_emotion_angry,GPIO.OUT)
GPIO.output(LED_emotion_angry, GPIO.LOW)
GPIO.setup(START_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(STOP_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
for pin in feeling_buttons:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Globals
music_process = None
process_lock = threading.Lock()
selected_feeling = None
feeling_selected = threading.Event()
# global label

last_press_time = 0
click_count = 0
paused = False
current_music_path = None
paused_position =0
music_start_time =0

print("Ready. Press START button first, then select a feeling.")

import subprocess

class MusicController(threading.Thread):
    """
    - 원격모드 없이 4인자 Popen 사용
    - pause 시 경과시간 저장 → resume 시 -k <frame_offset> 로 이어재생
    """
    def __init__(self, prefer_keyword="USB"):
        super().__init__(daemon=True)
        self.prefer_keyword = prefer_keyword
        self.device = None
        self.proc = None
        self.lock = threading.Lock()
        self.stop_evt = threading.Event()

        self.current_path = None
        self.paused = False
        self.started_at = 0.0         # 재생 시작(또는 마지막 resume) 시각
        self.paused_pos_sec = 0.0     # 일시정지된 시점(초)

        # MP3 한 프레임 길이 = 1152 / sample_rate
        # 44.1kHz 기준 FPS ≈ 44100/1152 ≈ 38.28125
        self.FRAMES_PER_SEC = 38.28125

    def run(self):
        self.device = get_audio_device()
        while not self.stop_evt.is_set():
            time.sleep(0.05)
        self._stop_proc()

    # ---------- 외부 API ----------
    def play(self, path: str):
        """새 곡 재생(처음부터)"""
        p = Path(path).expanduser().resolve()
        if not p.exists():
            print(f"[Music] 파일 없음: {p}"); return
        with self.lock:
            self._stop_proc()
            self._spawn_normal(p.as_posix())
            self.current_path = p.as_posix()
            self.started_at = time.time()
            self.paused_pos_sec = 0.0
            self.paused = False

    def pause_toggle(self):
        """재생 중 → pause / pause 상태 → 같은 지점부터 resume"""
        with self.lock:
            if self.proc and self.proc.poll() is None and not self.paused:
                # ▶️ playing → ⏸ pause: 경과 시간 저장 후 종료
                self.paused_pos_sec = time.time() - self.started_at
                self._stop_proc()
                self.paused = True
            elif self.paused and self.current_path:
                # ⏸ paused → ▶️ resume: -k 오프셋으로 재시작
                frame_offset = int(self.paused_pos_sec * self.FRAMES_PER_SEC)
                self._spawn_with_offset(self.current_path, frame_offset)
                self.started_at = time.time() - self.paused_pos_sec
                self.paused = False
            else:
                # 아무것도 안 재생 중이고 마지막 곡이 있으면 처음부터 틀기(옵션)
                if self.current_path and not self.proc:
                    self._spawn_normal(self.current_path)
                    self.started_at = time.time()
                    self.paused = False
                    self.paused_pos_sec = 0.0

    def stop(self):
        with self.lock:
            self._stop_proc()
            self.paused = False
            self.paused_pos_sec = 0.0

    def shutdown(self):
        self.stop_evt.set()

    # ---------- 내부 유틸 ----------
    def _spawn_normal(self, abs_path: str):
        self.proc = subprocess.Popen(
            ["mpg123", "-a", self.device, abs_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, text=False
        )

    def _spawn_with_offset(self, abs_path: str, frame_offset: int):
        # 이어재생: -k <frame_offset> 로 건너뛰고 시작
        self.proc = subprocess.Popen(
            ["mpg123", "-k", str(frame_offset), "-a", self.device, abs_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, text=False
        )

    def _stop_proc(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
        self.proc = None


def get_audio_device(prefer="USB"):
    result = subprocess.run("aplay -l", shell=True, capture_output=True, text=True)
    output = result.stdout

    card_number = None

    for line in output.splitlines():
        if "card" in line and "device" in line:
            # 예: card 3: UACDemoV10 [UACDemoV1.0], device 0: USB Audio
            if prefer in line:
                parts = line.split()
                card = parts[1].rstrip(':')
                device = parts[5].rstrip(':')
                return f"hw:{card},{device}"
    print(card_number)
    # fallback - 첫 번째 장치 사용
    for line in output.splitlines():
        if "card" in line and "device" in line:
            parts = line.split()
            card = parts[1].rstrip(':')
            device = parts[5].rstrip(':')
            return f"hw:{card},{device}"

    return None

# Toggle / random change logic on STOP_PIN
def handle_stop_button(channel):
    print("Hello?")
    global last_press_time, click_count, music_process, paused, current_music_path

    now = time.time()
    if now - last_press_time <= 1:
        click_count += 1
    else:
        click_count = 1
    last_press_time = now

    def single_click_action():
        global paused, click_count, music_process, current_music_path, paused_position, music_start_time
        time.sleep(1)
       
        if click_count == 1:
            print("음악 일시 정지")
            music_ctrl.pause_toggle()
        elif click_count == 2:
            with process_lock:
                print("🔁 더블 클릭 감지됨 - 새로운 랜덤 음악 재생")
                new_path = select_random_music_path()
                if new_path:
                    music_ctrl.play(new_path)
                else:
                    print("❌ 랜덤 음악 선택 실패")
        click_count = 0

    threading.Thread(target=single_click_action).start()

# Wait for feeling button press
def wait_for_feeling():
    global selected_feeling
    print("Please press a feeling button...")
    while True:
        for pin, feeling in feeling_buttons.items():
            if GPIO.input(pin) == GPIO.HIGH:
                selected_feeling = feeling
                with open("/home/capstone/project/want_feeling.txt", "w") as f:
                    f.write(f"{feeling}\n")
                print(f"Feeling selected: {feeling}")
                feeling_selected.set()
                return
        time.sleep(0.1)

def read_label_from_file():
    try:
        with open("/home/capstone/project/emotion_label.txt" , "r") as f:
            label = int(f.read().strip())
        return label
    except FileNotFoundError:
        print("Emotion label file not found!")
        return None

# ---------------- 감정 읽기 ----------------
def read_emotion(file_path):
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
            return lines[-1].strip() if lines else None
    except FileNotFoundError:
        return None

# Main emotion/music sequence
def run_emotion_music_sequence():
    global music_process, current_music_path, paused, music_start_time, paused_position
    if music_process:
        music_process.terminate()
        music_process = None
    with process_lock:
        print("START button pressed. Running STT sequence...")
        GPIO.output(LED_GREEN_PIN, GPIO.HIGH)

        result1 = subprocess.run(["python", "/home/capstone/project/record.py"])
        if result1.returncode != 0:
            print("record.py failed. Aborting.")
            return
        GPIO.output(LED_GREEN_PIN, GPIO.LOW)

       

        GPIO.output(LED_RED_PIN, GPIO.HIGH)

        result2 = subprocess.run(["python", "/home/capstone/project/stt&koelectra_small.py"])
        if result2.returncode != 0:
            print("stt&koelectra_small.py failed. Aborting.")
            return
        GPIO.output(LED_RED_PIN, GPIO.LOW)
        label = read_label_from_file()
        if label == 0:
            GPIO.output(LED_emotion_happy , GPIO.HIGH)
            time.sleep(2)
            GPIO.output(LED_emotion_happy, GPIO.LOW)
        elif label == 1:
            GPIO.output(LED_emotion_sad , GPIO.HIGH)
            time.sleep(2)
            GPIO.output(LED_emotion_sad, GPIO.LOW)
        elif label == 2:
            GPIO.output(LED_emotion_angry , GPIO.HIGH)
            time.sleep(2)
            GPIO.output(LED_emotion_angry, GPIO.LOW)
               
        GPIO.output(LED_YELLOW_PIN , GPIO.HIGH)
        wait_for_feeling()
        feeling_selected.wait()

        GPIO.output(LED_YELLOW_PIN , GPIO.LOW)
        if music_process and music_process.poll() is None:
            print("Music already playing.")
        else:
            print("Starting music for selected feeling!")
            music_path = select_random_music_path()
            if music_path:
                # # 감정 파일 경로
                want_file = "/home/capstone/project/want_feeling.txt"
                current_file = "/home/capstone/project/current_feeling.txt"
                current_feeling = read_emotion(current_file)
                want_feeling = read_emotion(want_file)
                print(current_feeling)
                current_music_path = music_path
                print(get_audio_device())
                music_process =music_ctrl.play(music_path)
                music_start_time = time.time()
                paused_position = 0
                paused = False
                threading.Thread(target=play_neopixel_effect, args =(current_feeling , want_feeling), daemon = True).start()
            else:
                print("Music selection failed.")

try:
    GPIO.remove_event_detect(START_PIN)
except RuntimeError:
    pass

music_ctrl = MusicController(prefer_keyword= "USB")
music_ctrl.start()

# Register GPIO events
GPIO.add_event_detect(START_PIN, GPIO.RISING, callback=lambda ch: threading.Thread(target=run_emotion_music_sequence).start(), bouncetime=500)
GPIO.add_event_detect(STOP_PIN, GPIO.RISING, callback=handle_stop_button, bouncetime=300)

# Main loop
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Interrupted")
finally:
    if music_process and music_process.poll() is None:
        music_process.terminate()
        music_process.wait()

    GPIO.cleanup()
