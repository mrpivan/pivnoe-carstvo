import logging
import os.path

import telebot
from telebot import types

from config import TOKEN, LOGS_PATH, ADMIN_ID, MAX_USERS, MAX_SESSIONS, MAX_TOKENS_IN_SESSION
from gpt import ask_gpt, create_prompt, count_tokens
from info import genres, characters, settings


logging.basicConfig(
    filename=LOGS_PATH,
    level=logging.DEBUG,
    format="%(asctime)s %(message)s", filemode="w"
)

# Создаём бота
bot = telebot.TeleBot(TOKEN)

user_data = {}
user_collection = {}


def menu_keyboard(options):
    """Создаёт клавиатуру с указанными кнопками."""
    buttons = (types.KeyboardButton(text=option) for option in options)
    keyboard = types.ReplyKeyboardMarkup(
        row_width=2,
        resize_keyboard=True,
        one_time_keyboard=True
    )
    keyboard.add(*buttons)
    return keyboard


@bot.message_handler(commands=['start'])
def start(message):
    """Обработчик команды /start."""
    user_name = message.from_user.first_name
    user_id = message.from_user.id

    user_collection[user_id] = []

    if not user_data.get(user_id):  # чтобы уже зареганый пользователь не мог обнулить потраченные токены и сессии
        user_data[user_id] = {
            'session_id': 0,
            'genre': None,
            'character': None,
            'setting': None,
            'state': 'регистрация',
            'session_tokens': 0
        }

    bot.send_message(message.chat.id, f"Привет, {user_name}! Я бот, который создаёт истории с помощью нейросети.\n"
                                      f"Мы будем писать историю поочерёдно. Я начну, а ты продолжить.\n"
                                      "Напиши /new_story, чтобы начать новую историю.\n"
                                      f"А когда ты закончишь, напиши /end.",
                     reply_markup=menu_keyboard(["/new_story"]))


@bot.message_handler(commands=['begin'])
def begin_story(message):
    """Обработчик команды /begin."""
    # Проверяем, что пользователь прошёл регистрацию
    # Если записи о нем нет в словаре user_data - советуем ему нажать /start
    if 'username' not in user_data:
         bot.reply_to(message, "Please start with /start to register first.")
    # Если состояние == "регистрация" - пишем ему что прежде чем писать историю, надо допройти регистрацию -> /new_story
    elif user_data['state'] == "регистрация":
        bot.reply_to(message, "Please complete the registration process before starting a new story. Type /new_story to do so.")

    # Иначе переводим состояние на "в истории"
    else:
        user_data['state'] = "in_story"
    # Запрашиваем ответ нейросети
    get_story(message)


@bot.message_handler(commands=['debug'])
def send_logs(message):
    # Если текущий пользователь имеет id = ADMIN_ID:
    if message.chat.id:
     # с помощью os.path.exists проверяем что файл с логами существует == ADMIN_ID:
        if os.path.exists(LOGS_PATH):
    # если все ОК - отправляем пользователю файл с логами LOGS_PATH
            bot.send_document(message.chat.id, open(LOGS_PATH, 'rb'))
    # если НЕ ОК - пишем пользователю сообщение что файл не найден
        else:
            bot.reply_to(message, "Log file not found.")
    else:
        bot.reply_to(message, "You are not authorized to access this command.")


@bot.message_handler(commands=['end'])
def end_the_story(message):
    # Если пользователь ещё не начал историю (его нет в user_collection)
    # то пишем ему об этом и предлагаем начать -> '/begin'
    if 'user_name' not in user_data:
        bot.reply_to(message, "Please start with /begin to initiate a story.")
    elif user_data['state'] != "in_story":
        bot.reply_to(message, "You haven't started a story yet. Start with /begin.")
    # Завершающий историю запрос к ГПТ
    # вызываем ask_gpt с режимом 'end'
    else:
        # Request the final part of the story from the GPT model
        final_story = ask_gpt("end")
    # Отправляем пользователю финал истории
        bot.send_message(message.chat.id, final_story)
    # Благодарим его за совместное творчество и выводим кнопки new_story и debug
    bot.send_message(message.chat.id, "Thank you for the storytelling journey! What would you like to do next?", 
                     reply_markup=menu_keyboard(['/new_story'],['debug']))

    # Очищаем предысторию сообщений чтобы они не попали в следующую сессию
    user_data['chat_history'] = []
    # Обнуляем счетчик токенов, израсходованных за сессию
    user_data['used_tokens'] = 0
    # Ставим режим "регистрация" чтобы направить пользователя на выбор
    # персонажа, жанра и сеттинга для следующей сессии
    user_data[genres][characters][settings] = "registration"


@bot.message_handler(commands=['new_story'])
def registration(message):
    """Обработчик команды /new_story."""
    users_amount = len(user_data)
    if users_amount > MAX_USERS:
        bot.send_message(message.chat.id, 'Лимит пользователей для регистрации превышен')
        return

    # отправляем пользователю вопрос о жанре и выводим клавиатуру с вариантами genres
    bot.send_message(message.chat.id, "Choose a genre for the story:", reply_markup=menu_keyboard(genres))
    # назначаем обработчиком следующего шага функцию handle_genre
    bot.register_next_step_handler(message, handle_genre)


def handle_genre(message):
    """Записывает ответ на вопрос о жанре и отправляет следующий вопрос о персонаже."""
    user_id = message.from_user.id
    # считываем ответ на предыдущий вопрос
    genre = message.text
    # Если пользователь отвечает что-то не то (not in genres), то отправляем ему вопрос ещё раз
    if genre not in genres:
        bot.send_message(message.chat.id, "Выбери один из предложенных на клавиатуре жанров:",
                         reply_markup=menu_keyboard(genres))
        bot.register_next_step_handler(message, handle_genre)
        return
    # обновляем данные пользователя
    user_data[user_id]['genre'] = genre
    user_data[user_id]['state'] = 'в истории'
    # отправляем следующий вопрос про главного героя и выводим клавиатуру с вариантами characters
    bot.send_message(message.chat.id, "Выбери главного героя:",
                     reply_markup=menu_keyboard(characters))
    # назначаем обработчиком следующего шага функцию handle_character
    bot.register_next_step_handler(message, handle_character)


def handle_character(message):
    """Записывает ответ на вопрос о персонаже и отправляет следующий вопрос о сеттинге."""
    # считываем ответ на предыдущий вопрос
    user_response = message.text
    chat_id = message.chat.id
    # Если пользователь отвечает что-то не то (not in characters), то отправляем ему вопрос ещё раз
    if user_response not in characters:
    # обновляем данные пользователя - вписываем выбранного персонажа
        bot.send_message(chat_id, "Please choose a character from the options:", reply_markup=menu_keyboard(characters))
        return
    # отправляем следующий вопрос про сеттинг и выводим клавиатуру с вариантами settings
    user_data['character'] = user_response
    bot.send_message(chat_id, "Choose a setting for the story:", reply_markup=menu_keyboard(settings))

    # назначаем обработчиком следующего шага функцию handle_setting
    bot.register_next_step_handler(message, handle_setting)


def handle_setting(message):
    """Записывает ответ на вопрос о сеттинге."""
    # Считываем ответ на предыдущий вопрос
    user_response = message.text
    chat_id = message.chat.id
    # Если пользователь отвечает что-то не то (not in settings), то отправляем ему вопрос ещё раз
    if user_response not in settings:
        bot.send_message(chat_id, "Please choose a setting from the options:", reply_markup=menu_keyboard(settings))
        return
    # Обновляем данные пользователя - добавляем выбранный сеттинг и устанавливаем статус в 'регистрация пройдена'
    user_data['settings'] = user_response
    user_data['state'] = 'регистрация пройдена'

    bot.send_message(message.chat.id, "Можешь переходить к истории написав /begin.",
                     reply_markup=menu_keyboard(["/begin"]))


@bot.message_handler(content_types=['text'])
def story_handler(message):
    """
    Эта функция работает до тех пор, пока пользователь не нажмет кнопку "/end"
    или не выйдет за лимиты токенов в сессии. Все ответные сообщения пользователя будут попадать
    в эту же функцию благодаря декоратору "message_handler(content_types=['text'])"
    """
    user_id = message.from_user.id
    user_answer = message.text

    # добавляем в историю переписки часть истории, написанную пользователем
    user_collection[user_id].append({'role': 'user', 'content': user_answer})

    # подсчитываем токены в части истории, написанной пользователем
    tokens_in_user_answer = count_tokens(user_answer)

    # добавляем эти токены к общему счетчику токенов за сессию session_tokens
    user_data[user_id]['session_tokens'] += tokens_in_user_answer

    # подсчитываем токены, которые будут потрачены на отправку предыстории
    tokens = 0
    for row in user_collection[user_id]:
        tokens += count_tokens(row['content'])

    # добавляем эти токены к общему счетчику токенов за сессию session_tokens
    user_data[user_id]['session_tokens'] += tokens

    # проверяем что мы не вышли за лимит токенов
    if user_data[user_id]['session_tokens'] > MAX_TOKENS_IN_SESSION:
        bot.send_message(
            message.chat.id,
            'В рамках данной темы вы вышли за лимит вопросов.\nМожете начать новую сессию, введя new_story',
            reply_markup=menu_keyboard(["/new_story", "/end"])
        )
        return

    gpt_text = ask_gpt(user_collection[user_id])
    # Сразу же добавляем ответ от GPT в историю переписки в assistant content,
    # чтобы он учитывался при следующих запросах в рамках данной сессии
    user_collection[user_id].append({'role': 'assistant', 'content': gpt_text})

    # И считаем токены, потраченные на ответ от GPT
    tokens_in_gpt_answer = count_tokens(gpt_text)
    # добавляем эти токены к общему счетчику токенов за сессию session_tokens
    user_data[user_id]['session_tokens'] += tokens_in_gpt_answer

    # выводим пользователю продолжение истории и кнопку для завершения сессии (истории)
    bot.send_message(message.chat.id, gpt_text, reply_markup=menu_keyboard(['/end']))


# @bot.message_handler(content_types=['text'])
def get_story(message):
    """
    Обработчик для генерирования начала истории.
    Эта функция отрабатывает один раз за сессию.
    """
    user_id = message.from_user.id
    # Так как изначально session_id = 0, то перед запросом увеличиваем это значение на 1
    user_data[user_id]['session_id'] += 1

    # Проверяем что лимит сессий не превышен
    if user_data[user_id]['session_id'] > MAX_SESSIONS:
        bot.send_message(
            user_id,
            'К сожалению, Вы израсходовали лимит сессий 😢\nПриходите позже)'
        )
        return

    # Генерируем промпт для system content
    user_story = create_prompt(user_data[user_id])

    user_collection[user_id].append({'role': 'system', 'content': user_story})
    # Считаем токены, которые будут потрачены сейчас при запросе
    tokens_for_start_story = count_tokens(user_story)

    # добавляем эти токены к общему счетчику токенов за сессию session_tokens
    user_data[user_id]['session_tokens'] += tokens_for_start_story

    bot.send_message(message.chat.id, "Генерирую...")

    # Непосредственно делаем сам запрос
    gpt_text = ask_gpt(user_collection[user_id])
    # Сразу же добавляем ответ от GPT в историю переписки в assistant content,
    # чтобы он учитывался при следующих запросах в рамках данной сессии
    user_collection[user_id].append({'role': 'assistant', 'content': gpt_text})

    # И считаем токены, потраченные на ответ от GPT
    tokens_in_gpt_answer = count_tokens(gpt_text)

    # добавляем эти токены к общему счетчику токенов за сессию session_tokens
    user_data[user_id]['session_tokens'] += tokens_in_gpt_answer

    # проверяем что мы не вышли за лимит токенов
    if user_data[user_id]['session_tokens'] > MAX_TOKENS_IN_SESSION:
        bot.send_message(
            message.chat.id,
            'В рамках данной темы вы вышли за лимит вопросов.\nМожете начать новую сессию, введя new_story',
            reply_markup=menu_keyboard(["/new_story", "/end"])
        )
        return

    # Обработка возможных проблем в ответе от GPT:
    if gpt_text is None:
        bot.send_message(
            message.chat.id,
            "Не могу получить ответ от GPT :(",
            reply_markup=menu_keyboard(["/new_story", "/end"])
        )

    elif gpt_text == "":
        bot.send_message(
            message.chat.id,
            "Не могу сформулировать решение :(",
            reply_markup=menu_keyboard(["/new_story", "/end"])
        )
        logging.info(f"TELEGRAM BOT: Input: {message.text}\nOutput: Error: нейросеть вернула пустую строку")

    else:
        # если проблем нет - выводим ответ от GPT пользователю
        msg = bot.send_message(message.chat.id, gpt_text)
        # и назначаем обработчиком последующих сообщений от пользователя функцию story_handler
        bot.register_next_step_handler(msg, story_handler)


bot.infinity_polling()
