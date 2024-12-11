import os
import json
from datetime import datetime
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.types import BotCommand
from openai import OpenAI
from groq import Groq
from utils import split_text_into_chunks, whisper, get_gpt_response, supported_formats

load_dotenv()
openai_client = OpenAI(api_key=OPENAI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

# ایجاد فولدرها در صورت عدم وجود
BASE_REPORTS_DIR = "reports"
DAILY_DIR = os.path.join(BASE_REPORTS_DIR, "daily-report")
WEEKLY_DIR = os.path.join(BASE_REPORTS_DIR, "weekly-report")

os.makedirs(DAILY_DIR, exist_ok=True)
os.makedirs(WEEKLY_DIR, exist_ok=True)

def get_next_report_filename(folder, base_name="report", extension=".md"):
    """نام فایل بعدی را در فولدر مشخص شده تولید می‌کند."""
    index = 1
    while True:
        filename = f"{folder}/{base_name}{index}{extension}"
        if not os.path.exists(filename):
            return filename
        index += 1

def get_next_weekly_folder():
    """ایجاد نام فولدر هفته جدید."""
    week_number = 1
    while True:
        weekly_folder = os.path.join(WEEKLY_DIR, f"daily-report-week{week_number}")
        if not os.path.exists(weekly_folder):
            os.makedirs(weekly_folder, exist_ok=True)
            return weekly_folder
        week_number += 1

def log_report_metadata(folder, metadata, filename="metadata.json"):
    """ذخیره اطلاعات متادیتا در فایل JSON مشخص شده."""
    log_file = os.path.join(folder, filename)
    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8") as file:
            logs = json.load(file)
    else:
        logs = []

    logs.append(metadata)
    with open(log_file, "w", encoding="utf-8") as file:
        json.dump(logs, file, indent=4, ensure_ascii=False)

def consolidate_reports_and_create_weekly():
    """گزارش‌های روزانه را تجمیع کرده و گزارش هفتگی ایجاد می‌کند."""
    daily_reports = [f for f in os.listdir(DAILY_DIR) if f.endswith(".md")]
    if len(daily_reports) >= 7:
        # خواندن محتوای تمام فایل‌های روزانه
        consolidated_text = ""
        for report_file in daily_reports[:7]:
            with open(os.path.join(DAILY_DIR, report_file), "r", encoding="utf-8") as file:
                consolidated_text += file.read() + "\n\n"

        # تولید گزارش هفتگی
        weekly_report = get_gpt_response(consolidated_text, openai_client, task="weekly-report")
        weekly_filename = get_next_report_filename(WEEKLY_DIR, base_name="weekly_report", extension=".md")
        with open(weekly_filename, "w", encoding="utf-8") as file:
            file.write(weekly_report)

        # ذخیره متادیتا برای گزارش هفتگی
        metadata = {
            "filename": os.path.basename(weekly_filename),
            "path": weekly_filename,
            "generated_at": datetime.now().isoformat(),
            "source_files": daily_reports[:7]
        }
        log_report_metadata(WEEKLY_DIR, metadata)

        # انتقال گزارش‌های روزانه به پوشه هفتگی
        weekly_folder = get_next_weekly_folder()
        for report_file in daily_reports[:7]:
            source_path = os.path.join(DAILY_DIR, report_file)
            destination_path = os.path.join(weekly_folder, report_file)
            os.rename(source_path, destination_path)

        # ذخیره متادیتا برای گزارش‌های روزانه هفته
        weekly_metadata = {
            "week_number": len([f for f in os.listdir(WEEKLY_DIR) if f.endswith(".md")]),
            "source_files": daily_reports[:7],
            "generated_at": datetime.now().isoformat()
        }
        log_report_metadata(weekly_folder, weekly_metadata)

bot = TeleBot(BOT_TOKEN)
bot.set_my_commands([
    BotCommand('start', 'start the bot'),
    BotCommand('help', 'get help'),
])

@bot.message_handler(commands=['start'])
def send_welcome_message(message):
    bot.send_message(message.chat.id, f"Hello dear <b>{message.from_user.first_name}</b>", parse_mode="HTML")

@bot.message_handler(content_types=['audio', 'video', 'voice'])
def handle_files(message):
    file_info = None
    mime_type = None

    if message.content_type == 'audio':
        mime_type = message.audio.mime_type
        file_info = bot.get_file(message.audio.file_id)
        waiting_msg = bot.reply_to(message, 'I received your file, wait..')
    elif message.content_type == 'video':
        mime_type = message.video.mime_type
        file_info = bot.get_file(message.video.file_id)
        waiting_msg = bot.reply_to(message, 'I received your file, wait..')
    elif message.content_type == 'voice':
        mime_type = 'audio/ogg'
        file_info = bot.get_file(message.voice.file_id)
        waiting_msg = bot.reply_to(message, 'I received your file, wait..')

    if file_info:
        if mime_type in supported_formats:
            file_link = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}'
            transcription_text = whisper(file_link, groq_client)

            final_response = get_gpt_response(transcription_text, openai_client, task="daily-report")
            bot.delete_message(message.chat.id, waiting_msg.message_id)

            # ذخیره فایل در پوشه daily-report
            report_filename = get_next_report_filename(DAILY_DIR)
            with open(report_filename, "w", encoding="utf-8") as file:
                file.write(final_response)

            # ذخیره متادیتا
            metadata = {
                "filename": os.path.basename(report_filename),
                "path": report_filename,
                "generated_at": datetime.now().isoformat()
            }
            log_report_metadata(DAILY_DIR, metadata)

            with open(report_filename, "rb") as file:
                bot.send_document(message.chat.id, file)

            # بررسی و ایجاد گزارش هفتگی
            consolidate_reports_and_create_weekly()
        else:
            bot.reply_to(message, "The file format is not supported.")
    else:
        bot.reply_to(message, "An error occurred, please try again.")

@bot.message_handler(func=lambda message: True)
def process_text(message):
    bot.reply_to(message, 'I received the info, please wait..')
    final_response = get_gpt_response(message.text, openai_client, task="daily-report")

    # ذخیره فایل در پوشه daily-report
    report_filename = get_next_report_filename(DAILY_DIR)
    with open(report_filename, "w", encoding="utf-8") as file:
        file.write(final_response)

    # ذخیره متادیتا
    metadata = {
        "filename": os.path.basename(report_filename),
        "path": report_filename,
        "generated_at": datetime.now().isoformat()
    }
    log_report_metadata(DAILY_DIR, metadata)

    with open(report_filename, "rb") as file:
        bot.send_document(message.chat.id, file)

    # بررسی و ایجاد گزارش هفتگی
    consolidate_reports_and_create_weekly()

bot.polling()
