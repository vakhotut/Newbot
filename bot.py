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
        "📌 Каждому пользователю присваивается *постоянный LTC-адрес* для пополнения.\n"
        "Используйте кнопки ниже для управления вашим аккаунтом."
    )
    keyboard = main_menu_keyboard()
    await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode='Markdown')

async def address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /address"""
    user_id = update.effective_user.id
    try:
        address = await db.db.get_or_create_ltc_address(user_id)
        text = f"""
📋 Ваш постоянный LTC-адрес:
`{address}`

💡 Используйте этот адрес для всех пополнений баланса.
        """
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        print(f"Error showing address: {e}")
        await update.message.reply_text("❌ Ошибка при получении адреса. Попробуйте позже.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance"""
    user_id = update.effective_user.id
    balance = await db.db.get_user_balance(user_id)
    text = f"💼 Ваш текущий баланс: {balance / 100000000:.8f} LTC"
    await update.message.reply_text(text)

def main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("💰 Мой баланс", callback_data='balance')],
        [InlineKeyboardButton("📥 Мой LTC-адрес", callback_data='deposit')],
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
    """Показывает единственный LTC-адрес для пополнения"""
    try:
        # Получаем или создаем адрес
        address = await db.db.get_or_create_ltc_address(user_id)
        
        text = f"""
📥 Для пополнения баланса отправьте LTC на следующий адрес:
`{address}`

💡 После отправки средств используйте кнопку «Проверить транзакцию» для обновления баланса.

⚠️ *Это ваш постоянный адрес для пополнения. Используйте его для всех депозитов.*
        """
        
        # Создаем клавиатуру с кнопками для этого адреса
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Проверить транзакции", callback_data=f'check_tx:{address}')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
        ])
        
        await query.edit_message_text(
            text=text, 
            reply_markup=keyboard, 
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Error showing deposit address: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при получении адреса. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
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

async def check_address_transactions_job(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача для проверки транзакций по адресам"""
    # Эта функция будет периодически проверять транзакции для всех пользователей
    # В реальном приложении нужно реализовать логику получения всех пользователей
    # и проверки транзакций для их адресов
    
    # Пример реализации:
    # 1. Получить всех пользователей с адресами
    # 2. Для каждого адреса проверить транзакции через API
    # 3. Обновить статусы транзакций и балансы пользователей
    pass

def main():
    # Инициализация приложения бота
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("address", address_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(handle_button_press))
    
    # Инициализация базы данных перед запуском
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_database())
    
    # Запуск бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
