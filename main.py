import logging
import random
import datetime
import os
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import timezone

TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN_HERE'
IMAGE_DIR = 'images'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

active_signals = {}
user_stats = {}


def generate_image(text: str, filename: str, color: str):
    img_size = (800, 400)
    img = Image.new('RGB', img_size, color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    x = (img_size[0] - (bbox[2] - bbox[0])) / 2
    y = (img_size[1] - (bbox[3] - bbox[1])) / 2

    draw.text((x, y), text, font=font, fill=color)

    os.makedirs(IMAGE_DIR, exist_ok=True)
    filepath = os.path.join(IMAGE_DIR, filename)
    img.save(filepath)
    return filepath


async def send_result(context: ContextTypes.DEFAULT_TYPE, chat_id: int, is_win: bool, odd: float, signal_msg_id: int, extra_msgs: list):
    try:
        image_text = "WIN" if is_win else "CRASH"
        image_color = "green" if is_win else "red"
        result_image = generate_image(image_text, f"result_{datetime.datetime.now().timestamp()}.jpg", image_color)

        if chat_id not in user_stats:
            user_stats[chat_id] = {'wins': 0, 'losses': 0}

        if is_win:
            user_stats[chat_id]['wins'] += 1
        else:
            user_stats[chat_id]['losses'] += 1

        # Удаляем сообщение "⛔ Please wait..." и лишние сообщения
        try:
            await context.bot.delete_message(chat_id, signal_msg_id)
            for msg_id in extra_msgs:
                await context.bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

        users_count = random.randint(400, 600)
        caption = (
            f"{'🎉 WIN!✅' if is_win else '❌ LOSE!'}\n"
            f"{odd}x\n"
            f"📊 {users_count} users placed their bets on this signal."
        )

        with open(result_image, 'rb') as img:
            await context.bot.send_photo(chat_id=chat_id, photo=img, caption=caption)

    except Exception as e:
        logger.error(f"Result error: {e}")
    finally:
        active_signals.pop(chat_id, None)


async def handle_signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.message.chat.id
        message_ids_to_delete = []

        if chat_id in active_signals:
            msg = await update.message.reply_text("⛔ Please wait for the current signal to finish.")
            message_ids_to_delete.append(msg.message_id)
            return

        odd = round(random.uniform(1.5, 10.0), 2)
        is_win = random.randint(1, 13) != 1

        signal_image = generate_image(f"{odd}x", f"signal_{datetime.datetime.now().timestamp()}.jpg", "white")

        with open(signal_image, 'rb') as img:
            signal_msg = await update.message.reply_photo(
                photo=img,
                caption="🔴 YOUR SIGNAL\n\n⏳ You have 1 minute to bet"
            )

        active_signals[chat_id] = True

        # Запланировать вывод результата через 1.5 минуты
        scheduler.add_job(
            send_result,
            'date',
            run_date=datetime.datetime.now() + datetime.timedelta(minutes=1.5),
            args=[context, chat_id, is_win, odd, signal_msg.message_id, message_ids_to_delete]
        )

    except Exception as e:
        logger.error(f"Error in handle_signal: {e}")


async def send_daily_stats(bot):
    try:
        for chat_id, stats in user_stats.items():
            msg = (
                "📊 Daily Stats:\n"
                f"✅ Wins: {stats['wins']}\n"
                f"❌ Losses: {stats['losses']}"
            )
            await bot.send_message(chat_id=chat_id, text=msg)
        user_stats.clear()
    except Exception as e:
        logger.error(f"Error sending daily stats: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🎯 Get Signal")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🚀 AVIATOR BOT 🚀\n\nPress the button below to receive your signal:",
        reply_markup=reply_markup
    )


def main():
    os.makedirs(IMAGE_DIR, exist_ok=True)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r'^🎯 Get Signal$'), handle_signal))

    india_tz = timezone('Asia/Kolkata')
    scheduler.configure(timezone=india_tz)
    scheduler.start()

    scheduler.add_job(
        send_daily_stats,
        'cron',
        hour=9, minute=0,
        args=[app.bot]
    )

    # Запускаем бота (без asyncio.run!)
    app.run_polling()


if __name__ == '__main__':
    main()
