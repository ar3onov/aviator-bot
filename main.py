import os
import logging
import random
import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from pytz import timezone
# Убираем APScheduler, будем пользоваться job_queue из PTB

# Берём токен из переменных окружения
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Environment variable TOKEN is not set")

IMAGE_DIR = "images"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

active_signals = {}
user_stats = {}


def generate_image(text: str, filename: str, color: str):
    img_size = (800, 400)
    img = Image.new("RGB", img_size, (30, 30, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=200
        )
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    x = (img_size[0] - (bbox[2] - bbox[0])) / 2
    y = (img_size[1] - (bbox[3] - bbox[1])) / 2
    draw.text((x, y), text, font=font, fill=color)

    os.makedirs(IMAGE_DIR, exist_ok=True)
    path = os.path.join(IMAGE_DIR, filename)
    img.save(path)
    return path


async def send_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    is_win: bool,
    odd: float,
    signal_msg_id: int,
    extra_msgs: list,
):
    try:
        # Генерируем картинку
        image_text = "WIN" if is_win else "CRASH"
        image_color = "green" if is_win else "red"
        result_path = generate_image(
            image_text, f"result_{datetime.datetime.now().timestamp()}.jpg", image_color
        )

        # Обновляем статистику
        stats = user_stats.setdefault(chat_id, {"wins": 0, "losses": 0})
        if is_win:
            stats["wins"] += 1
        else:
            stats["losses"] += 1

        # Удаляем старые сообщения
        try:
            await context.bot.delete_message(chat_id, signal_msg_id)
            for mid in extra_msgs:
                await context.bot.delete_message(chat_id, mid)
        except Exception:
            pass

        # Отправляем результат
        users_count = random.randint(400, 600)
        caption = (
            f"{'🎉 WIN!✅' if is_win else '❌ LOSE!'}\n"
            f"{odd}x\n"
            f"📊 {users_count} users placed their bets on this signal."
        )
        with open(result_path, "rb") as img:
            await context.bot.send_photo(chat_id=chat_id, photo=img, caption=caption)
    except Exception as e:
        logger.error(f"Error in send_result: {e}")
    finally:
        active_signals.pop(chat_id, None)


async def handle_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id

    if chat_id in active_signals:
        # Если сигнал ещё активен
        msg = await update.message.reply_text(
            "⛔ Please wait for the current signal to finish."
        )
        # Удалим автоматически через 90 секунд
        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(chat_id, msg.message_id), when=90
        )
        return

    # Генерируем новый сигнал
    odd = round(random.uniform(1.5, 10.0), 2)
    is_win = random.randint(1, 13) != 1

    signal_path = generate_image(
        f"{odd}x", f"signal_{datetime.datetime.now().timestamp()}.jpg", "white"
    )
    with open(signal_path, "rb") as img:
        signal_msg = await update.message.reply_photo(
            photo=img, caption="🔴 YOUR SIGNAL\n\n⏳ You have 1 minute to bet"
        )

    active_signals[chat_id] = True

    # Запланировать отправку результата через 90 секунд
    context.job_queue.run_once(
        lambda ctx: ctx.application.create_task(
            send_result(
                ctx,
                chat_id,
                is_win,
                odd,
                signal_msg.message_id,
                [],  # extra_msgs, если нужно
            )
        ),
        when=90,
    )


async def send_daily_stats(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    try:
        for chat_id, stats in user_stats.items():
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "📊 Daily Stats:\n"
                    f"✅ Wins: {stats['wins']}\n"
                    f"❌ Losses: {stats['losses']}"
                ),
            )
        user_stats.clear()
    except Exception as e:
        logger.error(f"Error in send_daily_stats: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton("🎯 Get Signal")]]
    await update.message.reply_text(
        "🚀 AVIATOR BOT 🚀\n\nPress the button below to receive your signal:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)

    app = ApplicationBuilder().token(TOKEN).build()

    # Обработчики команд и сообщений
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r"^🎯 Get Signal$"), handle_signal))

    # Ежедневная отправка статистики в 09:00 Asia/Kolkata
    app.job_queue.run_daily(
        send_daily_stats,
        time=datetime.time(hour=9, minute=0, tzinfo=timezone("Asia/Kolkata")),
    )

    # Запуск бота (PTB сам запускает asyncio loop)
    app.run_polling()


if __name__ == "__main__":
    main()
