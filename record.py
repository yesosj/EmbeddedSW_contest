import os
import subprocess
import io
import RPi.GPIO as GPIO
from google.cloud import speech

# 1. 녹음할 파일 이름
wav_path = "recorded.wav"


def get_mic_device():
    result = subprocess.run("arecord -l" , shell = True , capture_output= True , text= True)
    output = result.stdout

    lines = output.splitlines()
    for line in lines:
        if 'card' in line:
            card_number = line.split()[1]
            card_number = card_number.split(':')[0]
            return f"plughw:{card_number},0"

    return None
# 2. 녹음 (arecord 사용: 16bit, 16kHz, Mono, 8초)
# print(get_mic_device())

print("8초간 녹음 시작...")
subprocess.run([
    "arecord",
    "-D", get_mic_device(),      # USB 마이크에 맞게 수정
    "-f", "S16_LE",          # 16-bit
    "-r", "16000",           # 샘플레이트
    "-c", "1",               # 모노
    "-d", "8",               # 8초간 녹음
    wav_path
])

print("녹음 완료, STT 요청 중...")
