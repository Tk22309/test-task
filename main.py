import sys
from pathlib import Path
from openpyxl import Workbook
from skore_work_manager import Give_score, write_json_to_xlsx

from transcribe_calls import (
    process_file,    
    CALLS_DIR,
    SUPPORTED_EXTS,
    ensure_ffmpeg,   
)



OUTPUT_XLSX = Path("skore_manager.xlsx")


def ensure_calls_dir():
    if not CALLS_DIR.exists():
        raise FileNotFoundError(f"Папку з викликами не знайдено: {CALLS_DIR.resolve()}")


def ensure_xlsx(path: Path):
    """Створює порожню книгу, якщо її ще немає."""
    if not path.exists():
        Workbook().save(path)


def transcribe_all():
    """Транскрибувати всі .mp3/.wav у calls -> створити .txt поруч (якщо ще нема)."""
    audio_files = [p for p in sorted(CALLS_DIR.iterdir())
                   if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    if not audio_files:
        print("[i] У 'calls' немає .mp3/.wav")
        return
    for p in audio_files:
        process_file(p)


def score_all_texts(xlsx_path: Path):
    """Для кожного .txt у calls: GPT-оцінка -> запис у Excel."""
    for file in sorted(CALLS_DIR.iterdir()):
        if not (file.is_file() and file.suffix.lower() == ".txt"):
            continue

        text = file.read_text(encoding="utf-8")

        # 1) оцінка роботи менеджера
        try:
            clean_json = Give_score(text)
        except Exception as e:
            print(f"[!] GPT помилка для {file.name}: {e}")
            continue

        # 2) Запис у Excel
        try:
            write_json_to_xlsx(
                xlsx_path=str(xlsx_path),
                clean_json_text=clean_json,
                sheet_name=None,
                header_row=2,
                full_call_text=text,
            )
        except Exception as e:
            print(f"[!] Excel помилка для {file.name}: {e}")


def main():
    # Перевірки
    ensure_ffmpeg()       
    ensure_calls_dir()
    ensure_xlsx(OUTPUT_XLSX)

    # 1) Транскрипція аудіо у .txt
    print("[i] Транскрипція аудіофайлів…")
    transcribe_all()

    # 2) Оцінювання всіх .txt і запис у Excel
    print("[i] Оцінювання .txt і запис у Excel…")
    score_all_texts(OUTPUT_XLSX)

    print("[✓] Готово.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[!] Помилка: {e}")
        sys.exit(1)
