import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from openai import OpenAI



API_KEY = "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"

CALLS_DIR = Path("calls")
SUPPORTED_EXTS = {".mp3", ".wav"} 
CHUNK_SECONDS = 60                  # довжина чанку в сек (дуже гарне значення)
SAMPLE_RATE = 44100                 # Whisper любить 44.1 кГц
LANG = "uk"
MODEL = "whisper-1"
CLEANUP_MODEL = "gpt-4o-mini"


client = OpenAI(api_key=API_KEY)


def ensure_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception as e:
        raise RuntimeError("ffmpeg не знайдено у PATH. Встанови ffmpeg або додай у PATH.") from e


def norm_and_chunk(input_path: Path, out_dir: Path, chunk_seconds: int = CHUNK_SECONDS) -> list[Path]:
    #Нормалізуємо аудіо + додаємо 200 мс затримки на початку,
    #конвертуємо в моно WAV 44.1кГц 
    
    out_dir.mkdir(parents=True, exist_ok=True)
    norm_wav = out_dir / "normalized.wav"


    ff_norm = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", "loudnorm=I=-20:TP=-1.5:LRA=11,highpass=f=150,lowpass=f=8000,adelay=200|200",
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        str(norm_wav)
    ]
    subprocess.run(ff_norm, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ріжемо нормалізований WAV на шматки
    # segment_time = довжина фрагмента (сек)
    # chunk_%03d.wav — імена шматків 000, 001, 002...
    chunk_pattern = out_dir / "chunk_%03d.wav"
    ff_seg = [
        "ffmpeg", "-y",
        "-i", str(norm_wav),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1",
        str(chunk_pattern)
    ]
    subprocess.run(ff_seg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # перелік готових шматків
    chunks = sorted(out_dir.glob("chunk_*.wav"))
    return chunks


def transcribe_chunk(chunk_path: Path) -> str:
    #Надсилаємо шматок у Whisper-1 і повертаємо чистий текст
    with open(chunk_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model=MODEL,
            file=f,
            response_format="text",
            temperature=0.0,
            language=LANG,
        )
    return (resp or "").strip()


def gpt_cleanup(full_text: str) -> str:
    #Згладжуємо стики фрагментів, повертаємо пунктуацію, не вигадуємо фактів.
    #Просимо уникати дублювань на межах (типова проблема при чанкінгу).
    system = (
        "Ти — коректор транскриптів українською. "
        "Згладь стики між фрагментами (прибери дублювання слів на межах), "
        "віднови пунктуацію, виправ описки. "
        "Не вигадуй нових фактів і змісту."
    )
    user = (
        "Ось суцільний транскрипт, зібраний із кількох фрагментів. "
        "Будь ласка, прибери можливі дублювання на стиках і поверни відкоригований текст:\n\n"
        f"{full_text}"
    )
    resp = client.chat.completions.create(
        model=CLEANUP_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def process_file(audio_path: Path) -> None:

    print(f"[i] Обробка: {audio_path.name}")
    out_txt = audio_path.with_suffix(".txt")
    if out_txt.exists():
        print(f"[→] Пропуск (TXT вже існує): {out_txt.name}")
        return

    tmpdir = Path(tempfile.mkdtemp(prefix=f"chunks_{audio_path.stem}_"))
    try:
    
        chunks = norm_and_chunk(audio_path, tmpdir, CHUNK_SECONDS)
        if not chunks:
            print(f"[!] Не вдалось нарізати фрагменти: {audio_path.name}")
            return

        partials: list[str] = []
        for i, ch in enumerate(chunks, 1):
            txt = transcribe_chunk(ch)
            partials.append(txt)
            print(f"    [{i}/{len(chunks)}] {len(txt)} симв.")

        raw_full = "\n".join(s for s in partials if s)

        
        final_text = gpt_cleanup(raw_full) if raw_full.strip() else ""
        out_txt.write_text((final_text or raw_full).strip() + "\n", encoding="utf-8")


    except Exception as e:
        print(f"[!] Помилка на '{audio_path.name}': {e}")
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def main():
    ensure_ffmpeg()

    if not CALLS_DIR.exists():
        print(f"[!] Папка не знайдена: {CALLS_DIR.resolve()}")
        sys.exit(1)

    # обробляємо лише mp3/wav
    audio_files = [p for p in sorted(CALLS_DIR.iterdir()) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not audio_files:
        print("[i] У 'calls' немає .mp3/.wav")
        return

    for p in audio_files:
        process_file(p)

    print("Усі доступні файли оброблено.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:

        sys.exit(0)
