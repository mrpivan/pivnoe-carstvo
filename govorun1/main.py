import requests
import telebot


from config import TOKEN, MAX_USER_TTS_SYMBOLS, MAX_TTS_SYMBOLS, IAM_TOKEN, FOLDER_ID
from database import count_all_symbol, create_table, insert_row



bot = telebot.TeleBot(TOKEN)

#тыкни создать таблицу

#create_table()

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, text=f"Привет! Я бот, который конвертирует текст в голос. Для того чтобы начать напиши /tts")

@bot.message_handler(commands=['help'])
def speech(message):
    bot.send_message(message.from_user.id,
                     text="/tts")


@bot.message_handler(commands=['tts'])
def tts_handler(message):
    user_id = message.from_user.id
    bot.send_message(user_id, 'Отправь следующим сообщением текст, чтобы я его озвучил!')
    bot.register_next_step_handler(message, text_to_speech_handler)
    

def text_to_speech_handler(message):
    text = message.text
    user_id = message.from_user.id
    
    text_symbol = is_tts_symbol_limit(message, text)
    if text_symbol is None:
        return
    
    insert_row(user_id, text, text_symbol)
    
    success, response = text_to_speech(text)
    if success is True:
        with open("output.ogg", "wb") as audio_file:
            audio_file.write(response)
            bot.send_voice(message.chat.id, open('output.ogg', 'rb'))
        print("Аудиофайл успешно сохранен как output.ogg")
    else:
        print("Ошибка:", response) 
        

def text_to_speech(text):
    headers = {'Authorization': f"Bearer {IAM_TOKEN}"}
    data = {
        'text': text,
        'emotion': 'good',
        'lang': 'ru-RU',  
        'voice': 'jane',  
        'folderId': FOLDER_ID}
    url = 'https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize'
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return True, response.content
    else:
        return False, "При запросе в SpeechKit возникла ошибка"




def is_tts_symbol_limit(message, text):
    
    user_id = message.from_user.id
      # Получаем текст сообщения без команды
    text_symbols = len(text)
    insert_row(user_id, text, text_symbols)

    # Функция из БД для подсчёта всех потраченных пользователем символов
    all_symbols = count_all_symbol(user_id) + text_symbols

    # Сравниваем all_symbols с количеством доступных пользователю символов
    if all_symbols >= MAX_USER_TTS_SYMBOLS:
        msg = f"Превышен общий лимит SpeechKit TTS {MAX_USER_TTS_SYMBOLS}. Использовано: {all_symbols} символов. Доступно: {MAX_USER_TTS_SYMBOLS - all_symbols}"
        bot.send_message(user_id, msg)
        return None

    # Сравниваем количество символов в тексте с максимальным количеством символов в тексте
    if text_symbols >= MAX_TTS_SYMBOLS:
        msg = f"Превышен лимит SpeechKit TTS на запрос {MAX_TTS_SYMBOLS}, в сообщении {text_symbols} символов"
        bot.send_message(user_id, msg)
        return None
    return len(text)


bot.polling()