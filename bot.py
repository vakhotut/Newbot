import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from config import config
import db
import ltc

# Инициализация базы данных при запуске
async def init_database():
    await db.db.init_pool()
    await db.db.init_db()

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    welcome_text = (
        "👋 Добро пожаловать в LTC бот!\n"
        "Здесь вы можете пополнить баланс с помощью Litecoin.\n"
        "Используйте кнопки ниже для управления вашим аккаунтом."
    )
    keyboard = main_menu_keyboard()
    await update.message.reply_text(welcome_text, reply_markup=keyboard)

def main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("💰 Мой баланс", callback_data='balance')],
        [InlineKeyboardButton("📥 Пополнить баланс", callback_data='deposit')],
        [InlineKeyboardButton("📊 Последние транзакции", callback_data='transactions')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == 'balance':
        await show_balance(query, user_id)
    elif data == 'deposit':
        await show_deposit_address(query, user_id)
    elif data == 'transactions':
        await show_transactions(query, user_id)
    elif data.startswith('check_tx:'):
        txid = data.split(':')[1]
        await check_transaction_status(query, txid)
    elif data.startswith('delete_tx:'):
        txid = data.split(':')[1]
        await delete_transaction(query, txid)
    elif data == 'back_to_main':
        await query.edit_message_text(
            text="Главное меню:",
            reply_markup=main_menu_keyboard()
        )

async def show_balance(query, user_id):
    """Показать баланс пользователя"""
    balance = await db.db.get_user_balance(user_id)
    text = f"💼 Ваш текущий баланс: {balance / 100000000:.8f} LTC"
    await query.edit_message_text(text=text, reply_markup=main_menu_keyboard())

async def show_deposit_address(query, user_id):
    """Показать адрес для пополнения"""
    # Пытаемся получить существующий адрес
    address = await db.db.get_ltc_address(user_id)
    
    if not address:
        # Генерируем новый адрес
        address = await ltc.ltc_api.create_ltc_address()
        if address:
            await db.db.save_ltc_address(user_id, address)
        else:
            await query.edit_message_text(
                text="❌ Ошибка при создании адреса. Попробуйте позже.",
                reply_markup=main_menu_keyboard()
            )
            return

    text = f"""
📥 Для пополнения баланса отправьте LTC на следующий адрес:
`{address}`

💡 После отправки средств используйте кнопку «Проверить транзакцию» для обновления баланса.
    """
    
    # Создаем клавиатуру с кнопками для управления транзакциями
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Проверить транзакции", callback_data=f'check_address:{address}')],
        [InlineKeyboardButton("🗑️ Очистить историю", callback_data='clear_history')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ])
    
    await query.edit_message_text(
        text=text, 
        reply_markup=keyboard, 
        parse_mode='Markdown'
    )

async def check_transaction_status(query, txid):
    """Проверка статуса транзакции"""
    status, confirmations = await ltc.ltc_api.check_transaction_status(txid)
    
    if status == 'confirmed':
        # Получаем информацию о транзакции из базы данных
        transaction = await db.db.get_transaction(txid)
        if transaction:
            # Зачисляем средства на баланс
            await db.db.update_user_balance(transaction['user_id'], transaction['amount'])
            text = f"✅ Транзакция подтверждена! На ваш баланс зачислено {transaction['amount'] / 100000000:.8f} LTC."
        else:
            text = "✅ Транзакция подтверждена, но не найдена в базе данных."
    elif status == 'pending':
        text = f"⏳ Транзакция в обработке. Подтверждений: {confirmations}."
    else:
        text = "❌ Ошибка при проверке транзакции или транзакция не найдена."
    
    await query.edit_message_text(text=text, reply_markup=main_menu_keyboard())

async def delete_transaction(query, txid):
    """Удаление информации о транзакции"""
    await db.db.delete_transaction(txid)
    text = "Информация о транзакции удалена."
    await query.edit_message_text(text=text, reply_markup=main_menu_keyboard())

async def show_transactions(query, user_id):
    """Показать последние транзакции пользователя"""
    transactions = await db.db.get_user_transactions(user_id, limit=5)
    
    if not transactions:
        text = "📝 У вас еще нет транзакций."
    else:
        text = "📊 Последние транзакции:\n\n"
        for tx in transactions:
            status_icon = "✅" if tx['status'] == 'confirmed' else "⏳"
            text += f"{status_icon} {tx['amount'] / 100000000:.8f} LTC - {tx['status']}\n"
            text += f"TXID: {tx['txid'][:10]}...\n\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data='transactions')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ])
    
    await query.edit_message_text(text=text, reply_markup=keyboard)

async def check_address_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка транзакций по адресу (фоновная задача)"""
    # Эта функция может запускаться по расписанию для проверки новых транзакций
    user_id = update.effective_user.id
    address = await db.db.get_ltc_address(user_id)
    
    if address:
        # Проверяем неподтвержденные транзакции
        unconfirmed_txs = await ltc.ltc_api.get_unconfirmed_transactions(address)
        
        if unconfirmed_txs and 'data' in unconfirmed_txs:
            for tx in unconfirmed_txs['data']:
                # Сохраняем информацию о транзакции
                await db.db.add_transaction(
                    txid=tx['hash'],
                    user_id=user_id,
                    amount=tx['amount'],
                    address=address,
                    status='pending'
                )
        
        # Проверяем подтвержденные транзакции
        confirmed_txs = await ltc.ltc_api.get_address_transactions(address)
        if confirmed_txs and 'data' in confirmed_txs:
            for tx in confirmed_txs['data']:
                # Обновляем статус транзакции
                await db.db.add_transaction(
                    txid=tx['hash'],
                    user_id=user_id,
                    amount=tx['amount'],
                    address=address,
                    status='confirmed'
                )
                
                # Если транзакция подтверждена, обновляем баланс
                if tx.get('confirmations', 0) > 0:
                    await db.db.update_user_balance(user_id, tx['amount'])

def main():
    # Инициализация приложения бота
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button_press))
    
    # Инициализация базы данных перед запуском
    application.run_polling(init_database=init_database())

if __name__ == '__main__':
    main()
