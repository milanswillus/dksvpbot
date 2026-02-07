import logging
import asyncio
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Import modules
from config import USER_VPLAN, PASSWORD_VPLAN
import storage
from state_manager import load_state, save_state, calculate_hash
from meme_handler import create_meme, get_next_template_id

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

Wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    user = update.effective_user.first_name
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Hallo {user}! Ich helfe dir, deine Klassen zu verwalten.\n\n"
             "Nutze /betreten <Klasse>, um einer Klasse beizutreten.\n"
             "Nutze /verlassen <Klasse>, um eine Klasse zu verlassen.\n"
             "Nutze /meineklassen, um deine Liste zu sehen."
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bitte gib einen Klassennamen an. Beispiel: /hinzufuegen 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.add_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Klasse hinzugefügt: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Du bist bereits in der Klasse: {class_name}"
        )

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bitte gib einen Klassennamen an. Beispiel: /entfernen 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.remove_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Klasse entfernt: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Du bist nicht in der Klasse: {class_name}"
        )

async def classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists the user's classes."""
    chat_id = update.effective_chat.id
    user_classes = storage.get_student_classes(chat_id)
    
    if user_classes:
        classes_str = "\n".join(f"- {c}" for c in user_classes)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Deine Klassen:\n{classes_str}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Du hast noch keine Klassen. Nutze /hinzufuegen, um eine hinzuzufügen."
        )

async def check_updates(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job to check for updates on the school website."""
    logging.info("Checking for updates...")
    state = load_state()
    state_changed = False
    
    # Load current user subscriptions dynamically
    user_Klassen = storage.load_data()

    for Wochentag in Wochentage:
        url = f"https://dksdd.de/vtp/{Wochentag}.html"
        
        try:
            # Note: requests is synchronous. In a high-perf async app we might use aiohttp,
            # but for this low-frequency job it's acceptable (or run in executor).
            response = requests.get(url, auth=(USER_VPLAN, PASSWORD_VPLAN))
            response.raise_for_status()
        except Exception as e:
            logging.error(f"Fehler beim Abruf von {Wochentag}: {e}")
            continue

        html_content = response.content
        current_hash = calculate_hash(html_content)
        
        if Wochentag not in state:
            state[Wochentag] = {"html_hash": "", "sent_messages": {}}

        if state[Wochentag]["html_hash"] == current_hash:
            continue
            
        logging.info(f"Änderung erkannt für {Wochentag}! Analysiere...")
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        datum_span = soup.find('span', class_='vpfuerdatum')
        if not datum_span:
            continue
            
        Datum = datum_span.text.strip()
        
        last_date = state[Wochentag].get("last_date", "")
        if last_date != Datum:
            logging.info(f"Neues Datum für {Wochentag}: {Datum}. Resette State.")
            state[Wochentag]["sent_messages"] = {}
            state[Wochentag]["last_date"] = Datum
            state_changed = True

        for chat_id, Klassen in user_Klassen.items():
            # Ensure chat_id is int for sending messages, though dict keys are strings
            try:
                chat_id_int = int(chat_id)
            except ValueError:
                continue

            for Klasse in Klassen:
                klasse_elements = soup.find_all("td", string=Klasse)

                if not klasse_elements:
                    continue

                for idx, klasse_element in enumerate(klasse_elements):
                    tr_klasse = klasse_element.find_parent("tr")
                    zellen_inhalte = [td.text.strip() for td in tr_klasse.find_all("td")]

                    if len(zellen_inhalte) < 6:
                         continue

                    stunde = zellen_inhalte[1]
                    fach = zellen_inhalte[2]
                    lehrer = zellen_inhalte[3]
                    raum = zellen_inhalte[4]
                    info = zellen_inhalte[5]

                    caption_text = (
                        f"📅 {Wochentag} ({Datum})\n"
                        f"Klasse: {Klasse}\n"
                        f"Stunde: {stunde} | Fach: {fach}\n"
                        f"Lehrer: {lehrer} | Raum: {raum}\n"
                        f"Info: {info}"
                    )
                    
                    msg_identifier = f"{chat_id}_{Klasse}_{idx}_{caption_text}"
                    msg_hash = calculate_hash(msg_identifier)
                    
                    if msg_hash in state[Wochentag]["sent_messages"]:
                        continue
                    
                    # Decide: Meme or Text
                    if info and (("fällt aus" in info.lower()) or "--" in fach):
                        subject_mapping = {
                            "PH": "Physik", "MA": "Mathe", "KU": "Kunst", "EN": "Englisch",
                            "FR": "Französisch", "MU": "Musik", "SPO": "Sport", "ETH": "Ethik",
                            "DE": "Deutsch", "GE": "Geschichte", "GEO": "Geografie",
                            "CH": "Chemie", "INF": "Informatik", "GRW": "GRW"
                        }
                        raw_subject = info.split()[0]
                        match_subj = re.search(r'([a-zA-Z]+)', raw_subject)
                        if match_subj:
                            abbr = match_subj.group(1).upper()
                            subject_name = subject_mapping.get(abbr, re.sub(r'\d+$', '', raw_subject))
                        else:
                            subject_name = raw_subject

                        meme_text = f"am {Wochentag} kein {subject_name}"
                        logging.info(f"Generiere Meme für: {meme_text}")
                        
                        meme_path = create_meme(get_next_template_id(), meme_text)
                        
                        if meme_path:
                            try:
                                with open(meme_path, 'rb') as video_file:
                                    await context.bot.send_video(
                                        chat_id=chat_id_int,
                                        video=video_file,
                                        caption=caption_text
                                    )
                                os.remove(meme_path)
                            except Exception as e:
                                logging.error(f"Failed to send video: {e}")
                                # Fallback to text
                                await context.bot.send_message(chat_id=chat_id_int, text=caption_text)
                        else:
                            await context.bot.send_message(chat_id=chat_id_int, text=caption_text)
                    else:
                        await context.bot.send_message(chat_id=chat_id_int, text=caption_text)
                    
                    state[Wochentag]["sent_messages"][msg_hash] = True
                    state_changed = True

        if state[Wochentag]["html_hash"] != current_hash:
            state[Wochentag]["html_hash"] = current_hash
            state_changed = True

    if state_changed:
        save_state(state)

async def manual_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers a manual update check."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Prüfe auf Updates..."
    )
    await check_updates(context)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Update-Check abgeschlossen."
    )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.startswith("123456"):
        print("Error: TELEGRAM_BOT_TOKEN is not set properly.")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('betreten', add))
    application.add_handler(CommandHandler('verlassen', remove))
    application.add_handler(CommandHandler('meineklassen', classes))
    application.add_handler(CommandHandler('update', manual_update))
    
    # Scraping Job
    # Check every 60 minutes (3600 seconds)
    job_queue = application.job_queue
    job_queue.run_repeating(check_updates, interval=3600, first=10)
    
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()