import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F
from zeep import Client
from zeep.helpers import serialize_object
from concurrent.futures import ThreadPoolExecutor
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import os

load_dotenv()

partnumb = ""
part_guid = ""
crossresult = ""

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=API_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

SOAP_KEY1 = os.getenv("API_KEY1")
SOAP_KEY2 = os.getenv("API_KEY2")
DELIVERY_ID = "000000001"

wsdl_url = os.getenv("API_URL")

client = Client(wsdl=wsdl_url)

thread_executor = ThreadPoolExecutor()


def make_soap_request_sync(text):
    payload = {
        "KEY1": SOAP_KEY1,
        "KEY2": SOAP_KEY2,
        "text": text,
        "delivery_id": DELIVERY_ID
    }
    response = client.service.GetSearch(**payload)
    print(response)
    return serialize_object(response)


async def make_soap_request(text):
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(thread_executor, make_soap_request_sync, text)
    return response


def parse_response(response):
    global crossresult
    crossresult = ""  # Initialize crossresult to an empty string

    try:
        if not response.get('success', False):
            return "Нет результатов."

        parts_list = response.get('PartsList', {})
        parts = parts_list.get('Part', [])

        if not parts:
            return "Запчастей не найдено."

        all_parts_info = []

        for part in parts:
            name = part.get('name', 'N/A')
            partnumber = part.get('partnumber', 'N/A')
            brand = part.get('brand', 'N/A')
            guid = part.get('guid', 'N/A')
            crosses = part.get('crosses', {})
            stockss = part.get('stocks', {})

            # Check if stocks are available
            if not (stockss and isinstance(stockss, dict) and stockss.get('stock')):
                continue  # Skip parts with no stocks

            # Prepare stock info
            stocks = stockss.get('stock', [])
            first_stock = stocks[0]
            price = first_stock.get('price', 'N/A')
            count = first_stock.get('count', 'N/A')
            description = first_stock.get('description', 'N/A')
            stock_info = (
                f"*Цена: {round(int(float(price)))}тг*\n"
                f"Остаток на складе: {count}\n"
                f"Склад: {description}\n"
            )

            # Prepare crosslist
            crosslist = []
            if crosses and isinstance(crosses, dict):
                plist = crosses.get('Part', [])
                for item in plist:
                    stocks = item.get('stocks', {}).get('stock', [])
                    if stocks:
                        stock = stocks[0]
                        stockprice = f"*{round(int(float(stock.get('price', 'N/A'))))}тг*"
                        stockcount = stock.get('count', 'N/A')
                        stockdesc = stock.get('description', 'N/A')
                        if stockdesc != 'Партнерский склад':
                            idict = {
                                'brand': item.get('brand', 'N/A'),
                                'partnum': item.get('partnumber', 'N/A'),
                                'name': item.get('name', 'N/A'),
                                'stockprice': stockprice,
                                'stockcount': stockcount,
                                'stockdesc': stockdesc
                            }
                            crosslist.append(idict)
            if len(crosslist) > 7:
                crosslist = crosslist[:7]

            # Create formatted crossresult
            crossresult_part = ""
            vardict = {
                'brand': 'Бренд',
                'partnum': 'Артикул',
                'name': 'Название',
                'stockprice': '*Цена*',
                'stockcount': 'Остаток на складе',
                'stockdesc': 'Склад'
            }
            for dictionary in crosslist:
                for key, value in dictionary.items():
                    crossresult_part += f"{vardict[key]}: {value}\n"
                crossresult_part += "\n"
            if crosslist:
                crossresult_part += f"""\n_*Внимание: Из-за ограничений Telegram выведены только первые 7 аналогов; чтобы посмотреть остальные (если они есть), нажмите на кнопку "Открыть сайт"_"""

            part_info = (
                f"*Информация детали*\n"
                f"Название: {name}\n"
                f"Артикул: {partnumber}\n"
                f"Бренд: {brand}\n"
                f"{stock_info}\n\n"
                f"*Аналоги:*\n\n"
                f"{crossresult_part}\n\n"
            )

            all_parts_info.append(part_info)

        # If no parts with stocks are found
        if not all_parts_info:
            return "Нет доступных деталей с запасами."

        # Concatenate information for all valid parts
        response_message = "\n".join(all_parts_info)
        response_message = response_message.rstrip()

        global partnumb
        global part_guid
        # Assuming partnumb and part_guid need to be set from the last part
        if parts:
            last_part = parts[-1]
            partnumb = last_part.get('partnumber', 'N/A')
            part_guid = last_part.get('guid', 'N/A')

        return response_message

    except Exception as e:
        logging.error(f"Ошибка: {e} | {e.args}")
        return "При обработке произошла ошибка."


@dp.message(Command(commands=['start']))
async def send_welcome(message: types.Message):
    welcome_text = (
        "Бот для поиска автозапчастей\n\n"
        "Отправьте артикул/бренд/код детали (например, KYB 333114); Для оптимального поиска используйте - артикул; артикул + бренд; код номенклатуры."
    )
    await message.reply(welcome_text)


@dp.message(F.text)
async def handle_message(message: types.Message):
    user_text = message.text.strip()

    if not user_text:
        await message.reply("Пожалуйста, отправьте текстовый запрос (фото/документы не принимаются)")
        return

    await message.reply("Поиск...")
    await bot.send_chat_action(message.chat.id, "typing")

    try:
        soap_response = await make_soap_request(user_text)

        response_message = parse_response(soap_response)

        global partnumb
        global part_guid
        global crossresult

        link_button = InlineKeyboardButton(text="Открыть сайт   ",
                                           url=f"https://shym.rossko.ru/product?q={partnumb}&text={part_guid}&isSuggest=true")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[link_button]])
        if response_message != "При обработке произошла ошибка.":
            await message.reply(response_message, parse_mode='Markdown', reply_markup=keyboard)
            crossresult = ""
            part_guid = ""
            partnumb = ""
        elif response_message == "При обработке произошла ошибка.":
            await message.reply(response_message, parse_mode='Markdown')
            crossresult = ""
            part_guid = ""
            partnumb = ""
        user = message.from_user
        if user.is_premium is None:
            usertgprem = "No"
        elif user.is_premium is True:
            usertgprem = "Yes"
        print(
            f"""new search -> userid: {user.id} | username: {user.username} | search: {user_text} | 
            firstname: {user.first_name} | lastname: {user.last_name} | language: {user.language_code} | has tg premium: {usertgprem}""")
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.reply("Произошла ошибка, либо ничего не найдено")


async def main():
    await bot.set_my_commands(
        [BotCommand(command="/start", description="Запуск")]
    )

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
