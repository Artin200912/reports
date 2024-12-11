from dotenv import load_dotenv
from telebot import TeleBot
from telebot.types import BotCommand 
from openai import OpenAI
import os
from groq import Groq 
from utils import split_text_into_chunks, whisper, get_gpt_response, get_chat_response, supported_formats
import datetime

load_dotenv()
openai_client = OpenAI()
groq_client = Groq()

bot = TeleBot(os.getenv("BOT_TOKEN"))
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
        waiting_msg = bot.reply_to(message, 'I recieved your file, wait..')
    elif message.content_type == 'video':
        mime_type = message.video.mime_type
        file_info = bot.get_file(message.video.file_id)
        waiting_msg = bot.reply_to(message, 'I recieved your file, wait..')
    elif message.content_type == 'voice':
        mime_type = 'audio/ogg'
        file_info = bot.get_file(message.voice.file_id)
        waiting_msg = bot.reply_to(message, 'I recieved your file, wait..')


    if file_info:
        if mime_type in supported_formats:
            file_link = f'https://api.telegram.org/file/bot{os.getenv("BOT_TOKEN")}/{file_info.file_path}'
            transcription_text = whisper(file_link, groq_client)

            final_response = get_gpt_response(transcription_text, openai_client, task="report")

            # if len(final_response) > 3000:
            #     text_chunks = split_text_into_chunks(final_response, 3000)
            #     bot.delete_message(message.chat.id, waiting_msg.message_id)
            #     for chunk in text_chunks:
            #         bot.reply_to(message, chunk)
            bot.delete_message(message.chat.id, waiting_msg.message_id)
            with open('report.md', "w", encoding="utf-8") as file:
                file.write(final_response)
            
            with open('report.md', "rb") as file:
                bot.send_document(message.chat.id, file)
            os.remove('report.md')
        else:
            bot.reply_to(message, "The file format is not supported.")
    else:
        bot.reply_to(message, "an error occured, please try again")

@bot.message_handler(func=lambda message: True)
def process_text(message):
    bot.reply_to(message, 'i recieved the info, please wait..')
    final_response = get_gpt_response(message.text, openai_client, task="report")
    with open('report.md', "w", encoding="utf-8") as file:
        file.write(final_response)
    
    with open('report.md', "rb") as file:
        bot.send_document(message.chat.id, file)
    os.remove('report.md')
        
bot.polling()
