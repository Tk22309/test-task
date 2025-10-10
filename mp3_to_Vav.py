import os
import subprocess
import wave
import json
from vosk import Model, KaldiRecognizer


CALLS_DIR = "calls"                      
MODEL_PATH = "vosk-model-uk-v3"  
LOG_PATH = os.path.join(CALLS_DIR, "logs.txt")

# Потрыбно переконайся, що ffmpeg встановлено і додано в PATH.
# Якщо ні, завантаж: https://ffmpeg.org/ (або winget: winget install Gyan.FFmpeg)

def ensure_logs_header():
    if not os.path.exists(CALLS_DIR):
        os.makedirs(CALLS_DIR, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("=== ЛОГИ КОНВЕРТАЦІЇ ТА ТРАНСКРИПЦІЇ ===\n")

def log_line(text):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")

def ffmpeg_mp3_to_wav(mp3_path, wav_path):

    #Конвертація через ffmpeg у WAV (моно, 16 кГц, PCM 16-bit little endian).
    cmd = [
        "ffmpeg", "-y",
        "-i", mp3_path,
        "-ac", "1",
        "-ar", "16000",
        "-sample_fmt", "s16",
        wav_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg не знайдено. Встанови ffmpeg і додай у PATH.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Помилка ffmpeg при конвертації {os.path.basename(mp3_path)}: {e}")

def transcribe_wav_vosk(wav_path, model):
    
    #Транскрибує WAV (16kHz, mono, s16le) за допомогою Vosk.
    #Повертає str
    
    with wave.open(wav_path, "rb") as wf:
        if wf.getnchannels() != 1 or wf.getframerate() != 16000 or wf.getsampwidth() != 2:
            raise RuntimeError(f"WAV має бути mono/16kHz/16-bit: {os.path.basename(wav_path)}")

        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        result_texts = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                res = json.loads(rec.Result())
                result_texts.append(res.get("text", ""))

        final_res = json.loads(rec.FinalResult())
        result_texts.append(final_res.get("text", ""))

    # чистка від зайвоъ табуляції
    text = " ".join(t.strip() for t in result_texts if t.strip())
    return text.strip()

def process_calls_folder():
    ensure_logs_header()

    # Завантажуємо модель Vosk один раз
    if not os.path.isdir(MODEL_PATH):
        log_line(f"Модель не знайдено")
        print(f"Модель не знайдено")
        return
    print(" Завантаження моделі Vosk")
    model = Model(MODEL_PATH)
    print("Модель Vosk завантажено.")

    for filename in os.listdir(CALLS_DIR):
        file_path = os.path.join(CALLS_DIR, filename)

        if os.path.isdir(file_path) or filename == os.path.basename(LOG_PATH):
            continue

        # додав перевірку тільки для того щоб якщо випадково попався інший файл то програма не зламалась
        if not filename.lower().endswith(".mp3"):
            log_line(f"Файл {filename} не відповідає нашому формату")
            continue

        base = os.path.splitext(filename)[0]
        wav_path = os.path.join(CALLS_DIR, base + ".wav")
        txt_path = os.path.join(CALLS_DIR, base + ".txt")

        # MP3 → WAV
        try:
            ffmpeg_mp3_to_wav(file_path, wav_path)
            print(f"Конвертовано: {filename} → {os.path.basename(wav_path)}")
        except Exception as e:
            log_line(f"Помилка конвертації {filename}: {e}")
            continue

        # Транскрипція WAV → TXT (Vosk)
        try:
            text = transcribe_wav_vosk(wav_path, model)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            print(f"Транскрибовано: {os.path.basename(txt_path)}")
        except Exception as e:
            log_line(f"Помилка транскрипції {os.path.basename(wav_path)}: {e}")

    print("\nГотово")

if __name__ == "__main__":
    process_calls_folder()

