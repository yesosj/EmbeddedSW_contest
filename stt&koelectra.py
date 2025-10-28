# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import torch
import time
import os
import io
from google.cloud import speech
from transformers import AutoTokenizer, AutoModelForSequenceClassification

wav_path = "recorded.wav"

# 3. Google 인증 키 환경변수
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/capstone/project/capstone-458405-139f3ac27ecd.json"
client = speech.SpeechClient()

# 4. 녹음된 wav 파일 읽기
with io.open(wav_path, "rb") as f:
    content = f.read()

audio = speech.RecognitionAudio(content=content)

# 5. STT 요청 설정
config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=16000,
    language_code="ko-KR"
)

# 6. 요청 및 결과 저장
response = client.recognize(config=config, audio=audio)

with open("/home/capstone/결과.txt", "a", encoding="utf-8") as f:
    for result in response.results:
        transcript = result.alternatives[0].transcript
        print("인식 결과:", transcript)
        f.write(transcript + "\n")

       
model_path = "/home/capstone/Downloads/go_to_raspberrypi2"  

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)

model.eval()

input_path = "/home/capstone/결과.txt"

if not os.path.exists(input_path):
    print(f"Input file does not exist: {input_path}")
    exit(1)

with open(input_path, "r" , encoding="utf-8") as f:
    lines = f.readlines()
    if not lines:
        print("Input file is empty")
        exit(1)
    last_line = lines[-1].strip()

if not last_line:
    print("Last line is empty")
    exit(1)


def predict_emotion(text):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=128
    )
   
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probabilities = torch.softmax(logits, dim=1)

    predicted_label = torch.argmax(probabilities, dim=1).item()
    predicted_prob = probabilities[0][predicted_label].item()

    return predicted_label, predicted_prob

# 한글 텍스트 입력
print(last_line)
label, confidence = predict_emotion(last_line)

   
emotion_labels = {
    0: "happy",
    1: "sad",
    2: "angry"
}

print(f"{emotion_labels.get(label)}")

with open("/home/capstone/project/emotion_label.txt","w") as log_file:
    log_file.write(f"{label}")
with open("/home/capstone/project/current_feeling.txt","w") as log_file:
    log_file.write(f"{emotion_labels.get(label)}")
