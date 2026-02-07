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
        text=f"Hallo {user}! I help you manage your school classes.\n\n"
             "Use /add <class> to join a class.\n"
             "Use /remove <class> to leave a class.\n"
             "Use /classes to see your list.\n"
             "Use /reset to refresh your data."
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please specify a class. Example: /add 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.add_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Class added: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"You are already in class: {class_name}"
        )

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please specify a class. Example: /remove 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.remove_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Class removed: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"You are not in class: {class_name}"
        )

async def classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists the user's classes."""
    chat_id = update.effective_chat.id
    user_classes = storage.get_student_classes(chat_id)
    
    if user_classes:
        classes_str = "\n".join(f"- {c}" for c in user_classes)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Your classes:\n{classes_str}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="You have no classes yet. Use /add to add one."
        )

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the user's data version to force a refresh of messages."""
    chat_id = update.effective_chat.id
    new_version = storage.increment_reset_version(chat_id)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Data reset (Version {new_version}). You will receive all current updates again on the next check."
    )

async def check_updates(context: ContextTypes.DEFAULT_TYPE):
    """Periodic job to check for updates on the school website."""
    logging.info("Checking for updates...")
    state = load_state()
    state_changed = False
    
    # Load current user subscriptions dynamically
    user_data_raw = storage.load_data()

    for Wochentag in Wochentage:
        url = f"https://dksdd.de/vtp/{Wochentag}.html"
        
        try:
            response = requests.get(url, auth=(USER_VPLAN, PASSWORD_VPLAN))
            response.raise_for_status()
        except Exception as e:
            logging.error(f"Fehler beim Abruf von {Wochentag}: {e}")
            continue

        html_content = response.content
        current_hash = calculate_hash(html_content)
        
        if Wochentag not in state:
            state[Wochentag] = {"html_hash": "", "sent_messages": {}}

        if state[Wochentag]["html_hash"] == current_hash and not any(isinstance(v, dict) and v.get('version', 0) > 0 for v in user_data_raw.values()):
             pass

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

        for chat_id, entry in user_data_raw.items():
            if isinstance(entry, list):
                Klassen = entry
                version = 0
            else:
                Klassen = entry.get("classes", [])
                version = entry.get("version", 0)

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
                    
                    msg_identifier = f"{chat_id}_{Klasse}_{idx}_{caption_text}_v{version}"
                    msg_hash = calculate_hash(msg_identifier)
                    
                    if msg_hash in state[Wochentag]["sent_messages"]:
                        continue
                    
                    # Decide: Meme or Text
                    if info and (("fällt aus" in info.lower()) or "--" in fach):
                        subject_mapping = {
                            "PH": "Physik", "MA": "Mathe", "KU": "Kunst", "EN": "Englisch",
                            "FR": "Französisch", "MU": "Musik", "SPO": "Sport", "ETH": "Ethik",
                            "DE": "Deutsch", "GE": "Geschichte", "GEO": "Geo",
                            "CH": "Chemie", "INF": "Info", "GRW": "GRW", "BIO": "Bio",
                            "FÖ": "Förderung"
                        }
                        
                        # Improved Subject Detection
                        detected_subject = None

                        # 1. Try to find a known subject in the 'Info' string specifically if it's a cancellation
                        if "fällt aus" in info.lower():
                            # Find all uppercase words of length 2-3 (e.g. BIO, MA, DE)
                            words = re.findall(r'\b[A-Z]{2,3}\b', info)
                            for word in words:
                                if word in subject_mapping:
                                    detected_subject = subject_mapping[word]
                                    break
                        
                        # 2. If not found in Info, use the 'Fach' column if it's valid (not ---)
                        if not detected_subject and fach and "--" not in fach:
                             match_subj = re.search(r'([a-zA-Z]+)', fach)
                             if match_subj:
                                 abbr = match_subj.group(1).upper()
                                 detected_subject = subject_mapping.get(abbr, fach)

                        # 3. Fallback: Parse first word of Info (for rows like "---" where info is "BIO fällt aus")
                        if not detected_subject:
                            raw_subject = info.split()[0]
                            match_subj = re.search(r'([a-zA-Z]+)', raw_subject)
                            if match_subj:
                                abbr = match_subj.group(1).upper()
                                detected_subject = subject_mapping.get(abbr, re.sub(r'\d+$', '', raw_subject))
                            else:
                                detected_subject = raw_subject

                        # Determine Meme Text
                        # Prioritize Cancellation if "fällt aus" is in info
                        if "fällt aus" in info.lower():
                             meme_text = f"am {Wochentag} kein {detected_subject}"
                        elif "verlegt" in info.lower() or "verschoben" in info.lower():
                             meme_text = f"Am {Wochentag} {detected_subject} verschoben"
                        else:
                             meme_text = f"am {Wochentag} kein {detected_subject}"
                        
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
        text="Checking for updates..."
    )
    await check_updates(context)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Check completed."
    )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.startswith("123456"):
        print("Error: TELEGRAM_BOT_TOKEN is not set properly.")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('add', add))
    application.add_handler(CommandHandler('remove', remove))
    application.add_handler(CommandHandler('classes', classes))
    application.add_handler(CommandHandler('update', manual_update))
    application.add_handler(CommandHandler('reset', reset_data))
    
    # Scraping Job
    job_queue = application.job_queue
    job_queue.run_repeating(check_updates, interval=3600, first=10)
    
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()