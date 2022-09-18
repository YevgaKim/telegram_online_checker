import asyncio
import configparser
from email import message
from telethon import TelegramClient, events, sync
import time
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from datetime import datetime,timedelta
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
import aiogram.utils.markdown as md
from aiogram.types import ParseMode
import maya



config = configparser.ConfigParser()
config.read("config.ini")

api_id   = config['Telegram']['api_id']
api_hash = config['Telegram']['api_hash']
username = config['Telegram']['username']
TOKEN= config["TOKEN"]['token']

bot = Bot(token=TOKEN)
dp = Dispatcher(bot,storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

class Form(StatesGroup):
    username = State()  
    day = State()
    check = State()
    cancel = State()  

client = TelegramClient(username, api_id, api_hash)

TIME=30

client.start()
#Функция которая работает с telethon и возвращает уже обработаную инфу
async def check(data):
    try:
        person=data["username"]
        account = await client.get_entity(person)
        info=account.status.to_dict()
        if info["_"]=='UserStatusOffline':

            dt = maya.parse(info["was_online"]).datetime(to_timezone='Europe/Kyiv', naive=False)
            return f"Был(а) онлайн {dt.date().day}-{dt.date().month}-{dt.date().year} в {dt.time()}"

        elif info["_"]=='UserStatusOnline':
            return f"Пользователь {person} онлайн"

        elif info["_"]=='UserStatusRecently':
            return "Был(a) недавно онлайн"


    except ValueError:
        return "Такого юзернейма не существует. Проверьте правильность написания"
        

#Функция старта которая принимает юзернейм для передачи telethon
@dp.message_handler(commands=['start'])
@dp.message_handler(Text(equals='Start', ignore_case=True), state='*')
async def cmd_start(message: types.Message):
    await Form.username.set()
    await bot.send_message(message.from_user.id,"Введи юзернейм того за кем хочешь следить",reply_markup=types.ReplyKeyboardRemove())



#Функция отмены которая работает в любом state
@dp.message_handler(state='*', commands='cancel')
@dp.message_handler(Text(equals='Сancel', ignore_case=True), state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    await Form.next()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Start")
    current_state=await state.get_state()
    if current_state=="Form:cancel":
        await state.finish()
        await message.reply(f'ОК. Программа закроется через некоторое время сама и уведомит вас об этом, только потом вы опять сможете воспользоваться ботом снова',reply_markup=markup)
    else:
        await state.finish()
        await message.reply(f'ОК. Программа завершилась',reply_markup=markup)

#Функция которая сохраняет юзернейм и спрашивает пользователя о времени слежки
@dp.message_handler(state=Form.username)
async def process_username(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['username'] = message.text
    await Form.next()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("6 ч", "12 ч", "1 д")

    await message.reply("Укажи к-во дней (кнопкой)", reply_markup=markup)


#Функция которая проверяет что бы время было указано верно
@dp.message_handler(lambda message: message.text not in ["6 ч", "12 ч", "1 д"], state=Form.day)
async def process_day(message: types.Message):
    return await message.reply("Укажите к-во дней на клавиатуре")


#Функция которая сохраняет время и выводит инфу и "анкету"  
@dp.message_handler(state=Form.day)
async def process_day(message: types.Message, state: FSMContext):
    await Form.next()
    await state.update_data(day=message.text)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Check")
    async with state.proxy() as data:
        await bot.send_message(
            message.chat.id,
            md.text(
                md.text('Хорошо!'),
                md.text('Это человек за которым мы будем следить - ', md.bold(data['username']),'.'),
                md.text('Столько дней - ', md.bold(data['day']),'.'),
                md.text('Начать слежку - "Сheck".'),
                md.text('Прекратить слежку - "Сancel".'),
                md.text('Внепланово сразу получить статус - "Get status now".'),
                md.text(md.bold('Пожалуйста не флудите!')),
                sep='\n',
            ),reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN)

#Функция которая сразу(смотря в каком режиме, может и не сразу) отправляет все данные о статусе пользователя 
@dp.message_handler(commands="now", state="*")
@dp.message_handler(Text(equals='Get status now', ignore_case=True), state="*")
async def get_online_now(message: types.Message, state: FSMContext):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Сancel","Get status now")
    
    async with state.proxy() as data:
        
        info = await check(data)
        if "Был(а) онлайн" in info:
            await bot.send_message(message.from_user.id,info,reply_markup=markup)
        elif info=="Был(a) недавно онлайн":
            await bot.send_message(message.from_user.id,"У данного пользователя включен режим невидимки в Телеграме",reply_markup=markup)

        elif info=="Такого юзернейма не существует. Проверьте правильность написания":
            await bot.send_message(message.from_user.id,info,reply_markup=markup)

        else:
            await bot.send_message(message.from_user.id,info,reply_markup=markup)

#Функция работает со временем и устанавливает будущее время, то есть конец работы бота
async def check_time(data,date):
    if "6 ч" in data["day"]:
        return date+timedelta(hours=6)
    elif "12 ч" in data["day"]:
        return date+timedelta(hours=12)
    if "1 д" in data["day"]:
        return date+timedelta(days=1)

#Функция которая на протяжении указаного времени проверяет статус указаного пользователя
#и возвращает результат только в случае ошибки или онлайна пользователя(в этом случае или в случае работы
#функции Cancel работа данной функции завершается)
#если пользователь не онлайн, ничего отправляться не будет
@dp.message_handler(commands="check", state=Form.check)
@dp.message_handler(Text(equals='Check', ignore_case=True), state=Form.check)
async def get_online(message: types.Message, state: FSMContext):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("Start")
    markup_2 = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup_2.add("Сancel","Get status now")
    await bot.send_message(message.from_user.id,"Проверка началась",reply_markup=markup_2)
    async with state.proxy() as data:
        date = datetime.now()
        
        future_date = await check_time(data,date)

        while str(date)[:13]!=str(future_date)[:13]:
            current_state = await state.get_state()
            if current_state == None:
                break 
            date = datetime.now()
            info = await check(data)
            if "Был(а) онлайн" in info:
                pass
            elif info=="Был(a) недавно онлайн":
                await bot.send_message(message.from_user.id,"У данного пользователя(или у вас) включен режим невидимки в Телеграме. Проверьте всё и попробуйте ещё.",reply_markup=markup)
                break
            elif info=="Такого юзернейма не существует. Проверьте правильность написания":
                await bot.send_message(message.from_user.id,info,reply_markup=markup)
                break
            else:
                await bot.send_message(message.from_user.id,info,reply_markup=markup)
                break
            #await asyncio.sleep(TIME)  #fast response(instant ban)
            time.sleep(TIME) #slow responce

    await bot.send_message(message.from_user.id,"Проверка окончена",reply_markup=markup)
    await state.finish()
                




if __name__ == '__main__':
    executor.start_polling(dp,skip_updates=True)









    

