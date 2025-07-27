import requests
import bs4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os
import sqlite3
import math

user_orders = {}
last_messages = {}
user_payments = {}
awaiting_address = {}
awaiting_budget = {}
user_started = set()

DB_FILE = "gold_data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gold (
            id INTEGER PRIMARY KEY,
            last_price INTEGER
        )
    ''')
    conn.commit()
    conn.close()


TOKEN = "8452996336:AAHq1z8lhzUj-_Ow4EX-BcFx_cCEo4AhmVs"

def gold_price():
    try:
        url = 'https://www.tgju.org'
        response = requests.get(url, timeout=5)
        soup = bs4.BeautifulSoup(response.text, 'html.parser')
        prices = soup.select(".info-price")
        price = prices[3].get_text()
        cleaned = price.replace(",", "")
        number = int(cleaned)
        n = int(number / 10)  # به تومان
        return n
    except:
        return None

def format_price_farsi(number):
    return f"{number:,}".replace(",", "٬")

def get_last_price():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT last_price FROM gold WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_last_price(price):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO gold (id, last_price) VALUES (1, ?)", (price,))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    old_msg_id = last_messages.get(user_id)

    if user_id in awaiting_address:
        sent_msg = await update.message.reply_text("📬 شما در حال ارسال آدرس سفارش هستید. لطفاً ابتدا آدرس را وارد کنید.")
        last_messages[user_id] = sent_msg.message_id
        return

    if old_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_msg_id)
        except:
            pass
    # حذف همه پیام‌های فعال قبلی
    for uid, msg_id in list(last_messages.items()):
        if uid == user_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except:
                pass
            del last_messages[uid]

    keyboard = [
        [InlineKeyboardButton("📊 قیمت طلا", callback_data="gold_price")],
        [InlineKeyboardButton("🪙 قلک طلا", callback_data="buy_piggy")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_msg = await update.message.reply_text("سلام! یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=reply_markup)
    last_messages[user_id] = sent_msg.message_id
    user_started.add(user_id)
from telegram import CallbackQuery

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    old_msg_id = last_messages.get(user_id)
    if old_msg_id and old_msg_id != query.message.message_id:
        try:
            await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
        except:
            pass

    if query.data == "gold_price":
        # اصلاح وزن‌ها با مقادیر صحیح (بر حسب کیلوگرم)
        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }
        current_price = gold_price()
        if current_price is None:
            await query.edit_message_text("❌ خطا در دریافت قیمت طلا. لطفاً بعداً امتحان کن.")
            return

        last_price = get_last_price()
        save_last_price(current_price)
        formatted = format_price_farsi(current_price)

        if last_price:
            diff = current_price - last_price
            if diff > 0:
                emoji = "🔺"
                status = f"⬆️ افزایش {format_price_farsi(diff)} تومان"
            elif diff < 0:
                emoji = "🔻"
                status = f"⬇️ کاهش {format_price_farsi(abs(diff))} تومان"
            else:
                emoji = "⏸️"
                status = "بدون تغییر نسبت به آخرین بار"
        else:
            emoji = "📊"
            status = "اولین بار بررسی قیمت"

        msg = (
            f"📈 <b>قیمت لحظه‌ای طلا (۱۸ عیار)</b>\n\n"
            f"{emoji} <b>{formatted} تومان</b>\n"
            f"{status}"
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=reply_markup)
    elif query.data == "buy_piggy":
        # مرحله اول: نمایش دکمه‌های انتخاب زیر
        buttons = [
            [InlineKeyboardButton("📄 مشاهده قیمت‌ها", callback_data="view_prices")],
            [InlineKeyboardButton("💡 پیشنهاد بر اساس بودجه شما", callback_data="suggest_budget")],
            [InlineKeyboardButton("🛒 خرید قلک", callback_data="start_purchase")]
        ]
        if user_id in user_orders and user_orders[user_id]:
            buttons.append([InlineKeyboardButton("🧾 مشاهده سفارش فعلی", callback_data="view_invoice")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)
    elif query.data == "suggest_budget":
        awaiting_budget[user_id] = True
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="🧮 لطفاً بودجه‌ات رو بر حسب تومان وارد کن "
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "view_prices":
        gold = gold_price()
        if gold is None:
            await query.edit_message_text("❌ خطا در دریافت قیمت طلا.")
            return

        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }

        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }

        lines = []
        for key in weights:
            weight = weights[key]
            label = labels[key]
            price = int(round(((weight * 1.19) * gold) / 1000) * 1000)
            price_str = format_price_farsi(price)
            lines.append(f"• {label}: {price_str} تومان")

        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="buy_piggy")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("💰 قیمت قلک‌ها:\n\n" + "\n".join(lines), reply_markup=reply_markup)
    elif query.data == "start_purchase":
        gold = gold_price()
        if gold is None:
            await query.edit_message_text("❌ خطا در دریافت قیمت طلا.")
            return

        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }

        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }

        buttons = []
        for key in weights:
            weight = weights[key]
            label = labels[key]
            price = int(round(((weight * 1.19) * gold) / 1000) * 1000)
            price_str = format_price_farsi(price)
            buttons.append([InlineKeyboardButton(f"➕ {label} - {price_str} تومان", callback_data=key)])

        buttons.append([InlineKeyboardButton("🧾 مشاهده فاکتور", callback_data="view_invoice")])
        buttons.append([InlineKeyboardButton("🗑 پاک کردن سبد خرید", callback_data="clear_cart")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("مدل مورد نظر قلک طلا رو انتخاب کن:", reply_markup=reply_markup)
    elif query.data.startswith("item_"):
        if user_id not in user_orders:
            user_orders[user_id] = {}
        user_orders[user_id][query.data] = user_orders[user_id].get(query.data, 0) + 1

        # اصلاح وزن‌ها بر حسب گرم
        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }
        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }
        weight = weights.get(query.data)
        label = labels.get(query.data)
        gold = gold_price()
        if gold is None:
            await query.edit_message_text("❌ خطا در دریافت قیمت طلا.")
            return
        raw_price = int((weight * 1.19) * gold)
        final_price = int(round(raw_price / 1000) * 1000)
        formatted = format_price_farsi(final_price)
        await query.answer("به سبد خرید اضافه شد ✅", show_alert=False)
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=(
                f"💰 <b>{label}</b>\n\n"
                f"🔢 وزن کل با اجرت: {weight * 1.19:.3f} گرم\n"
                f"💵 قیمت نهایی: <b>{formatted} تومان</b>"
            ),
            parse_mode="HTML"
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "view_invoice":
        if user_id not in user_orders or not user_orders[user_id]:
            await query.edit_message_text("سبد خرید شما خالی است.")
            return

        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass

        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }
        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }
        gold = gold_price()
        if gold is None:
            await query.edit_message_text("❌ خطا در دریافت قیمت طلا.")
            return

        total = 0
        lines = []
        keyboard = []
        for key, count in user_orders[user_id].items():
            weight = weights[key]
            label = labels[key]
            raw_price = (weight * 1.19) * gold
            final_price = int(round(raw_price / 1000) * 1000)
            total += final_price * count
            lines.append(f"{label} × {count} = {format_price_farsi(final_price * count)} تومان")
            keyboard.append([InlineKeyboardButton(f"❌ حذف {label}", callback_data=f"remove_{key}")])
        keyboard.append([InlineKeyboardButton("✅ ثبت سفارش", callback_data="submit_order")])
        keyboard.append([InlineKeyboardButton("❌ لغو سفارش فعلی", callback_data="cancel_order")])

        total_formatted = format_price_farsi(total)
        lines.append("\n💵 <b>مبلغ کل: " + total_formatted + " تومان</b>")
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "clear_cart":
        user_orders[user_id] = {}
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="🗑 سبد خرید با موفقیت پاک شد."
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data.startswith("remove_"):
        item_key = query.data.replace("remove_", "")
        if user_id in user_orders and item_key in user_orders[user_id]:
            del user_orders[user_id][item_key]
        await query.answer("✅ حذف شد")
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="مورد حذف شد. برای مشاهده فاکتور جدید، دوباره دکمه فاکتور را بزنید."
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("📊 قیمت طلا", callback_data="gold_price")],
            [InlineKeyboardButton("🪙 قلک طلا", callback_data="buy_piggy")]
        ]
        if user_id in user_orders and user_orders[user_id]:
            keyboard.append([InlineKeyboardButton("🧾 مشاهده سفارش فعلی", callback_data="view_invoice")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("سلام! یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=reply_markup)
    elif query.data == "submit_order":
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        keyboard = [[InlineKeyboardButton("📤 ارسال فیش پرداخت", callback_data="send_receipt")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="✅ سفارش شما آماده است.\nبرای تکمیل خرید، فیش پرداخت خود را ارسال کنید.",
            reply_markup=reply_markup
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "send_receipt":
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="💳 لطفاً مبلغ فاکتور را به شماره کارت زیر واریز کنید:\n\n"
                 "<b>6219 8619 1416 7779</b>\n"
                 "به نام مهدی عموزاده آرائی\n\n"
                 "سپس عکس فیش پرداخت یا متن واریز را ارسال کنید.",
            parse_mode="HTML"
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "cancel_order":
        user_orders[user_id] = {}
        # حذف پیام قبلی
        old_msg_id = last_messages.get(user_id)
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=query.message.chat.id, message_id=old_msg_id)
            except:
                pass
        sent_msg = await context.bot.send_message(
            chat_id=query.message.chat.id,
            text="❌ سفارش فعلی لغو شد."
        )
        last_messages[user_id] = sent_msg.message_id
    elif query.data == "restart":
        keyboard = [
            [InlineKeyboardButton("📊 قیمت طلا", callback_data="gold_price")],
            [InlineKeyboardButton("🪙 قلک طلا", callback_data="buy_piggy")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🔄 شروع دوباره:\nیکی از گزینه‌های زیر را انتخاب کن:", reply_markup=reply_markup)

async def gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_price = gold_price()

    if current_price is None:
        await update.message.reply_text("❌ خطا در دریافت قیمت طلا. لطفاً بعداً امتحان کن.")
        return

    last_price = get_last_price()
    save_last_price(current_price)
    formatted = format_price_farsi(current_price)

    # مقایسه
    if last_price:
        diff = current_price - last_price
        if diff > 0:
            emoji = "🔺"
            status = f"⬆️ افزایش {format_price_farsi(diff)} تومان"
        elif diff < 0:
            emoji = "🔻"
            status = f"⬇️ کاهش {format_price_farsi(abs(diff))} تومان"
        else:
            emoji = "⏸️"
            status = "بدون تغییر نسبت به آخرین بار"
    else:
        emoji = "📊"
        status = "اولین بار بررسی قیمت"

    msg = (
        f"📈 <b>قیمت لحظه‌ای طلا (۱۸ عیار)</b>\n\n"
        f"{emoji} <b>{formatted} تومان</b>\n"
        f"{status}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


# --- هندلر عکس فیش پرداخت ---
from telegram.ext import MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_orders or not user_orders[user_id]:
        sent_msg = await update.message.reply_text("❗️شما هنوز سفارشی ثبت نکرده‌اید.")
        last_messages[user_id] = sent_msg.message_id
        return

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        user_payments[user_id] = {
            "order": user_orders[user_id],
            "file_id": file_id
        }

        admin_chat_id = 7678246038  #آیدی ادمین
        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }
        order_items = user_orders[user_id]
        order_text = "\n".join([f"{labels.get(k, k)} × {v}" for k, v in order_items.items()])
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        await context.bot.send_photo(
            chat_id=admin_chat_id,
            photo=file_id,
            caption=f"📥 سفارش جدید از کاربر {user_mention}:\n\n{order_text}",
            parse_mode="HTML"
        )

        awaiting_address[user_id] = user_payments[user_id]
        sent_msg = await update.message.reply_text("✅ فیش دریافت شد.\n\n📬 لطفاً آدرس پستی و شماره تماس خود را وارد نمایید:")
        last_messages[user_id] = sent_msg.message_id
        # پاک کردن پرداخت پس از دریافت موفق فیش
        user_payments.pop(user_id, None)
    else:
        sent_msg = await update.message.reply_text("لطفاً فیش را به صورت عکس ارسال کنید.")
        last_messages[user_id] = sent_msg.message_id


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # بودجه: اگر کاربر در حالت انتظار بودجه است
    if user_id in awaiting_budget:
        awaiting_budget.pop(user_id)
        text = update.message.text.lower().replace(",", "").replace("تومان", "").strip()
        multiplier = 1
        if "هزار" in text:
            multiplier = 1000
        elif "میلیون" in text:
            multiplier = 1000000
        import re
        match = re.search(r"\d+", text)
        if not match:
            sent_msg = await update.message.reply_text("❌ لطفاً مقدار عددی معتبر وارد کن.")
            last_messages[user_id] = sent_msg.message_id
            return

        amount = int(match.group()) * multiplier

        gold = gold_price()
        if gold is None:
            sent_msg = await update.message.reply_text("❌ خطا در دریافت قیمت طلا.")
            last_messages[user_id] = sent_msg.message_id
            return

        weights = {
            "item_ball_110": 0.110,
            "item_ball_100": 0.100,
            "item_cube_110": 0.110,
            "item_cube_90": 0.090,
            "item_ball_30": 0.030
        }
        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }

        prices = {}
        for key in weights:
            prices[key] = int(round(((weights[key] * 1.19) * gold) / 1000) * 1000)

        sorted_items = sorted(prices.items(), key=lambda x: -x[1])
        result = []
        total = 0
        selected = {}

        for key, price in sorted_items:
            count = amount // price
            if count > 0:
                selected[key] = count
                total += count * price
                amount -= count * price
                result.append(f"{labels[key]} × {count} = {format_price_farsi(count * price)} تومان")

        if not result:
            sent_msg = await update.message.reply_text("❌ با این بودجه امکان خرید هیچ آیتمی وجود ندارد.")
            last_messages[user_id] = sent_msg.message_id
            return

        user_orders[user_id] = selected

        result.append(f"\n💵 مجموع: <b>{format_price_farsi(total)} تومان</b>")
        keyboard = [
            [InlineKeyboardButton("✅ همینو می‌خوام", callback_data="view_invoice")],
            [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_msg = await update.message.reply_text(
            "📊 بر اساس بودجه‌ات پیشنهاد خرید:\n\n" + "\n".join(result),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        last_messages[user_id] = sent_msg.message_id
        return

    if user_id in awaiting_address:
        order_data = awaiting_address.pop(user_id)
        address = update.message.text
        admin_chat_id = 7678246038  # آیدی عددی شما

        # ارسال اطلاعات کامل به مدیر با نام فارسی آیتم‌ها و جمع کل
        labels = {
            "item_ball_110": "گوی ۱۱۰ سوتی",
            "item_ball_100": "گوی ۱۰۰ سوتی",
            "item_cube_110": "مکعب ۱۱۰ سوتی",
            "item_cube_90": "مکعب ۹۰ سوتی",
            "item_ball_30": "گوی ۳۰ سوتی"
        }
        gold = gold_price()
        total = 0
        lines = []
        for key, count in order_data['order'].items():
            label = labels.get(key, key)
            weight = {"item_ball_110": 0.110, "item_ball_100": 0.100, "item_cube_110": 0.110, "item_cube_90": 0.090, "item_ball_30": 0.030}[key]
            final_price = int(round(((weight * 1.19) * gold) / 1000) * 1000)
            lines.append(f"{label} × {count} = {format_price_farsi(final_price * count)} تومان")
            total += final_price * count

        total_formatted = format_price_farsi(total)
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        summary = (
            f"📦 سفارش جدید از کاربر {user_mention}\n\n"
            f"🛍 فاکتور:\n" + "\n".join(lines) +
            f"\n\n💵 مبلغ کل: {total_formatted} تومان\n"
            f"\n📬 آدرس و شماره تماس:\n{address}"
        )
        await context.bot.send_message(chat_id=admin_chat_id, text=summary, parse_mode="HTML")

        sent_msg = await update.message.reply_text("✅ آدرس دریافت شد. سفارش شما ثبت شد. ممنون از خریدتون 💛")
        last_messages[user_id] = sent_msg.message_id
        user_orders[user_id] = {}

if __name__ == '__main__':
    from telegram.ext import CallbackQueryHandler
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gold", gold))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    print("ربات در حال اجراست...")
    app.run_polling()