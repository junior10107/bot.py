import logging
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import AsyncOpenAI

# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# خواندن توکن‌ها از محیط (برای تست می‌تونی مستقیماً مقدار بذاری)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# وضعیت کاربران: رشته و سبک پاسخ
user_field = {}        # {user_id: "ریاضی" | "تجربی"}
user_style = {}        # {user_id: "ساده" | "مرحله‌به‌مرحله" | "دقیق"}
user_pending_question = {}  # {user_id: "آخرین سؤال منتظر سبک"}

# کیبوردها
field_keyboard = ReplyKeyboardMarkup([["ریاضی", "تجربی"]], resize_keyboard=True)
style_keyboard = ReplyKeyboardMarkup([["ساده", "مرحله‌به‌مرحله", "دقیق"]], resize_keyboard=True)

# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام 👋\n\n"
        "من ربات پاسخگوی فیزیک دهم هستم 📘\n"
        "اول رشته‌ات رو مشخص کن:",
        reply_markup=field_keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = (update.message.text or "").strip()

    # ثبت رشته
    if text in ["ریاضی", "تجربی"]:
        user_field[user_id] = text
        await update.message.reply_text(
            f"✅ رشته {text} ثبت شد.\n\nحالا سبک پاسخ رو انتخاب کن:",
            reply_markup=style_keyboard
        )
        return

    # ثبت سبک پاسخ
    if text in ["ساده", "مرحله‌به‌مرحله", "دقیق"]:
        user_style[user_id] = text

        # اگر سوال معوق داریم، هم‌اکنون پاسخ بده
        pending = user_pending_question.get(user_id)
        if pending:
            await update.message.reply_text("✏️ در حال آماده‌سازی پاسخ بر اساس سبک انتخابی...")
            answer = await ask_ai(pending, user_field.get(user_id), user_style.get(user_id))
            user_pending_question.pop(user_id, None)
            await update.message.reply_text(answer, reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text(
                "✅ سبک پاسخ ثبت شد. حالا سوالت رو بپرس.",
                reply_markup=ReplyKeyboardRemove()
            )
        return

    # اگر رشته مشخص نشده
    if user_id not in user_field:
        await update.message.reply_text("⚠️ لطفاً اول رشته‌ات رو مشخص کن (ریاضی یا تجربی).", reply_markup=field_keyboard)
        return

    # اگر سبک پاسخ مشخص نشده، سوال را نگه داریم و سبک بگیریم
    if user_id not in user_style:
        user_pending_question[user_id] = text
        await update.message.reply_text(
            "سبک پاسخ رو انتخاب کن تا دقیقاً همون‌طور جواب بدم:",
            reply_markup=style_keyboard
        )
        return

    # همه‌چیز آماده: پاسخ بده
    await update.message.reply_text("✏️ در حال فکر کردن به پاسخ...")
    answer = await ask_ai(text, user_field[user_id], user_style[user_id])
    await update.message.reply_text(answer)

def build_prompt(question: str, field: str, style: str) -> str:
    if style == "ساده":
        style_rules = """
- جواب کوتاه و ساده بده
- از مثال‌های روزمره استفاده کن
- فرمول فقط در صورت نیاز و خیلی خلاصه
- هیچ تیتر یا Markdown یا متن انگلیسی ننویس
"""
    elif style == "مرحله‌به‌مرحله":
        style_rules = """
- مسئله را به چند گام ساده تقسیم کن
- هر گام را با شماره‌گذاری فارسی (۱، ۲، ۳) توضیح بده
- فرمول‌ها را در همان خط ساده بنویس (مثلاً KE = ½ m v^2)
- هیچ تیتر یا متن انگلیسی اضافه ننویس
"""
    else:  # دقیق
        style_rules = """
- توضیح کامل و تشریحی بده
- فرمول‌ها را واضح و در متن ساده بنویس
- مثال عددی هم حل کن
- در پایان یک جمع‌بندی کوتاه بده
- هیچ Markdown یا متن انگلیسی ننویس
"""

    prompt = f"""
تو یک دبیر حرفه‌ای فیزیک دهم هستی.
رشته دانش‌آموز: {field}
سبک پاسخ: {style}

قوانین پاسخ:
{style_rules}

سوال:
{question}
"""
    return prompt


async def ask_ai(question: str, field: str, style: str) -> str:
    prompt = build_prompt(question, field, style)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "تو یک دبیر فیزیک دهم هستی."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()  # حلقه رویداد را خودش مدیریت می‌کند

if __name__ == "__main__":
    main()
