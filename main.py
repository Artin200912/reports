import os
import json
from datetime import datetime
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.types import BotCommand
from openai import OpenAI
from groq import Groq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from utils import get_gpt_response
import logging
from functools import wraps
from typing import Optional
import time
from utils import supported_formats, whisper

load_dotenv()
openai_client = OpenAI(api_key=OPENAI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
bot = TeleBot(BOT_TOKEN)

bot.set_my_commands([
    BotCommand('start', 'start the bot'),
    BotCommand('help', 'get help'),
    BotCommand('monthly_report', 'generate and send monthly report')
])

# ایجاد فولدرها در صورت عدم وجود
BASE_REPORTS_DIR = "reports"
DAILY_DIR = os.path.join(BASE_REPORTS_DIR, "daily-report")
WEEKLY_DIR = os.path.join(BASE_REPORTS_DIR, "weekly-report")

os.makedirs(DAILY_DIR, exist_ok=True)
os.makedirs(WEEKLY_DIR, exist_ok=True)

def create_monthly_plot(metadata_logs, month_number):
    """Create a plot showing total hours worked per week for the month"""
    try:
        # Get the last 4 weeks of data
        recent_weeks = metadata_logs[-4:]
        
        # Extract total hours from each week's summary
        weeks = []
        app_dev_hours = []
        ai_dev_hours = []
        
        for week_data in recent_weeks:
            week_summary = week_data[-1]['week_summary']
            weeks.append(f"Week {week_summary['week_number']}")
            app_dev_hours.append(week_summary['total_app_hours'])
            ai_dev_hours.append(week_summary['total_ai_hours'])
        
        # Create the plot
        plt.figure(figsize=(10, 6))
        
        # Plot Application Development hours
        plt.plot(weeks, app_dev_hours, marker='o', color='blue', linestyle='-', 
                linewidth=2, markersize=8, label='Application Development')
        
        # Plot AI Development hours
        plt.plot(weeks, ai_dev_hours, marker='o', color='green', linestyle='-', 
                linewidth=2, markersize=8, label='AI Development')
        
        # Add labels and title
        plt.xlabel("Week")
        plt.ylabel("Hours Worked")
        plt.title(f"Month {month_number}: Total Hours Worked per Week")
        
        # Calculate and display totals
        total_app_dev = sum(app_dev_hours)
        total_ai_dev = sum(ai_dev_hours)
        plt.figtext(0.15, 0.85, f"Total Application Development Hours: {total_app_dev} hrs", fontsize=10)
        plt.figtext(0.15, 0.80, f"Total AI Development Hours: {total_ai_dev} hrs", fontsize=10)
        
        # Add legend and adjust layout
        plt.legend()
        plt.tight_layout()
        
        # Save plot
        plot_filename = f'monthly_development_hours_{month_number}.png'
        plt.savefig(plot_filename)
        plt.close()
        
        return plot_filename
    except Exception as e:
        logger.error(f"Error creating monthly plot: {str(e)}")
        return None

def generate_monthly_report():
    """Generate monthly report from 4 weekly reports"""
    monthly_dir = os.path.join(BASE_REPORTS_DIR, "monthly-report")
    os.makedirs(monthly_dir, exist_ok=True)
    
    # تعیین شماره ماه بر اساس تعداد پوشه‌های موجود
    month_folders = [d for d in os.listdir(monthly_dir) 
                    if os.path.isdir(os.path.join(monthly_dir, d)) 
                    and d.startswith('weekly-report-month')]
    month_number = len(month_folders) + 1
    
    # ایجاد پوشه برای گزارش‌های هفتگی این ماه
    weekly_month_dir = os.path.join(monthly_dir, f"weekly-report-month{month_number}")
    os.makedirs(weekly_month_dir, exist_ok=True)
    
    # Load metadata for plotting
    metadata_file = os.path.join(DAILY_DIR, "metadata.json")
    with open(metadata_file, "r", encoding="utf-8") as file:
        metadata_logs = json.load(file)
    
    # Create monthly plot
    plot_filename = create_monthly_plot(metadata_logs, month_number)
    if plot_filename:
        plot_destination = os.path.join(weekly_month_dir, plot_filename)
        os.rename(plot_filename, plot_destination)
    
    # جمع‌آوری ۴ گزارش هفتگی آخر
    weekly_reports = sorted([
        f for f in os.listdir(WEEKLY_DIR) 
        if f.startswith('weekly_report') and f.endswith('.md')
    ])[-4:]
    
    consolidated_text = ""
    # کپی گزارش‌های هفتگی به پوشه ماهانه و حذف فایل‌های اصلی
    for report_file in weekly_reports:
        source_path = os.path.join(WEEKLY_DIR, report_file)
        dest_path = os.path.join(weekly_month_dir, report_file)
        
        # خواندن محتوا برای گزارش ماهانه
        with open(source_path, 'r', encoding='utf-8') as file:
            consolidated_text += file.read() + "\n\n"
            
        # کپی فایل به پوشه ماهانه
        if os.path.exists(source_path):
            # کپی فایل
            with open(source_path, 'r', encoding='utf-8') as source, \
                 open(dest_path, 'w', encoding='utf-8') as dest:
                dest.write(source.read())
            
            # فقط حذف فایل گزارش هفتگی
            os.remove(source_path)
    
    try:
        monthly_report = get_gpt_response(consolidated_text, openai_client, task="monthly-report")
        
        current_date = datetime.now()
        month = current_date.strftime("%B_%Y")
        filename = f"monthly_report_{month}.md"
        filepath = os.path.join(weekly_month_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(monthly_report)
        
        logger.info(f"Monthly report generated successfully: {filename}")
        return filepath, plot_destination if plot_filename else None
    
    except Exception as e:
        logger.error(f"Error generating monthly report: {str(e)}")
        return None, None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiting decorator
def rate_limit(seconds: int):
    """
    Decorator to implement rate limiting for bot commands
    Args:
        seconds: The cooldown period in seconds
    """
    def decorator(func):
        last_called = {}  # Dictionary to store last call times for each user
        
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            user_id = message.from_user.id  # Get user ID from message
            current_time = time.time()      # Get current timestamp
            
            # Check if user is in cooldown period
            if user_id in last_called and current_time - last_called[user_id] < seconds:
                remaining = int(seconds - (current_time - last_called[user_id]))
                bot.reply_to(message, f"Please wait {remaining} seconds before trying again.")
                return
            
            last_called[user_id] = current_time  # Update last call time
            return func(message, *args, **kwargs)  # Execute the wrapped function
        return wrapper
    return decorator

def get_next_report_filename(folder, base_name="report", extension=".md"):
    """
    Generate the next available filename in sequence, taking weeks into account
    Args:
        folder: Directory path
        base_name: Base name for the file
        extension: File extension
    Returns:
        str: Next available filename
    """
    # Load existing metadata to determine the current week and report count
    metadata_file = os.path.join(folder, "metadata.json")
    if os.path.exists(metadata_file):
        with open(metadata_file, "r", encoding="utf-8") as file:
            metadata = json.load(file)
            current_week = len(metadata)  # Current week (1-based)
            if current_week > 0:
                reports_in_current_week = len([
                    entry for entry in metadata[current_week - 1]
                    if isinstance(entry, dict) and 'filename' in entry
                ])
                if reports_in_current_week >= 7:
                    current_week += 1
                    reports_in_current_week = 0
            else:
                current_week = 1
                reports_in_current_week = 0
    else:
        current_week = 1
        reports_in_current_week = 0

    # Calculate the absolute report number
    report_number = ((current_week - 1) * 7) + reports_in_current_week + 1
    filename = f"{folder}/{base_name}{report_number}{extension}"
    
    return filename

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
    try:
        log_file = os.path.join(folder, filename)
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as file:
                logs = json.load(file)
        else:
            logs = []

        # Extract report number from filename (e.g., "report8.md" -> 8)
        report_num = int(''.join(filter(str.isdigit, metadata['filename'])))
        
        # Calculate which week this report belongs to (1-based indexing)
        week_index = (report_num - 1) // 7
        
        # Ensure we have enough weeks in our logs
        while len(logs) <= week_index:
            logs.append([])
        
        # Add the metadata to the appropriate week
        logs[week_index].append(metadata)
        
        # Sort reports within the week by report number
        logs[week_index].sort(key=lambda x: int(''.join(filter(str.isdigit, x['filename']))) 
                             if isinstance(x, dict) and 'filename' in x else float('inf'))
        
        # If this week has 7 reports and no summary yet, add the summary
        reports_in_week = [entry for entry in logs[week_index] 
                          if isinstance(entry, dict) and 'filename' in entry]
        
        has_summary = any(isinstance(entry, dict) and 'week_summary' in entry 
                         for entry in logs[week_index])
        
        if len(reports_in_week) == 7 and not has_summary:
            week_number = week_index + 1
            ai_hours = [entry['ai'] for entry in reports_in_week]
            app_hours = [entry['app'] for entry in reports_in_week]
            
            summary = {
                "week_summary": {
                    "week_number": week_number,
                    "ai_hours_list": ai_hours,
                    "app_hours_list": app_hours,
                    "total_ai_hours": sum(ai_hours),
                    "total_app_hours": sum(app_hours)
                }
            }
            logs[week_index].append(summary)

        with open(log_file, "w", encoding="utf-8") as file:
            json.dump(logs, file, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error in log_report_metadata: {str(e)}")
        return

def create_weekly_plot(ai_hours, app_hours, week_number):
    """Create a plot for weekly hours and save it."""
    try:
        # Define x-axis labels for the plot
        days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        # Create a new figure with specified size
        plt.figure(figsize=(10, 6))
        
        # Plot Application Development hours line
        plt.plot(days_of_week, app_hours, marker='o', color='blue', linestyle='-', 
                linewidth=2, markersize=8, label='Application Development')
        
        # Plot AI Development hours line
        plt.plot(days_of_week, ai_hours, marker='o', color='green', linestyle='-', 
                linewidth=2, markersize=8, label='AI Development')
        
        # Add labels and title
        plt.xlabel("Day of the Week")
        plt.ylabel("Hours Worked")
        plt.title(f"Week {week_number}: Hours Worked in Application and AI Development")
        
        # Calculate and display totals
        total_app_dev = sum(app_hours)
        total_ai_dev = sum(ai_hours)
        plt.figtext(0.15, 0.85, f"Total Application Development Hours: {total_app_dev} hrs", fontsize=12)
        plt.figtext(0.15, 0.80, f"Total AI Development Hours: {total_ai_dev} hrs", fontsize=12)
        
        # Add legend and adjust layout
        plt.legend()
        plt.tight_layout()
        
        # Save plot to file
        plot_filename = f'week_{week_number}_development_hours.png'
        plt.savefig(plot_filename)
        plt.close()  # Close figure to free memory
        
        return plot_filename
    except Exception as e:
        print(f"Error creating plot for week {week_number}: {str(e)}")
        return None


def consolidate_reports_and_create_weekly():
    """Consolidate daily reports and create weekly summary"""
    # Check for metadata file
    metadata_file = os.path.join(DAILY_DIR, "metadata.json")
    if not os.path.exists(metadata_file):
        return

    # Load metadata
    with open(metadata_file, "r", encoding="utf-8") as file:
        metadata_logs = json.load(file)
    
    # Get the list of already processed weeks
    processed_weeks_file = os.path.join(WEEKLY_DIR, "processed_weeks.json")
    processed_weeks = set()
    if os.path.exists(processed_weeks_file):
        with open(processed_weeks_file, "r", encoding="utf-8") as file:
            processed_weeks = set(json.load(file))
    
    # فقط آخرین هفته تکمیل شده را پیدا کن
    current_week = len(metadata_logs)
    if current_week > 0 and len(metadata_logs[-1]) == 8:  # اگر هفته آخر کامل است
        week_number = current_week
        
        # اگر این هفته قبلاً پردازش شده، برگرد
        if week_number in processed_weeks:
            return None
            
        week_data = metadata_logs[-1]  # آخرین هفته
        summary = week_data[-1]['week_summary']
        week_reports = [entry['filename'] for entry in week_data[:7]]
        
        # Create weekly folder
        weekly_folder = os.path.join(WEEKLY_DIR, f"daily-report-week{week_number}")
        os.makedirs(weekly_folder, exist_ok=True)

        # Setup plot paths
        plot_filename = f'week_{week_number}_development_hours.png'
        plot_destination = os.path.join(weekly_folder, plot_filename)

        # Only create plot and move files if they haven't been processed yet
        weekly_report_path = os.path.join(WEEKLY_DIR, f"weekly_report{week_number}.md")
        if not os.path.exists(weekly_report_path) or not os.path.exists(plot_destination):
            # Create plot
            if not os.path.exists(plot_destination):
                temp_plot = create_weekly_plot(
                    summary['ai_hours_list'],
                    summary['app_hours_list'],
                    week_number
                )
                # Move plot to weekly folder
                if temp_plot:
                    os.rename(temp_plot, plot_destination)
            
            # Generate weekly report if needed
            if not os.path.exists(weekly_report_path):
                # Consolidate all daily reports
                consolidated_text = ""
                for report_file in week_reports:
                    report_path = os.path.join(DAILY_DIR, report_file)
                    if os.path.exists(report_path):
                        with open(report_path, "r", encoding="utf-8") as file:
                            consolidated_text += file.read() + "\n\n"
                
                # Generate weekly summary using GPT
                weekly_report = get_gpt_response(consolidated_text, openai_client, task="weekly-report")
                with open(weekly_report_path, "w", encoding="utf-8") as file:
                    file.write(weekly_report)

            # Move daily reports to weekly folder
            for report_file in week_reports:
                source_path = os.path.join(DAILY_DIR, report_file)
                destination_path = os.path.join(weekly_folder, report_file)
                if os.path.exists(source_path) and not os.path.exists(destination_path):
                    os.rename(source_path, destination_path)

        # Add this week to processed weeks
        processed_weeks.add(week_number)
        
        # Save processed weeks
        with open(processed_weeks_file, "w", encoding="utf-8") as file:
            json.dump(list(processed_weeks), file)
        
        result = {
            'week_number': week_number,
            'plot_path': plot_destination,
            'report_path': weekly_report_path,
            'is_new': True
        }
        
        # Check for monthly report generation
        weekly_reports = [f for f in os.listdir(WEEKLY_DIR) if f.startswith('weekly_report') and f.endswith('.md')]
        if len(weekly_reports) == 4:  # اگر ۴ گزارش هفتگی داریم
            monthly_report_path, plot_destination = generate_monthly_report()
            if monthly_report_path:
                # Reset processed weeks after generating monthly report
                processed_weeks.clear()
                with open(processed_weeks_file, "w", encoding="utf-8") as file:
                    json.dump(list(processed_weeks), file)
                
                return {
                    'monthly_report': monthly_report_path,
                    'week_data': result,
                    'plot_destination': plot_destination
                }
        
        return result
            
    return None

def send_weekly_reports(chat_id):
    """Send weekly reports and plots to user"""
    result = consolidate_reports_and_create_weekly()
    
    if result:  # اگر نتیجه‌ای وجود دارد
        if isinstance(result, dict) and 'monthly_report' in result:
            # اگر گزارش ماهانه باشد
            return result
        else:
            # اگر گزارش هفتگی باشد
            # Send plot with caption
            with open(result['plot_path'], 'rb') as photo:
                bot.send_photo(chat_id, photo, 
                             caption=f"Weekly Development Hours Summary - Week {result['week_number']}")
            
            # Send report document
            with open(result['report_path'], 'rb') as report:
                bot.send_document(chat_id, report, 
                               caption=f"Weekly Report - Week {result['week_number']}")
    
    return result

@bot.message_handler(commands=['start'])
def send_welcome_message(message):
    bot.send_message(message.chat.id, f"Hello dear <b>{message.from_user.first_name}</b>", parse_mode="HTML")

@rate_limit(60)
@bot.message_handler(content_types=['audio', 'video', 'voice'])
def handle_files(message):
    """
    Handle incoming audio/video/voice files
    Args:
        message: Telegram message object containing the file
    """
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    if not BOT_TOKEN:
        bot.reply_to(message, "Bot token not configured properly.")
        return
        
    file_info = None
    mime_type = None

    # Determine file type and get file information
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

    # Process the file if it's valid
    if file_info and mime_type in supported_formats:
        # Generate file download link
        file_link = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}'
        # Get transcription using Whisper
        transcription_text = whisper(file_link, groq_client)
        # Generate report using GPT
        final_response = get_gpt_response(transcription_text, openai_client, task="daily-report")
        
        # Clean up and save report
        bot.delete_message(message.chat.id, waiting_msg.message_id)
        report_filename = get_next_report_filename(DAILY_DIR)
        with open(report_filename, "w", encoding="utf-8") as file:
            file.write(final_response)

        # Save metadata
        metadata = {
            "filename": os.path.basename(report_filename),
            "path": report_filename,
            "generated_at": datetime.now().isoformat()
        }
        log_report_metadata(DAILY_DIR, metadata)

        # Send report back to user
        with open(report_filename, "rb") as file:
            bot.send_document(message.chat.id, file)

        # Only process and send weekly reports if this report completed a week
        report_num = int(''.join(filter(str.isdigit, os.path.basename(report_filename))))
        is_week_complete = report_num % 7 == 0  # True if this report completes a week
        if is_week_complete:
            result = send_weekly_reports(message.chat.id)
            
            # اگر گزارش ماهانه ایجاد شده، آن را هم ارسال کن
            if isinstance(result, dict) and 'monthly_report' in result:
                monthly_report_path = result['monthly_report']
                monthly_plot_path = result['plot_destination']
                
                # ارسال نمودار ماهانه
                if monthly_plot_path:
                    with open(monthly_plot_path, 'rb') as plot:
                        bot.send_photo(
                            message.chat.id,
                            plot,
                            caption="Monthly Development Hours Summary"
                        )
                
                # ارسال گزارش ماهانه
                with open(monthly_report_path, 'rb') as monthly_file:
                    bot.send_document(
                        message.chat.id, 
                        monthly_file,
                        caption="Monthly Report Generated"
                    )
    else:
        bot.reply_to(message, "An error occurred, please try again.")

@bot.message_handler(content_types=['text'])
def process_text(message):
    """Handle text messages and generate reports"""
    # Send waiting message
    waiting_msg = bot.reply_to(message, 'I received the info, please wait..')
    
    # Generate daily report from text
    final_response = get_gpt_response(message.text, openai_client, task="daily-report")
    
    # Remove waiting message
    bot.delete_message(message.chat.id, waiting_msg.message_id)

    # Save report to file
    report_filename = get_next_report_filename(DAILY_DIR)
    with open(report_filename, "w", encoding="utf-8") as file:
        file.write(final_response)
    
    hours = get_gpt_response(message.text, openai_client, task="worked_hours")
    try:
        # Parse hours data
        json_string = hours.replace("'", '"')
        data = json.loads(json_string)
    except json.JSONDecodeError:
        bot.reply_to(message, "Error processing hours data. Please try again.")
        return

    # Get the report number to check if it completes a week
    report_num = int(''.join(filter(str.isdigit, os.path.basename(report_filename))))
    is_week_complete = report_num % 7 == 0  # True if this report completes a week

    # Save metadata
    metadata = {
        "filename": os.path.basename(report_filename),
        "path": report_filename,
        "generated_at": datetime.now().isoformat(),
        'ai': data['ai'],
        'app': data['app']
    }
    log_report_metadata(DAILY_DIR, metadata)

    # Send report to user
    with open(report_filename, "rb") as file:
        bot.send_document(message.chat.id, file)

    # Only process and send weekly reports if this report completed a week
    if is_week_complete:
        result = send_weekly_reports(message.chat.id)
        
        # اگر گزارش ماهانه ایجاد شده، آن را هم ارسال کن
        if isinstance(result, dict) and 'monthly_report' in result:
            monthly_report_path = result['monthly_report']
            monthly_plot_path = result['plot_destination']
            
            # ارسال نمودار ماهانه
            if monthly_plot_path:
                with open(monthly_plot_path, 'rb') as plot:
                    bot.send_photo(
                        message.chat.id,
                        plot,
                        caption="Monthly Development Hours Summary"
                    )
            
            # ارسال گزارش ماهانه
            with open(monthly_report_path, 'rb') as monthly_file:
                bot.send_document(
                    message.chat.id, 
                    monthly_file,
                    caption="Monthly Report Generated"
                )

# Start bot with error handling
try:
    # Start bot with timeout settings
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
except Exception as e:
    # Log any polling errors
    print(f"Bot polling error: {str(e)}")
finally:
    # Ensure bot stops properly
    bot.stop_polling()
