import requests
import os
import time
import telebot

def split_text_into_chunks(text, chunk_size):
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
    return chunks


supported_formats = ['audio/flac', 'audio/mpeg', 'audio/mp4', 'video/mp4',
                     'audio/x-m4a', 'audio/ogg', 'audio/wav', 'video/webm']
file_supported_formats = ['.flac', '.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.ogg', '.wav', '.webm']

def get_chat_response(history, client, model):
    
    try:
        # دریافت پاسخ از مدل اول
        response = client.chat.completions.create(
            model=model,
            messages=history,
            stream=False
        ).choices[0].message.content

        return response

    except Exception as e:
        print(f"Error in get_chat_response: {e}")
        return "خطایی در پردازش درخواست شما رخ داده است. لطفاً مجدداً امتحان کنید."

# تابع ارسال پاسخ مدل اول به مدل دوم برای فرمت‌بندی کدها
def format_code_with_another_model(response, client):
    # ساختار پیام برای ارسال به مدل دوم
    history_for_formatting = [
        {"role": "system", "content": "وظیفه تو این است که در پیام کاربر هیچ تغییری ندی اما اگه بخشی از آن پیام مربوط به کدنویسی هست را داخل تگ <pre></pre> قرار بدی"},
        {"role": "user", "content": response}
    ]

    # ارسال درخواست به مدل دوم
    formatted_response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history_for_formatting,
        stream=False
    ).choices[0].message.content

    return formatted_response

def whisper(file_url, client):
  response = requests.get(file_url)
  file_extention = os.path.splitext(file_url)[-1]
  if file_extention.lower() == '.oga':
      file_extention = '.ogg'
  try:
    if response.status_code == 200:
      if file_extention.lower() in file_supported_formats:
        file_name = f"downloaded_file{file_extention}"

        with open(file_name, 'wb') as f:
          f.write(response.content)

        with open(file_name, 'rb') as f:

          transcription = client.audio.transcriptions.create(
              file = (file_name, f.read()),
              model = "whisper-large-v3",
              temperature = 0.0
          )
        os.remove(file_name)
  except Exception as e:
    print(e)
  
  return transcription.text

def get_gpt_response(text: str, client, task: str):
    if task == "default":
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    "role": "system",
                    "content": "وظیفه تو تصحیح غلط های املایی در یک متن هست. تو نباید هیج تغییری در حالت صحبت یا محتوای متن انجام بدی و فقط باید در سطح کلمات غلط های املایی رو درست کنی."
                },
                {
                    "role": "user",
                    "content": f"""کلمات این متن رو بدون هیچ تغییری در حالت صحبت متن تصحیح املایی کن و کلمات رو از حالت فعلی در نیار. یعنی کلمات مجلسی رو عامیانه نکن و برعکس. و متن رو دوباره بفرست {text}"""
                }
            ],
            stream=False
        ).choices[0].message.content
    elif task == "summary":
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {
                    "role": "system",
                    "content": "وظیفه تو خلاصه سازی یک متن هست بدون اینکه از معناش چیزی کم بشه یا نکته ای جا بیفته."
                },
                {
                    "role": "user",
                    "content": f"""این متن رو به این حالت خلاصه کن : باید همه نکات مهم استخراج بشن. نباید هیچ نکته مهمی جا بمونه. حالت صحبت متن رو عوض نکن. با فرمت قابل فهمی بنویس: {text}"""
                }
            ],
            stream=False
        ).choices[0].message.content
    
    elif task == 'weekly-report':
        response = client.chat.completions.create(
            model = 'gpt-4o',
            messages = [
                {
                    "role": "system",
                    "content": "You are a report assistant, user will give you a breif explannation of what he did during the week and you are supposed to wrap everything up in a weekly-report format. use markdown"
                },
                {
                    "role":"user",
                    "content": f"{text}"
                }
            ],
            stream=False
        ).choices[0].message.content

    elif task == 'daily-report':
        response = client.chat.completions.create(
            model = 'gpt-4o',
            messages = [
                {
                    "role": "system",
                    "content": "use the information that is provided by the user to create a daily report. use markdown"
                },
                {
                    "role":"user",
                    "content": f"{text}"
                }
            ],
            stream=False
        ).choices[0].message.content
        
    return response
