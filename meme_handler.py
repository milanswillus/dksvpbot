import os
import PIL.Image
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from config import TEMPLATE_DIR, OUTPUT_DIR, COUNTER_FILE

# --- MOVIEPY & PILLOW FIX ---
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

def get_next_template_id():
    """Liest den nächsten Template-Counter, inkrementiert ihn und speichert ihn ab."""
    current_id = 1
    
    # 1. Aktuellen Stand lesen
    if COUNTER_FILE.exists():
        try:
            with open(COUNTER_FILE, "r") as f:
                content = f.read().strip()
                if content.isdigit():
                    current_id = int(content)
        except Exception as e:
            print(f"Fehler beim Lesen des Counters: {e}")
            current_id = 1

    # 2. Prüfen ob Template existiert
    template_path = TEMPLATE_DIR / f"{current_id}.mp4"
    if not template_path.exists():
        print(f"ℹ️ Template {current_id} existiert nicht. Resette auf 1.")
        current_id = 1
        # Sicherheitshalber prüfen ob 1 existiert
        if not (TEMPLATE_DIR / "1.mp4").exists():
            print("❌ ACHTUNG: Template 1.mp4 fehlt auch! Das könnte Probleme geben.")

    # 3. Nächsten Wert berechnen und speichern
    next_id = current_id + 1
    try:
        with open(COUNTER_FILE, "w") as f:
            f.write(str(next_id))
    except Exception as e:
        print(f"Fehler beim Speichern des Counters: {e}")

    return current_id

def create_meme(video_id: int, text: str):
    """Erstellt ein Meme und gibt den Dateipfad zurück"""
    clean_text = "".join(c if c.isalnum() else "_" for c in text).strip("_")
    while "__" in clean_text: clean_text = clean_text.replace("__", "_")
    
    input_path = TEMPLATE_DIR / f"{video_id}.mp4"
    output_file = OUTPUT_DIR / f"meme_{video_id}_{clean_text}.mp4"

    if not input_path.exists():
        print(f"❌ Template fehlt: {input_path}")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        video = VideoFileClip(str(input_path))
        
        # Auf Quadrat zuschneiden
        min_dim = min(video.w, video.h)
        video = video.crop(width=min_dim, height=min_dim, x_center=video.w/2, y_center=video.h/2)

        upscale_factor = 2
        target_width = video.w * 0.9

        txt_clip = TextClip(
            text,
            fontsize=50,             
            color='white',
            font='DejaVu-Sans-Bold',
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(target_width * upscale_factor, None),
            align='Center'
        ).resize(1/upscale_factor).set_position('center').set_duration(video.duration)

        final_video = CompositeVideoClip([video, txt_clip])
        
        # Audio codec aac ist wichtig für Telegram
        final_video.write_videofile(
            str(output_file),
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=4,
            logger=None # Unterdrückt den Moviepy Output im Log
        )
        return output_file
        
    except Exception as e:
        print(f"Fehler beim Erstellen des Memes: {e}")
        return None
