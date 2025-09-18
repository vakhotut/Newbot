import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
import aioschedule
import os
import time
from aiogram.utils.exceptions import RetryAfter

from database import Database
from blockchain import BlockchainManager
from keyboards import (
    main_menu_keyboard,
    tbilisi_menu_keyboard,
    districts_keyboard,
    delivery_type_keyboard,
    confirmation_keyboard,
    invoice_keyboard
)
from config import BOT_TOKEN, BLOCKCYPHER_TOKEN, LITECOIN_API_KEY, ADMIN_USER_ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database()
blockchain = BlockchainManager(BLOCKCYPHER_TOKEN, LITECOIN_API_KEY)

class UserStates(StatesGroup):
    waiting_for_topup_amount = State()
    waiting_for_product_selection = State()
    waiting_for_district_selection = State()
    waiting_for_delivery_type = State()
    waiting_for_confirmation = State()

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if not await db.user_exists(user_id):
        await db.create_user(user_id)
    
    await message.answer(
        "Добро пожаловать в главное меню!",
        reply_markup=main_menu_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data == 'tbilisi')
async def process_tbilisi(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите товар:",
        reply_markup=tbilisi_menu_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data.startswith('product_'))
async def process_product_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    product_id = callback_query.data.split('_')[1]
    
    async with state.proxy() as data:
        data['product_id'] = product_id
    
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите район:",
        reply_markup=districts_keyboard()
    )
    await UserStates.waiting_for_district_selection.set()

@dp.callback_query_handler(lambda c: c.data.startswith('district_'), state=UserStates.waiting_for_district_selection)
async def process_district_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    district = callback_query.data.split('_')[1]
    
    async with state.proxy() as data:
        data['district'] = district
    
    await bot.send_message(
        callback_query.from_user.id,
        "Выберите тип подъезда:",
        reply_markup=delivery_type_keyboard()
    )
    await UserStates.waiting_for_delivery_type.set()

@dp.callback_query_handler(lambda c: c.data.startswith('delivery_'), state=UserStates.waiting_for_delivery_type)
async def process_delivery_type(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    delivery_type = callback_query.data.split('_')[1]
    
    async with state.proxy() as data:
        data['delivery_type'] = delivery_type
        product_id = data['product_id']
        district = data['district']
    
    product = await db.get_product(product_id)
    
    confirmation_text = (
        f"Подтвердите заказ:\n"
        f"Товар: {product['name']}\n"
        f"Цена: {product['price']} USD\n"
        f"Район: {district}\n"
        f"Тип подъезда: {delivery_type}"
    )
    
    await bot.send_message(
        callback_query.from_user.id,
        confirmation_text,
        reply_markup=confirmation_keyboard()
    )
    await UserStates.waiting_for_confirmation.set()

@dp.callback_query_handler(lambda c: c.data == 'confirm_yes', state=UserStates.waiting_for_confirmation)
async def process_confirmation_yes(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    
    async with state.proxy() as data:
        product_id = data['product_id']
        district = data['district']
        delivery_type = data['delivery_type']
    
    user_id = callback_query.from_user.id
    product = await db.get_product(product_id)
    
    invoice = await blockchain.create_invoice(user_id, product['price'])
    await db.create_invoice(
        user_id=user_id,
        amount=product['price'],
        address=invoice['address'],
        crypto=invoice['crypto'],
        invoice_id=invoice['invoice_id']
    )
    
    qr_code = await blockchain.generate_qr_code(invoice['address'], product['price'])
    
    invoice_text = (
        f"Оплатите {product['price']} LTC на адрес:\n"
        f"`{invoice['address']}`\n\n"
        f"После оплаты нажмите 'Проверить транзакцию'"
    )
    
    await bot.send_photo(
        callback_query.from_user.id,
        photo=qr_code,
        caption=invoice_text,
        reply_markup=invoice_keyboard(invoice['invoice_id']),
        parse_mode='Markdown'
    )
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'balance')
async def process_balance(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    user_id = callback_query.from_user.id
    balance = await db.get_balance(user_id)
    
    await bot.send_message(
        user_id,
        f"Ваш текущий баланс: {balance} USD\n\n"
        "Введите сумму для пополнения (в USD):"
    )
    await UserStates.waiting_for_topup_amount.set()

@dp.message_handler(state=UserStates.waiting_for_topup_amount)
async def process_topup_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        
        user_id = message.from_user.id
        invoice = await blockchain.create_invoice(user_id, amount)
        await db.create_invoice(
            user_id=user_id,
            amount=amount,
            address=invoice['address'],
            crypto=invoice['crypto'],
            invoice_id=invoice['invoice_id']
        )
        
        qr_code = await blockchain.generate_qr_code(invoice['address'], amount)
        
        invoice_text = (
            f"Оплатите {amount} LTC на адрес:\n"
            f"`{invoice['address']}`\n\n"
            f"После оплаты нажмите 'Проверить транзакцию'"
        )
        
        await bot.send_photo(
            message.chat.id,
            photo=qr_code,
            caption=invoice_text,
            reply_markup=invoice_keyboard(invoice['invoice_id']),
            parse_mode='Markdown'
        )
        await state.finish()
    
    except ValueError:
        await message.answer("Пожалуйста, введите корректную сумму числами:")

@dp.callback_query_handler(lambda c: c.data.startswith('check_tx_'))
async def check_transaction(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    invoice_id = callback_query.data.split('_')[2]
    
    try:
        invoice = await db.get_invoice(invoice_id)
        if not invoice:
            await bot.send_message(callback_query.from_user.id, "Инвойс не найден")
            return
        
        limits = await blockchain.check_api_limits()
        if limits and limits['remaining'] < 5:
            await bot.send_message(
                callback_query.from_user.id,
                f"⚠️ Лимиты API почти исчерпаны. Осталось {limits['remaining']} запросов в час.\n"
                "Возможны задержки в проверке транзакций."
            )
        
        tx_status = await blockchain.check_transaction(invoice['address'], invoice['amount'])
        
        if tx_status is None:
            await bot.send_message(
                callback_query.from_user.id,
                "Ошибка при проверке транзакции. Попробуйте позже."
            )
            return
        
        if tx_status['confirmed']:
            await db.update_invoice_status(invoice_id, 'completed')
            await db.update_balance(invoice['user_id'], invoice['amount'])
            await bot.send_message(
                callback_query.from_user.id,
                f"✅ Транзакция подтверждена! Баланс пополнен на {invoice['amount']} USD"
            )
        else:
            confirmations_text = f"Подтверждений: {tx_status['confirmations']}/4" if tx_status['confirmations'] > 0 else "Транзакция не найдена"
            await bot.send_message(
                callback_query.from_user.id,
                f"⏳ Транзакция еще не подтверждена. {confirmations_text}\n"
                f"Получено: {tx_status['amount_received']} LTC"
            )
    
    except Exception as e:
        print(f"Error in check_transaction: {e}")
        await bot.send_message(
            callback_query.from_user.id,
            "Произошла ошибка при проверке транзакции. Попробуйте позже."
        )

@dp.callback_query_handler(lambda c: c.data.startswith('cancel_tx_'))
async def cancel_transaction(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    invoice_id = callback_query.data.split('_')[2]
    
    await db.update_invoice_status(invoice_id, 'cancelled')
    await bot.send_message(callback_query.from_user.id, "Пополнение отменено")

@dp.callback_query_handler(lambda c: c.data == 'purchase_history')
async def show_purchase_history(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    user_id = callback_query.from_user.id
    
    purchases = await db.get_purchase_history(user_id)
    if not purchases:
        await bot.send_message(user_id, "История покупок пуста")
        return
    
    history_text = "История покупок:\n\n"
    for purchase in purchases:
        history_text += f"Дата: {purchase['date']}\nСумма: {purchase['amount']} USD\nТовар: {purchase['product']}\n\n"
    
    await bot.send_message(user_id, history_text)

@dp.errors_handler(exception=RetryAfter)
async def rate_limit_exceeded(update, exception):
    print(f"Telegram rate limit exceeded. Retry after {exception.timeout} seconds")
    return True

@dp.message_handler(commands=['limits'])
async def check_limits(message: types.Message):
    limits = await blockchain.check_api_limits()
    if limits:
        await message.answer(
            f"Лимиты BlockCypher API:\n"
            f"• Лимит в час: {limits['limit']}\n"
            f"• Использовано: {limits['used']}\n"
            f"• Осталось: {limits['remaining']}\n"
            f"• Использовано: {limits['used']/limits['limit']*100:.1f}%"
        )
    else:
        await message.answer("Не удалось получить информацию о лимитах API")

async def check_pending_transactions():
    try:
        limits = await blockchain.check_api_limits()
        if limits and limits['remaining'] < 20:
            print(f"Warning: Only {limits['remaining']} API calls remaining. Skipping batch processing.")
            return
        
        pending_invoices = await db.get_pending_invoices()
        for invoice in pending_invoices:
            limits = await blockchain.check_api_limits()
            if limits and limits['remaining'] < 5:
                print("API limit almost exceeded. Stopping transaction checks.")
                break
                
            tx_status = await blockchain.check_transaction(invoice['address'], invoice['amount'])
            
            if tx_status and tx_status['confirmed']:
                await db.update_invoice_status(invoice['id'], 'completed')
                await db.update_balance(invoice['user_id'], invoice['amount'])
                
                await bot.send_message(
                    invoice['user_id'],
                    f"Транзакция подтверждена! Баланс пополнен на {invoice['amount']} USD"
                )
    
    except Exception as e:
        print(f"Error in check_pending_transactions: {e}")

async def check_api_limits_notification():
    limits = await blockchain.check_api_limits()
    if limits and limits['remaining'] < 50:
        if ADMIN_USER_ID:
            await bot.send_message(
                ADMIN_USER_ID,
                f"⚠️ Внимание: Осталось только {limits['remaining']} "
                f"запросов к BlockCypher API в этом часе.\n"
                f"Использовано: {limits['used']}/{limits['limit']} "
                f"({limits['used']/limits['limit']*100:.1f}%)"
            )

async def scheduler():
    aioschedule.every(5).minutes.do(check_pending_transactions)
    aioschedule.every(1).hours.do(check_api_limits_notification)
    
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

async def on_startup(dp):
    await db.connect()
    asyncio.create_task(scheduler())

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
