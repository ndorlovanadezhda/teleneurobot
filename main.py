from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, KeyboardButtonPollType, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.types import CallbackQuery
from aiogram.utils.chat_action import ChatActionSender
from aiogram.types import ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Any, Awaitable, Callable, Dict
from aiogram import types
from html import escape
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
from gigachat import GigaChat
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat
import uuid

#токены доступа API tg и gigachat
token = '8009570785:AAEfwwxaAVeEYOO3ApRiYn_mtT_WJeCIY2I'
GigaChatKey = "ZmQ2MTFmMDAtZmU2OS00YTIyLTlhYTAtYmM1YWI3OTYzMzk1OmQ3NGI2ZDBlLTgxNjQtNGYyNC05NjA5LTIwODQwODc1ZGFhNQ=="

llm = GigaChat(
    credentials=GigaChatKey,
    scope="GIGACHAT_API_PERS",
    model="GigaChat",
    verify_ssl_certs=False, # Отключает проверку наличия сертификатов НУЦ Минцифры
    streaming=False,
)

#Заполнение пользователем анкеты при регистрации (FSM).
class UserForm(StatesGroup):
    FIO = State()
    age = State()
    level = State()
    quizcount = State()
    finalRegistration = State()

bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())


#Включаем логирование
logging.basicConfig(force=True, level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


#Проверка зарегистрированности пользователя при вызове команд (Middleware).
class SomeMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        id = data['event_update'].message.chat.id
        state: FSMContext = data['state']
        current_state = await state.get_state()

        if current_state in [UserForm.FIO.state, UserForm.age.state, UserForm.level.state, UserForm.quizcount.state]:
            return await handler(event, data)

        if data ['event_update'].message.text != '/start':
            async with aiosqlite.connect('users.db') as db:
                async with db.execute("SELECT id FROM users WHERE id = ?", (id, )) as cursor:
                    if await cursor.fetchone() is None:
                        await bot.send_message(chat_id=id, text="К сожалению, вы не прошли регистрацию")
                        return
        result = await handler(event, data)
        return result

#Начало работы
@dp.message(Command('start'), State(None))
async def cmd_start(message: Message, state: FSMContext):
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id, )) as cursor:
            if await cursor.fetchone() is None:
                await message.answer(f"Привет, {message.from_user.first_name}! Для использования бота введите ФИО: ")
                await state.set_state(UserForm.FIO)
            else:
                await message.answer(f"Привет {message.from_user.first_name}! Вы уже прошли регистрацию!")

# Завершение любого процесса
@dp.message(Command("abort"), State(None))
async def stop_bot(message: types.Message, state: FSMContext):
    """Команда для остановки всех процессов."""
    await message.answer("Бот завершает работу. До свидания!")
    await state.clear()
    await bot.session.close()
    await dp.shutdown()
    await asyncio.get_event_loop().stop()

#Заполнение анкеты пользователем повторно после начала использования (FSM).
@dp.message(F.text, UserForm.finalRegistration)
async def cmd_start2(message: Message, state: FSMContext):
    await message.answer ("Заполните анкету заново. Введите ФИО:")
    await state.set_state(UserForm.FIO)

# Проверка и ввод ФИО(должно быть 3 слова)
@dp.message(F.text, UserForm.FIO)
async def input_fio(message: Message, state: FSMContext):
    if len(message.text.split()) != 3:
        await message.answer("ФИО введено неверно, введите повторно:")
        return
    await state.update_data(fio=message.text)
    await message.answer("Введите ваш возраст(только цифры): ")
    await state.set_state(UserForm.age)

# Проверка и ввод возраста(должна быть цифра)
@dp.message(F.text, UserForm.age)
async def input_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите корректный возраст: ")
        return

    await state.update_data(age=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="хороший уровень"),],
            [KeyboardButton(text="средний уровень"),],
            [KeyboardButton(text="все плохо"),],
            [KeyboardButton(text="затрудняюсь ответить"),
            ],
        ],
        resize_keyboard=True
    )

    await message.answer("Оцените свою нейропластичность на данный момент", reply_markup=keyboard)
    await state.set_state(UserForm.level)

@dp.message(F.text, UserForm.level)
async def input_level(message: Message, state: FSMContext):
    level_options = [
        "хороший уровень",
        "средний уровень",
        "все плохо",
        "затрудняюсь ответить"
    ]
    if message.text not in level_options:
        await message.answer("Пожалуйста, выберите один из предложенных вариантов.")
        return
    await state.update_data(level=message.text)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="5"),],
            [KeyboardButton(text="10"),],
            [KeyboardButton(text="15"),],
        ],
        resize_keyboard=True
    )
    await message.answer(f"Сколько вопросов вы предпочитаете в тесте на нейропластичность?", reply_markup=keyboard)
    await state.set_state(UserForm.quizcount)

@dp.message(F.text, UserForm.quizcount)
async def input_quizcount(message: Message, state: FSMContext):
    level_options = [
        "5",
        "10",
        "15",
    ]
    if message.text not in level_options:
        await message.answer("Пожалуйста, выберите один из предложенных вариантов.")
        return

    await state.update_data(quizcount=message.text)
    data = await state.get_data()
#Заносим информацию в бд
    async with aiosqlite.connect('users.db') as db:
        cursor = await db.execute('SELECT * FROM users WHERE id = ?', (message.from_user.id,))
        user = await cursor.fetchone()
        if user:
            await db.execute('UPDATE users SET fio = ?, age = ?, level = ?, quizcount = ? WHERE id = ?',
                             (data['fio'], data['age'], data['level'], data['quizcount'], message.from_user.id))
        else:
            # Создаем нового пользователя
            await db.execute('INSERT INTO users (id, fio, age, level, notification, quizlevel, quizcount, quizpoints, quizleft) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (message.from_user.id, data['fio'], data['age'], data['level'], False,"Затрудняюсь ответить", data['quizcount'], 0, 0))

        await db.commit()

    await message.answer(f"Спасибо, {data['fio']}. Регистрация выполнена успешно!")
    await state.clear()
    await cmd_mainmenu(message)


# Напоминания или периодические сообщения
# Команды включения/выключения уведомлений
@dp.message(Command('onnotification'))
async def ontext(message: Message):
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET notification = TRUE WHERE id = ?", (message.from_user.id,))
        await db.commit()
    await message.answer('Уведомления активированы!')

@dp.message(Command('offnotification'))
async def offtext(message: Message):
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET notification = FALSE WHERE id = ?", (message.from_user.id,))
        await db.commit()
    await message.answer('Уведомления отключены!')

#Наличие командного меню.
menu1 = {
    'menu': [
        {'text': 'Тест-оценка нейропластичности'},
        {'text': 'Раздел упражнений нейрогимнастики'},
        {'text': 'Раздел упражнений на память'},
        {'text': 'Раздел статей о нейропластичности'},
        {'text': 'Уведомления', 'status': False},
        {'text': 'Мой прогресс'}
    ],
}

levels = [
        "хороший уровень",
        "средний уровень",
        "все плохо"
]

# Главная команда меню
@dp.message(Command('menu'), State(None))
async def cmd_mainmenu(message:Message):
    builder = ReplyKeyboardBuilder()
    user_id = message.from_user.id
    for item in menu1['menu']:
        if item.get('text') == 'Уведомления':
            status = await get_user_status(user_id)
            if status:
                 text = 'Отключить уведомления'
                 item['status'] = True
            else:
                 text = 'Включить уведомления'
                 item['status'] = False
            builder.button(text=text)
        else:
             builder.button(text=item.get('text'))
    builder.adjust(2, 2)
    await message.answer("Выберите действие из меню", reply_markup=builder.as_markup(resize_keyboard=True))

#Получение информации об уведомлениях
async def get_user_status(user_id: int):
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT notification FROM users WHERE id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            status = result[0]
        return status

#Получение информации о прогрессе!
@dp.message(F.text == 'Мой прогресс')
async def osebe(message : Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Пройти анкету заново", callback_data="back_to_discription")
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT * FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    await message.answer(f"\nФИО: {res[1]}\nВозраст: {res[2]}\nВаш уровень: {res[3]}\nКоличество задач из опроса в день: {res[7]}\nЗаработанные очки: {res[9]}",  reply_markup=builder.as_markup())

# Сообщение для пользователя
async def send_msg(dp):
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT * FROM users WHERE notification=TRUE") as cursor:
            async for row in cursor:
                await bot.send_message(chat_id=row[0], text='Вы давно не занимались! Попробуйте пройти тест на нейропластичность!')

@dp.message((F.text =='Включить уведомления') | (F.text == 'Отключить уведомления'))
async def toggle_notifications(message: Message):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
          status = await get_user_status(id)
          status = not status
          await db.execute("UPDATE users SET notification = ? WHERE id = ?", (status, id))
          await db.commit()
    await cmd_mainmenu(message)

#Раздел статей о нейропластичности
@dp.message(F.text =='Раздел статей о нейропластичности')
async def osebe(message : Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Хочу еще статью", callback_data="new_article")
        # Получение первой статьи
    article = await fetch_article()
    await message.answer(
        f"Первая статья о нейропластичности:\n{article}",
        reply_markup=builder.as_markup()
    )

async def fetch_article():
    global chat_answer
    messages_questions = [
    SystemMessage(
        content= "Тебе нужно написать информацию о нейропластичности: предоставить ссылки на актуальные статьи и кратко изложить их содержание, также ты можешь упомянуть книги и труды о нейропластичности и старение мозга, факторы влияния, пути решения, используй около 100 слов для одного ответа"
    ),
     "Убедись, что ты не повторяешься - не нужно писать о проверке данных."
    ]
    res = llm.invoke(messages_questions)
    messages_questions.insert(len(messages_questions) - 1,res)
    chat_answer = messages_questions[(len(messages_questions)-2)].content
    return chat_answer

# FSM для тестов и ответов по ним
class TaskStateN(StatesGroup):
    sentence_answer = State() # Продолжение теста(да/нет)
    waiting_answer_for_task = State() # Ожидание ответа на задачу
    stoping = State() # Остановка работы

#Нейрогимнастика - начало
@dp.message(F.text == "Раздел упражнений нейрогимнастики", State(None))
async def neuro_task(message:Message, state:FSMContext):
    await start_neuro(message, state)

# Из главного меню + текстом вызов команды нейрогимнастики
@dp.message(Command('neuro'))
async def start_neuro(message:Message, state: FSMContext):
    await message.answer("Перед началом упражнения озвучим некоторые правила. \n Вы можете уточнять технику упражнения(используя '?'), если упражнение выполнено напиши 'Упражнение выполнено', чтобы бот засчитал это задание. \n При этом если уточнения больше не требуются вы можете остановить бота с помощью команды /stop. \n Напечатай 'Готов' если хочешь начать.")
    await state.set_state(TaskStateN.sentence_answer)


# Проверка на ввод и отгрузка уровня пользователя
@dp.message(TaskStateN.sentence_answer)
async def confirm_task(message:Message, state:FSMContext):
    if message.text.lower() == 'готов':
        level, builder = await func_for_buttons(state, message.from_user.id)
        await message.answer(f"Ваш текущий уровень сложности: {level}\n Выберит одно из действий:", reply_markup=builder.as_markup())
    else:
        await state.set_state(TaskStateN.stoping)
        await stoping(message, state)


async def func_for_buttons(state: FSMContext, user_id: int):
    async with aiosqlite.connect("users.db") as db:
            async with db.execute("SELECT level FROM users WHERE id = ?", (user_id,)) as cursor:
                res = await cursor.fetchone()

    level = res[0]

    builder = InlineKeyboardBuilder()
    builder.button(text = 'Изменить уровень сложности', callback_data='levelNeuro')
    builder.button(text = 'Описание', callback_data='info_neuro')
    builder.button(text = 'Начать упражнения', callback_data='tasks')
    builder.button(text = 'Отмена', callback_data='stopNeuro')
    builder.adjust(2)

    return level, builder


# Остановка игры
@dp.callback_query(F.data == 'stopNeuro')
async def stoping_from_kboard(callback:CallbackQuery, state: FSMContext):
    await state.set_state(TaskStateN.stoping)
    await stoping(callback.message, state)

# Остановка игры
@dp.message(TaskStateN.stoping)
async def stoping(message:Message, state:FSMContext):
    await message.answer(f'Игра остановлена')
    await state.clear()

# Описание нейрогимнастики
@dp.callback_query(F.data == 'info_neuro')
async def info_neuro(callback: CallbackQuery):
    description = (
        "Привет, немного о нейрогимнастике...\n\n"
        "Нейрогимнастика — это комплекс телесно-ориентированных упражнений, направленный на развитие связей между структурами головного мозга.\n"
        "С помощью специально подобранных упражнений организм координирует работу правого и левого полушарий и развивает взаимодействие тела и интеллекта.\n"
        "Перед началом упражнения озвучим некоторые правила. Вы можете уточнять технику упражнения, при этом если уточнения больше не требуются или ты не хочешь выполнять это упражнение вы можете остановить бота с помощью команды /stop но при этом баллы не зачтутся.\n"
        "Вы можете настроить уровень сложности под себя.\n"
        "Напиши 'Упражнение выполнено', если ты хочешь закончить обьяснения и выполнил упражнение.\n"
        "За упражнения тебе засчитываются баллы - в зависимости от уровня сложности:\n"
        "  • Для новичков: 1 балл\n"
        "  • Средние по сложности: 2 балла\n"
        "  • Сложные упражнения: 3 балла\n"

    )
    await callback.message.edit_text(description, reply_markup=await create_back_keyboardNeuro())
    await callback.answer()

async def create_back_keyboardNeuro():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_menuNeuro")
    return builder.as_markup()

# Вызов генерации упражнения
@dp.callback_query(F.data == 'tasks')
async def task_single(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выполнение упражнений")
    await callback.answer()
    await state.set_state(TaskStateN.waiting_answer_for_task)
    await generate_question(callback)


# Генерация упражнения
async def generate_question(arg):
    if isinstance(arg, types.Message):
        id = arg.from_user.id
        msg = arg
    elif isinstance(arg, types.CallbackQuery):
        id = arg.from_user.id
        msg = arg.message

    task_id = str(uuid.uuid4()) # идентификатор задачи

    global chat_answer
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level, age FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
            if res:
                level = res[0]
                age = res[1]
                story = ''
            else:
                await msg.answer("Ошибка БД")
                return

    message_questions = [
        {
            "role":"system",
            "content":"Ты должен описать любое физическое упражнения для развития нейропластичности."
            "Есть 3 уровня сложности: для профессионалов(сложный уровень), средний уровень, и для людей с проблемами с нейропластичностью(легкий уровень)"
            f"Сгенерируй задачу на уровне сложности: {level}"
            f"Сгенерируй упражнение подходящее для возраста: {age}"
            "Не пиши решение или объяснение, только описание упражнения. "
            "Убедись, что такое упражнение не было предложено ранее."
        }
    ]

    res = llm.invoke(message_questions)
    await msg.answer(res.content)

    story += f"\nБот: {res.content} (Id: {task_id})"

    # Сохраняем историю в бд
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET story = ? WHERE id = ?", (story, id))
        await db.commit()

    return task_id

# Обработчик ответа пользователя
@dp.message(TaskStateN.waiting_answer_for_task)
async def answer_waiting(message:Message, state:FSMContext):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level, quizpoints, story FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    points = res[1]
    story = res[2]

    # Извлекаем идентификатор
    task_id = None
    if 'Id:' in story:
        task_id = story.split("Id:")[0]

    alfa = 0
    sumalfa = 0
    if level == "все плохо" or level == "затрудняюсь ответить":
        alfa = 1
    elif level == "средний уровень":
        alfa = 2
    elif level == "хороший уровень":
        alfa = 3

    user_conversation = message.text
    print(task_id)
    if '?' in user_conversation:
        message_conversations = [
            {
                "role":"system",
                "content":f"Ты проверяющий и ты отвечаешь на вопросы пользователя, которые он тебе задает по упражнению {task_id}. Отвечаешь до тех пор, пока пользователь не напишет 'Упражнение выполнено'."
            },
            {
                "role":"user",
                "content":user_conversation
            }
        ]

        res = await llm.ainvoke(message_conversations)
        answering = res.content.strip()
        await message.answer(f"Ответ на ваш вопрос: {answering}")

        new_conversation = f"Пользователь:{user_conversation}\nБот: {answering}"
        story += new_conversation
    else:
      if user_conversation == "Упражнение выполнено":
        points += alfa
        sumalfa += alfa
      await message.answer(f'Заработанный балл: {sumalfa}')
      async with aiosqlite.connect("users.db") as db:
            async with db.execute("SELECT quizpoints FROM users WHERE id = ?", (id,)) as cursor:
                rows = await cursor.fetchone()
                pointsALL = int(rows[0]) + alfa
            await db.execute("UPDATE users SET quizpoints = ? WHERE id = ?", (pointsALL, id,))
            await db.commit()
      points = 0
      await state.clear()
      await start_neuro(message, state)
      return

class TaskStateM(StatesGroup):
    answer = State()            
    stoping = State()    

#Упражнения на память
@dp.message(F.text == "Раздел упражнений на память", State(None))
async def memory_task(message:Message, state:FSMContext):
    await start_memory(message, state)

@dp.message(Command('memory'),State(None))
async def start_memory(message:Message, state: FSMContext):
    await message.answer("Перед началом упражнения озвучим некоторые правила. \n Внимательно запоминайте появившийся текст, после ознакомления с ним вас ждет уточняющий вопрос.")
    await memory(message)

# Основная функция теста, выводит меню с выбором уровня и количества задач
async def memory(arg):
    if isinstance(arg, types.Message):
     id = arg.from_user.id
     msg = arg
    elif isinstance(arg, types.CallbackQuery):
      id = arg.from_user.id
      msg = arg.message
    # Извлекаем текущие уровень сложности и количество задач из базы данных
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]

    # Создаем кнопки для управления тестом-оценкой
    builder = InlineKeyboardBuilder()
    builder.button(text='Уровень сложности', callback_data='levelMemory' )
    builder.button(text='Инфо', callback_data='info2')
    builder.button(text='Начать опрос', callback_data='taskM')
    builder.button(text='Отмена', callback_data='stopMemory')
    builder.adjust(2)
    # Выводим меню пользователю
    await msg.answer(f"Упражнения на память \nВаш текущий уровень сложности:\n{level}\nВыберите действие:", reply_markup=builder.as_markup())
  
#вывод информации
@dp.callback_query(F.data == 'info2')
async def infotest(callback: CallbackQuery):
    description = (
   
   "Привет, это раздел с упражнениями на память!\n\n"
        "Когда мы тренируем память, в мозге формируются новые связи, которые повышают нейропластичность и восстанавливают поврежденные клетки. То есть заучивая информацию, мы одновременно развиваем мышление, воображение и концентрацию.\n"
        "Чем чаще мы заставляем мозг работать, тем медленнее он будет подвергаться возрастным изменениям. Учите стихи, читайте книги и пересказывайте сюжет, вспоминайте приятные моменты из жизни и делитесь с близкими. Регулярно развивайте свою память, чтобы сохранить интеллектуальные способности и снизить риск появления деменции и болезни Альцгеймера.\n"
        "Внимательно запоминайте появившийся текст, после ознакомления с ним вас ждет уточняющий вопрос.Вы можете остановить бота с помощью команды /stop но при этом баллы не зачтутся.\n"
        "Вы можете настроить уровень сложности под себя.\n"
        "За упражнения тебе засчитываются баллы - в зависимости от уровня сложности:\n"
        "  • Для новичков: 1 балл\n"
        "  • Средние по сложности: 2 балла\n"
        "  • Сложные упражнения: 3 балла\n"
    )
    await callback.message.edit_text(description, reply_markup=await create_back_keyboardMemory())
    await callback.answer()

async def create_back_keyboardMemory():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_menuMemory")
    return builder.as_markup()

 # Остановка игры
@dp.callback_query(F.data == 'stopMemory')
async def stoping_from_kboard1(callback:CallbackQuery, state: FSMContext):
    await state.set_state(TaskStateM.stoping)
    await stoping(callback.message, state)

# Остановка игры
@dp.message(TaskStateM.stoping)
async def stoping(message:Message, state:FSMContext):
    await message.answer(f'Игра остановлена')
    await state.clear()

#Тест-оценка генерация задачи
@dp.callback_query(F.data == 'taskM', State(None))
async def taskMemory(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выполнение упражнения на память!")
    await callback.answer()
    await state.set_state(TaskStateM.answer)
    await generate_text(callback)

async def generate_text(arg):
    if isinstance(arg, types.Message):
     id = arg.from_user.id
     msg = arg
    elif isinstance(arg, types.CallbackQuery):
      id = arg.from_user.id
      msg = arg.message
    global chat_answer
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    messages_questions = [
    SystemMessage(
        content= "Тебе нужно придумать текст не более 100 слов с множеством описаний(прилагательные и числительные), текст связный. "
    )
    ]
    res = llm.invoke(messages_questions)
    messages_questions.insert(len(messages_questions) - 1,res)
    chat_answer = messages_questions[(len(messages_questions)-2)].content
    story = chat_answer
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET story = ? WHERE id = ?", (story, id))
        await db.commit()

    builderM = InlineKeyboardBuilder()
    builderM.button(text="Запомнил, теперь вопрос!", callback_data="question_memory")
    await msg.answer(f"{res.content}", reply_markup=builderM.as_markup())


@dp.callback_query(F.data == "question_memory")
async def send_question(callback: CallbackQuery):
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level, story FROM users WHERE id = ?", (callback.from_user.id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    story = res[1]

    messages = [
        SystemMessage(
            content= f"Составь вопрос по тексту {story}.Вопрос должен соответстовать уровню {level}. Вопрос должен относится к количеству или свойству обьекта из текста, при этом ответ есть в тексте. Например, 'сколько чайников стояло в комнате?'"
        )
    ]

    res = await llm.ainvoke(messages)
    story += res.content
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET story = ? WHERE id = ?", (story, callback.from_user.id))
        await db.commit()
    await callback.message.edit_text(res.content)
    #process_user_answer(message,state)


# Обработчик ответа пользователя
@dp.message(TaskStateM.answer, ~F.text.in_({"/stop","/start","/menu","/onnotification", "/offnotification", "нет", "Режим викторины"}))
async def process_user_answer(message: Message, state: FSMContext):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT story, level, quizpoints FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[1]
    story = res[0]
    points = res[2]
    sumalfa = 0
    alfa = 0
    if level == "все плохо" or level == "затрудняюсь ответить":
        alfa = 1
    elif level == "средний уровень":
        alfa = 2
    elif level == "хороший уровень":
        alfa = 3

    user_answer = message.text
    messages = [
        SystemMessage(
            content="Ты проверяющий, оцени насколько правильно ответил пользователь. Выдай только 'Верно' если ответ правильный, 'Неверно' если неправильный. Если ответ неверный, напиши верный ответ."
        ),
        HumanMessage(
            content=f"Вопрос: {story} \nОтвет пользователя: {user_answer}"
        )
    ]

    res = await llm.ainvoke(messages)
    evaluation = res.content.strip()
    if evaluation == "Верно":
        points = points + alfa
        sumalfa += alfa 
    await message.answer(f"Оценка: {evaluation}")

    id = int(message.from_user.id)
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET quizpoints = ? WHERE id = ?", (points, id))
        await db.commit()

    await message.answer(f'Количество заработанных баллов: {sumalfa}\n')
    points = 0
    await state.clear()


# FSM для генерации задач для теста-опроса
class OprosState(StatesGroup):
    answer = State()             # ответы пользователя
    count = State()              # количество вопросов

@dp.message(Command('test'),State(None))
async def cmd_test(message: Message):
    await test(message)

@dp.message(F.text == "Тест-оценка нейропластичности", State(None))
async def button_test(message: Message):
    await test(message)

@dp.callback_query(F.data == "back_to_menu")
async def inftest(callback: CallbackQuery):
    await test(callback)

@dp.callback_query(F.data == "back_to_menuNeuro")
async def infneuro(callback:CallbackQuery, state:FSMContext):
    await start_neuro(callback.message, state)

@dp.callback_query(F.data == "back_to_menuMemory")
async def infmemory(callback: CallbackQuery):
    await memory(callback)    

@dp.callback_query(F.data == "back_to_discription")
async def inftest2(callback: CallbackQuery, state: FSMContext):
    await cmd_start2(callback.message, state)

@dp.callback_query(F.data == "new_article")
async def send_new_article(callback: CallbackQuery):
    """Обработка нажатия кнопки и отправка новой статьи."""
    article = await fetch_article()
    builder = InlineKeyboardBuilder()
    builder.button(text="Хочу еще статью", callback_data="new_article")

    await callback.message.edit_text(
        f"Новая статья о нейропластичности:\n{article}",
        reply_markup=builder.as_markup()
    )

@dp.message(Command('stop'),OprosState.answer)
async def cmd_stop(message: Message, state: FSMContext):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT quizpoints FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    points = res[0]
    async with aiosqlite.connect("users.db") as db:
        await db.execute("UPDATE users SET quizleft = ? WHERE id = ?", (0, id)) 
        await db.commit()  
    await message.answer(f'Тест закончен досрочно\nКоличество заработанных баллов: {points}')
    await state.clear()

# Окончание викторины
@dp.message(((F.text == "Тест-оценка нейропластичности") | (F.text == "/start") | (F.text == "/test") | (F.text == "/menu") | (F.text == "/")), OprosState.answer)
async def stop_quiz(message: Message, state: FSMContext):
    await message.answer("Для окончания викторины введите команду: /stop")
    await state.set_state(OprosState.answer)

# Основная функция теста, выводит меню с выбором уровня и количества задач
async def test(arg):
    if isinstance(arg, types.Message):
     id = arg.from_user.id
     msg = arg
    elif isinstance(arg, types.CallbackQuery):
      id = arg.from_user.id
      msg = arg.message
    # Извлекаем текущие уровень сложности и количество задач из базы данных
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT quizlevel, quizcount FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    count = res[1]
    # Создаем кнопки для управления тестом-оценкой
    builder = InlineKeyboardBuilder()
    builder.button(text='Уровень сложности', callback_data='flevel1' )
    builder.button(text='Количество задач', callback_data='many' )
    builder.button(text='Начать опрос', callback_data='task1')
    builder.button(text='Инфо', callback_data='info1')
    builder.adjust(2)
    # Выводим меню пользователю
    await msg.answer(f"Тест-оценка нейропластичности\nВаш текущий уровень сложности:\n{level}\nКоличество задач: \n{count}\nВыберите действие:", reply_markup=builder.as_markup())

# Обработка выбора количества задач в викторине
@dp.callback_query(F.data == 'many')
async def many_quizmod(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите количество задач")
    await state.set_state(OprosState.count)

# Обработка ввода количества задач пользователем
@dp.message(OprosState.count)
async def many_choise(message: Message, state: FSMContext):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT quizcount FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    count = res[0]
    if not message.text.isdigit() or message.text == "0":
        await message.answer("Введите корректное число: ")
        return
    count = int(message.text)
    async with aiosqlite.connect("users.db") as db:
          await db.execute("UPDATE users SET quizcount = ? WHERE id = ?", (count, id))
          await db.commit()
    await state.clear()
    await test(message)



#Режим выбор уровня
@dp.callback_query(F.data.in_(['flevel1', 'levelNeuro', 'levelMemory']))
async def freemode_level(callback: CallbackQuery):
    print("Вызвали")
    id = callback.from_user.id
    source = callback.data
    # Извлекаем текущий уровень сложности
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT level FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    builder = InlineKeyboardBuilder()
    # Создаем кнопки для выбора уровня сложности
    for i, level_name in enumerate(levels):
       builder.button(text=level_name, callback_data=f'level{i+1}:{source}')
    #builder.button(text='Назад', callback_data='back_to_freemode')
    builder.adjust(1)
    await callback.message.edit_text(f'Изменение уровня сложности\nВаш текущий уровень сложности:\n{level}\nВыберите новый уровень:', reply_markup=builder.as_markup())
    await callback.answer()

# Обработка выбора уровня сложности
@dp.callback_query(F.data.startswith('level'))
async def process_level_choice(callback: CallbackQuery):
    id = callback.from_user.id
    data_parts = callback.data.split(':')
    level_number = int(data_parts[0].replace('level', ''))
    source = data_parts[1]
    level = levels[level_number-1]
    if source == 'flevel1':
      await callback.message.edit_text(f'Вы выбрали уровень сложности: {level}')
      async with aiosqlite.connect("users.db") as db:
            await db.execute("UPDATE users SET quizlevel = ? WHERE id = ?", (level, id))
            await db.commit()
      await callback.answer()
    else:
      await callback.message.edit_text(f'Вы выбрали уровень сложности: {level}')
      async with aiosqlite.connect("users.db") as db:
            await db.execute("UPDATE users SET level = ? WHERE id = ?", (level, id))
            await db.commit()
      await callback.answer()
    if source == 'flevel1':
        await test(callback)
    elif source == 'levelNeuro':
        level, builder = await func_for_buttons(state=TaskStateN.sentence_answer, user_id=callback.from_user.id)
        await callback.message.edit_text(f"Ваш текущий уровень сложности: {level}\n Выберите одно из действий:", reply_markup=builder.as_markup())
        await callback.answer()
    elif source == 'levelMemory':
        await memory(callback)


#Оценка нейропластиности вывод информации
@dp.callback_query(F.data == 'info1')
async def infotest(callback: CallbackQuery):
    description = (
        "Привет это тест-опрос о нейропластичности!\n\n"
        "Нейропластичность — способность мозга на протяжении всей жизни менять свою структуру, функции или нейронные связи в ответ на внутренние или внешние раздражители и в ответ на опыт.\n"
        "Нейропластичность позволяет эффективно адаптироваться к изменениям. Нужные связи закрепляются, а те, что не используются, — разрушаются.\n "
        "Ты можешь выбрать количество вопросов и уровень сложности.\n"
        "За упражнения тебе засчитываются баллы - в зависимости от уровня сложности:\n"
        "  • Для новичков: 1 балл\n"
        "  • Средние по сложности: 2 балла\n"
        "  • Сложные упражнения: 3 балла\n"
    )
    await callback.message.edit_text(description, reply_markup=await create_back_keyboard())
    await callback.answer()

async def create_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_menu")
    return builder.as_markup()

#Тест-оценка генерация задачи
@dp.callback_query(F.data == 'task1', State(None))
async def taskfreedom(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Начинаем тест")
    await callback.answer()
    await state.set_state(OprosState.answer)
    await process_chat_task(callback)

async def process_chat_task(arg):
    if isinstance(arg, types.Message):
     id = arg.from_user.id
     msg = arg
    elif isinstance(arg, types.CallbackQuery):
      id = arg.from_user.id
      msg = arg.message
    global chat_answer
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT quizlevel, age  FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    level = res[0]
    age = res[1]
    messages_questions = [
    SystemMessage(
        content= "Тебе нужно придумать задачу для оценки нейропластичности человека не имея никаких материалов кроме бумаги и ручки, в задаче должен быть вопрос, на который нужно ответить пользователю.Есть 3 уровня сложности: для профессионалов(сложный уровень), средний уровень, и для людей с проблемами с нейропластичностью(легкий уровень)"
            f"Сгенерируй задачу на уровне сложности: {level}"
            f"Сгенерируй задачу подходящее для возраста: {age}"
            "Не пиши решение или объяснение, только описание упражнения. "
            "Убедись, что такое упражнение не было предложено ранее."
    ),
    ]
    res = llm.invoke(messages_questions)
    messages_questions.insert(len(messages_questions) - 1,res)
    chat_answer = messages_questions[(len(messages_questions)-2)].content
    await msg.answer(res.content)


# Обработчик ответа пользователя
@dp.message(OprosState.answer, ~F.text.in_({"/stop","/start","/menu","/onnotification", "/offnotification"}))
async def process_user_answer(message: Message, state: FSMContext):
    id = message.from_user.id
    async with aiosqlite.connect("users.db") as db:
        async with db.execute("SELECT quizlevel, quizcount, quizpoints, quizleft FROM users WHERE id = ?", (id,)) as cursor:
            res = await cursor.fetchone()
    count = res[1]
    points = res[2]
    level = res[0]
    left = res[3]
    print(left)
    alfa = 0
    sumalfa = 0
    if level == "все плохо" or level == "затрудняюсь ответить":
        alfa = 1
    elif level == "средний уровень":
        alfa = 2
    elif level == "хороший уровень":
        alfa = 3

    user_answer = message.text
    messages = [
        SystemMessage(
            content="Ты проверяющий, оцени ответ пользователя и выдай только 'Верно' если ответ правильный, 'Неверно' если неправильный. Если ответ неверный, напиши верный ответ."
        ),
        HumanMessage(
            content=f"Задача: {chat_answer} \nОтвет пользователя: {user_answer}"
        )
    ]

    res = await llm.ainvoke(messages)
    evaluation = res.content.strip()
    if evaluation == "Верно":
        points = points + alfa
        sumalfa = sumalfa + alfa
    await message.answer(f"Оценка: {evaluation}")

    if int(left) + 1 < int(count):
        left = left + 1
        async with aiosqlite.connect("users.db") as db:
          await db.execute("UPDATE users SET quizpoints = ?, quizleft = ? WHERE id = ?", (points, left, id))
          await db.commit()
        await process_chat_task(message)
    else:
        id = int(message.from_user.id)
        await message.answer(f'Поздравляем! \nТест пройден\nКоличество заработанных баллов: {sumalfa}\n')
        left = 0
        points = 0
        async with aiosqlite.connect("users.db") as db:
          await db.execute("UPDATE users SET quizleft = ? WHERE id = ?", (left, id))
          await db.commit()
        await state.clear()


# Ответ на произвольный текст
@dp.message()
async def text_not_appropriate(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get('fio', 'Пользователь')
    await message.answer(f'Уважаемый {name}, нельзя писать произвольный текст.')

# Подключаемся к базе данных
async def start_db():
    async with aiosqlite.connect("users.db") as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER,
            fio VARCHAR(255),
            age INTEGER,
            level VARCHAR(255),
            story TEXT,
            notification BOOLEAN,
            quizlevel VARCHAR(255),
            quizcount INTEGER,
            quizleft INTEGER,
            quizpoints INTEGER
            )
        ''')
        await db.commit()

async def start_bot():
    commands = [
        BotCommand(command='start', description='Начать взаимодействие'),
        BotCommand(command='abort', description='Закончить взаимодействие'),
        BotCommand(command='neuro', description='Начать нейрогимнастику'),
        BotCommand(command='memory', description='Начать упражнения на память'),
        BotCommand(command='stop', description='Закончить проверку нейропластичности'),
        BotCommand(command='menu', description='Выйти в главное меню'),
        BotCommand(command='test', description='Тест-оценка нейропластичности'),
        BotCommand(command='offnotification', description='Отключить уведомления'),
        BotCommand(command='onnotification', description='Включить уведомления'),
    ]
    await bot.set_my_commands(commands, BotCommandScopeDefault())

#Работа  и запуск бота
async def main():
  #Уведомления(каждые 10 секунд)
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.add_job(send_msg, 'interval', seconds=10, args=(dp, ))
    scheduler.start()

    dp.startup.register(start_bot)
    dp.message.outer_middleware(SomeMiddleware())
    dp.startup.register(start_db)
    try:
        print("Бот запущен")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        print("Бот остановлен")

asyncio.run(main())
