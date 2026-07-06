import logging
import asyncio
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Import modules
from config import USER_VPLAN, PASSWORD_VPLAN, BASE_DIR
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

def matches_class(user_class: str, cell_value: str) -> bool:
    """Checks if a user's class subscription matches the cell value in the substitution plan."""
    user_class = user_class.strip().lower()
    cell_value = cell_value.strip().lower()
    
    if not user_class or not cell_value:
        return False
        
    if user_class == cell_value:
        return True
        
    # Split by comma first (e.g. "5a, 5b, 6d" -> ["5a", "5b", "6d"])
    parts = [p.strip() for p in cell_value.split(',')]
    for part in parts:
        if user_class == part:
            return True
            
        # Also split by slash (e.g. "JG11/ 11PH1" -> ["jg11", "11ph1"])
        subparts = [sp.strip() for sp in part.split('/')]
        if user_class in subparts:
            return True
            
        # Check if user is subscribed to a course starting with '11' or '12' 
        # and the notice is for the general year group 'jg11' / 'jg12'
        if user_class.startswith("11") and part == "jg11":
            return True
        if user_class.startswith("12") and part == "jg12":
            return True
            
    return False

def scrape_available_courses() -> list:
    """Fallback to dynamically scrape available courses from dksdd.de."""
    courses = set()
    for day in Wochentage:
        url = f"https://dksdd.de/vtp/{day}.html"
        try:
            r = requests.get(url, auth=(USER_VPLAN, PASSWORD_VPLAN))
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, 'html.parser')
                for tr in soup.find_all('tr'):
                    tds = tr.find_all('td')
                    if tds:
                        val = tds[0].text.strip()
                        if val.startswith("JG11/") or val.startswith("JG12/"):
                            parts = [p.strip() for p in val.split('/')]
                            if len(parts) > 1 and parts[1]:
                                courses.add(parts[1])
        except Exception as e:
            logging.error(f"Error scraping courses for {day}: {e}")
    return sorted(list(courses))

def get_available_courses() -> list:
    """Returns the list of available courses from faecher.txt, or falls back to cached state/scraping."""
    faecher_file = BASE_DIR / "faecher.txt"
    if faecher_file.exists():
        try:
            courses = []
            with open(faecher_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        courses.append(line)
            if courses:
                # Retain file order in a stable unique list
                seen = set()
                return [x for x in courses if not (x in seen or seen.add(x))]
        except Exception as e:
            logging.error(f"Error reading faecher.txt: {e}")

    state = load_state()
    courses = state.get("discovered_courses", [])
    if not courses:
        courses = scrape_available_courses()
    return courses

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and prompts for stufe (level)."""
    chat_id = update.effective_chat.id
    user = update.effective_user.first_name
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Hallo {user}! Ich helfe dir, deinen Vertretungsplan zu verwalten.\n\n"
             "Nutze /stufe um deine Klassenstufe zu ändern.\n"
             "Nutze /klassen um deine Klassen/Kurse anzuzeigen und zu verwalten.\n"
             "Nutze /zuruecksetzen um deine Benachrichtigungen zurückzusetzen.\n\n"
             "Bitte richte zuerst deine Stufe ein:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Mittelstufe (5-10)", callback_data="stufe_Mittelstufe"),
            InlineKeyboardButton("Oberstufe (Abitur)", callback_data="stufe_Oberstufe")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Welche Stufe besuchst du?",
        reply_markup=reply_markup
    )

async def stufe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts the user to change their level."""
    chat_id = update.effective_chat.id
    keyboard = [
        [
            InlineKeyboardButton("Mittelstufe (5-10)", callback_data="stufe_Mittelstufe"),
            InlineKeyboardButton("Oberstufe (Abitur)", callback_data="stufe_Oberstufe")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Welche Stufe besuchst du? (Achtung: Dies setzt deine bisherigen Klassen zurück!)",
        reply_markup=reply_markup
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bitte gib eine Klasse/einen Kurs an. Beispiel: /hinzufuegen 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.add_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Klasse/Kurs hinzugefügt: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Du bist bereits in Klasse/Kurs: {class_name}"
        )

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes a class."""
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Bitte gib eine Klasse/einen Kurs an. Beispiel: /entfernen 11b"
        )
        return

    class_name = " ".join(context.args)
    chat_id = update.effective_chat.id
    
    if storage.remove_class(chat_id, class_name):
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Klasse/Kurs entfernt: {class_name}"
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Du bist nicht in Klasse/Kurs: {class_name}"
        )

async def classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists the user's classes."""
    chat_id = update.effective_chat.id
    stufe = storage.get_student_stufe(chat_id)
    
    if not stufe:
        keyboard = [
            [
                InlineKeyboardButton("Mittelstufe (5-10)", callback_data="stufe_Mittelstufe"),
                InlineKeyboardButton("Oberstufe (Abitur)", callback_data="stufe_Oberstufe")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Bitte richte zuerst deine Stufe ein, um deine Klassen/Kurse zu verwalten:",
            reply_markup=reply_markup
        )
        return
        
    user_classes = storage.get_student_classes(chat_id)
    if stufe == "Mittelstufe":
        class_text = user_classes[0] if user_classes else "keine Klasse ausgewählt"
        text = f"Deine aktuelle Klasse: {class_text}"
        keyboard = [[InlineKeyboardButton("Klasse ändern / auswählen", callback_data="menu_mittel_grades")]]
    else: # Oberstufe
        if user_classes:
            classes_str = "\n".join(f"- {c}" for c in user_classes)
            text = f"Deine abonnierten Kurse:\n{classes_str}"
        else:
            text = "Du hast noch keine Kurse abonniert."
        keyboard = [
            [
                InlineKeyboardButton("Kurse verwalten (JG 11)", callback_data="menu_ober_jg11"),
                InlineKeyboardButton("Kurse verwalten (JG 12)", callback_data="menu_ober_jg12")
            ]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup
    )

async def show_mittel_grades(query):
    keyboard = [
        [
            InlineKeyboardButton("Klasse 5", callback_data="menu_mittel_letters:5"),
            InlineKeyboardButton("Klasse 6", callback_data="menu_mittel_letters:6")
        ],
        [
            InlineKeyboardButton("Klasse 7", callback_data="menu_mittel_letters:7"),
            InlineKeyboardButton("Klasse 8", callback_data="menu_mittel_letters:8")
        ],
        [
            InlineKeyboardButton("Klasse 9", callback_data="menu_mittel_letters:9"),
            InlineKeyboardButton("Klasse 10", callback_data="menu_mittel_letters:10")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="Wähle deine Klassenstufe (Mittelstufe):",
        reply_markup=reply_markup
    )

async def show_mittel_letters(query, grade):
    letters = ["a", "b", "c", "d", "e"]
    keyboard = []
    row = []
    for l in letters:
        class_name = f"{grade}{l}"
        row.append(InlineKeyboardButton(class_name, callback_data=f"set_class:{class_name}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("⬅️ Zurück", callback_data="menu_mittel_grades")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=f"Wähle deine Klasse für Stufe {grade}:",
        reply_markup=reply_markup
    )

async def show_ober_jg_selection(query):
    keyboard = [
        [
            InlineKeyboardButton("Jahrgang 11", callback_data="menu_ober_jg11"),
            InlineKeyboardButton("Jahrgang 12", callback_data="menu_ober_jg12")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="Wähle deinen Jahrgang (Oberstufe):",
        reply_markup=reply_markup
    )

async def show_ober_courses(query, jg):
    chat_id = query.message.chat_id
    user_classes = storage.get_student_classes(chat_id)
    available_courses = get_available_courses()
    
    jg_courses = [c for c in available_courses if c.startswith(jg)]
    user_jg_courses = [c for c in user_classes if c.startswith(jg)]
    
    # Sort according to the order in available_courses (faecher.txt order)
    course_order = {course: index for index, course in enumerate(available_courses)}
    all_jg_courses = sorted(
        list(set(jg_courses + user_jg_courses)),
        key=lambda c: (course_order.get(c, len(available_courses)), c)
    )
    
    keyboard = []
    row = []
    for course in all_jg_courses:
        is_subbed = course in user_classes
        label = f"✅ {course}" if is_subbed else course
        row.append(InlineKeyboardButton(label, callback_data=f"toggle_course:{course}:{jg}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([
        InlineKeyboardButton("➕ Kurs manuell eingeben", callback_data="enter_course_manual")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Zurück", callback_data="menu_ober_jg_selection"),
        InlineKeyboardButton("Fertig 🏁", callback_data="done")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=f"Klicke auf deine Kurse für Jahrgang {jg}, um sie zu abonnieren/abzubestellen:",
        reply_markup=reply_markup
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    data = query.data
    
    if data.startswith("stufe_"):
        selected_stufe = data.split("_")[1]
        storage.set_student_stufe(chat_id, selected_stufe, clear_classes=True)
        
        if selected_stufe == "Mittelstufe":
            await show_mittel_grades(query)
        else:
            await show_ober_jg_selection(query)
            
    elif data == "menu_mittel_grades":
        await show_mittel_grades(query)
        
    elif data.startswith("menu_mittel_letters:"):
        grade = data.split(":")[1]
        await show_mittel_letters(query, grade)
        
    elif data.startswith("set_class:"):
        class_name = data.split(":")[1]
        storage.set_student_stufe(chat_id, "Mittelstufe", clear_classes=True)
        storage.add_class(chat_id, class_name)
        
        await query.edit_message_text(
            text=f"Klasse {class_name} wurde erfolgreich eingerichtet! Du erhältst ab jetzt Benachrichtigungen für diese Klasse."
        )
        
    elif data == "menu_ober_jg_selection":
        await show_ober_jg_selection(query)
        
    elif data.startswith("menu_ober_jg"):
        jg = data.replace("menu_ober_jg", "")
        await show_ober_courses(query, jg)
        
    elif data.startswith("toggle_course:"):
        parts = data.split(":")
        course = parts[1]
        jg = parts[2]
        
        user_classes = storage.get_student_classes(chat_id)
        if course in user_classes:
            storage.remove_class(chat_id, course)
        else:
            storage.add_class(chat_id, course)
            
        await show_ober_courses(query, jg)
        
    elif data == "enter_course_manual":
        context.user_data["waiting_for_course"] = True
        await query.edit_message_text(
            text="Bitte gib den Kursnamen manuell ein (z.B. '11ku2' oder '12ENG1') und sende die Nachricht:"
        )
        
    elif data == "done":
        user_classes = storage.get_student_classes(chat_id)
        if user_classes:
            classes_str = "\n".join(f"- {c}" for c in user_classes)
            await query.edit_message_text(
                text=f"Einrichtung abgeschlossen! Deine abonnierten Kurse:\n{classes_str}"
            )
        else:
            await query.edit_message_text(
                text="Einrichtung abgeschlossen! Du hast derzeit keine Kurse abonniert."
            )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages (e.g. when typing a course name manually)."""
    chat_id = update.effective_chat.id
    if context.user_data.get("waiting_for_course"):
        course_name = update.message.text.strip()
        
        if not course_name:
            await update.message.reply_text("Ungültiger Kursname. Bitte erneut versuchen:")
            return
            
        storage.add_class(chat_id, course_name)
        context.user_data["waiting_for_course"] = False
        
        jg = "12" if course_name.startswith("12") else "11"
            
        await update.message.reply_text(f"Kurs '{course_name}' hinzugefügt!")
        
        # Send fresh menu
        user_classes = storage.get_student_classes(chat_id)
        available_courses = get_available_courses()
        jg_courses = [c for c in available_courses if c.startswith(jg)]
        user_jg_courses = [c for c in user_classes if c.startswith(jg)]
        
        # Sort according to the order in available_courses (faecher.txt order)
        course_order = {course: index for index, course in enumerate(available_courses)}
        all_jg_courses = sorted(
            list(set(jg_courses + user_jg_courses)),
            key=lambda c: (course_order.get(c, len(available_courses)), c)
        )
        
        keyboard = []
        row = []
        for course in all_jg_courses:
            is_subbed = course in user_classes
            label = f"✅ {course}" if is_subbed else course
            row.append(InlineKeyboardButton(label, callback_data=f"toggle_course:{course}:{jg}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([
            InlineKeyboardButton("➕ Kurs manuell eingeben", callback_data="enter_course_manual")
        ])
        keyboard.append([
            InlineKeyboardButton("⬅️ Zurück", callback_data="menu_ober_jg_selection"),
            InlineKeyboardButton("Fertig 🏁", callback_data="done")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text=f"Deine Kurse für Jahrgang {jg}:",
            reply_markup=reply_markup
        )

async def reset_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resets the user's data version to force a refresh of messages."""
    chat_id = update.effective_chat.id
    new_version = storage.increment_reset_version(chat_id)
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Daten zurückgesetzt (Version {new_version}). Du erhältst alle aktuellen Benachrichtigungen beim nächsten Check erneut."
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
        
        # Collect Oberstufe courses from this day's plan
        discovered_courses = set(state.get("discovered_courses", []))
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if tds:
                val = tds[0].text.strip()
                if val.startswith("JG11/") or val.startswith("JG12/"):
                    parts = [p.strip() for p in val.split('/')]
                    if len(parts) > 1 and parts[1]:
                        discovered_courses.add(parts[1])
        state["discovered_courses"] = sorted(list(discovered_courses))
        state_changed = True
        
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

            rows = soup.find_all("tr")
            for Klasse in Klassen:
                matching_rows = []
                for tr in rows:
                    tds = tr.find_all("td")
                    if tds and len(tds) >= 6:
                        if matches_class(Klasse, tds[0].text.strip()):
                            matching_rows.append(tr)

                for idx, tr_klasse in enumerate(matching_rows):
                    zellen_inhalte = [td.text.strip() for td in tr_klasse.find_all("td")]

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
        text="Prüfe auf Updates..."
    )
    await check_updates(context)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Prüfung abgeschlossen."
    )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.startswith("123456"):
        print("Error: TELEGRAM_BOT_TOKEN is not set properly.")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stufe', stufe_command))
    application.add_handler(CommandHandler('hinzufuegen', add))
    application.add_handler(CommandHandler('entfernen', remove))
    application.add_handler(CommandHandler('klassen', classes))
    application.add_handler(CommandHandler('aktualisieren', manual_update))
    application.add_handler(CommandHandler('zuruecksetzen', reset_data))
    
    # Callback query and message handlers
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Scraping Job
    job_queue = application.job_queue
    job_queue.run_repeating(check_updates, interval=3600, first=10)
    
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()