import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest
from config import config
import db
import ltc
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация базы данных при запуске
async def init_database():
    await db.db.init_pool()
    await db.db.init_db()

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} started the bot")
    welcome_text = (
        "👋 Добро пожаловать в LTC бот!\n"
        "Здесь вы можете пополнить баланс с помощью Litecoin.\n"
        "📌 Каждому пользователю присваивается *постоянный LTC-адрес* для пополнения.\n"
        "Используйте кнопки ниже для управления вашим аккаунтом."
    )
    keyboard = main_menu_keyboard()
    
    # Создаем пользователя в базе если его нет
    try:
        await db.db.create_user_if_not_exists(user_id)
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode='Markdown')
    else:
        try:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=keyboard, parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                # Игнорируем ошибку, если сообщение не изменилось
                pass
            else:
                raise

async def address_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /address"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested address")
    try:
        # Убедимся, что пользователь существует
        await db.db.create_user_if_not_exists(user_id)
        address = await db.db.get_or_create_ltc_address(user_id)
        text = f"""
📋 Ваш постоянный LTC-адрес:
`{address}`

💡 Используйте этот адрес для всех пополнений баланса.
        """
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error showing address for user {user_id}: {e}")
        await update.message.reply_text("❌ Ошибка при получении адреса. Попробуйте позже.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance"""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} requested balance")
    try:
        # Убедимся, что пользователь существует
        await db.db.create_user_if_not_exists(user_id)
        balance = await db.db.get_user_balance(user_id)
        text = f"💼 Ваш текущий баланс: {balance / 100000000:.8f} LTC"
        await update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Error getting balance for user {user_id}: {e}")
        await update.message.reply_text("❌ Ошибка при получении баланса. Попробуйте позже.")

def main_menu_keyboard():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("💰 Мой баланс", callback_data='balance')],
        [InlineKeyboardButton("📥 Мой LTC-адрес", callback_data='deposit')],
        [InlineKeyboardButton("📊 Последние транзакции", callback_data='transactions')],
        [InlineKeyboardButton("🔄 Обновить", callback_data='start')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн-кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    logger.info(f"User {user_id} pressed button: {data}")

    # Убедимся, что пользователь существует
    try:
        await db.db.create_user_if_not_exists(user_id)
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при инициализации пользователя. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )
        return

    if data == 'balance':
        await show_balance(query, user_id)
    elif data == 'deposit':
        await show_deposit_address(query, user_id)
    elif data == 'transactions':
        await show_transactions(query, user_id)
    elif data == 'start':
        await start(update, context)
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
    try:
        balance = await db.db.get_user_balance(user_id)
        text = f"💼 Ваш текущий баланс: {balance / 100000000:.8f} LTC"
        await query.edit_message_text(text=text, reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error showing balance for user {user_id}: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при получении баланса. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )

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
        logger.error(f"Error showing deposit address for user {user_id}: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при получении адреса. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )

async def check_transaction_status(query, address):
    """Проверка статуса транзакции для адреса"""
    try:
        # Получаем транзакции для адреса
        transactions_data = await ltc.ltc_api.get_address_transactions(address)
        
        if not transactions_data or 'data' not in transactions_data:
            await query.edit_message_text(
                text="❌ Не удалось получить информацию о транзакциях.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        transactions = transactions_data['data'].get('list', [])
        
        if not transactions:
            await query.edit_message_text(
                text="📭 На этом адресе еще нет транзакций.",
                reply_markup=main_menu_keyboard()
            )
            return
        
        # Обрабатываем каждую транзакцию
        for tx in transactions:
            tx_hash = tx['hash']
            amount = int(float(tx['amount']) * 100000000)  # Конвертируем в сатоши
            
            # Проверяем статус транзакции
            status, confirmations = await ltc.ltc_api.check_transaction_status(tx_hash)
            
            # Сохраняем/обновляем транзакцию в базе данных
            user_id = query.from_user.id
            await db.db.add_transaction(tx_hash, user_id, amount, address, status)
            
            # Если транзакция подтверждена, зачисляем средства
            if status == 'confirmed':
                await db.db.update_user_balance(user_id, amount)
        
        await query.edit_message_text(
            text="✅ Статус транзакций обновлен. Проверьте баланс.",
            reply_markup=main_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error checking transaction status for address {address}: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при проверке транзакций. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )

async def show_transactions(query, user_id):
    """Показать последние транзакции пользователя"""
    try:
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
    except Exception as e:
        logger.error(f"Error showing transactions for user {user_id}: {e}")
        await query.edit_message_text(
            text="❌ Ошибка при получении транзакций. Попробуйте позже.",
            reply_markup=main_menu_keyboard()
        )

async def check_address_transactions_job(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача для проверки транзакций по адресам"""
    logger.info("Running background transaction check")
    # Здесь можно реализовать периодическую проверку транзакций
    # для всех пользователей в базе данных

async def main():
    # Инициализация приложения бота
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("address", address_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CallbackQueryHandler(handle_button_press))
    
    # Инициализация базы данных перед запуском
    await init_database()
    
    # Запуск бота
    logger.info("Бот запущен...")
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
