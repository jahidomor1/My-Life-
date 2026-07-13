#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🤖 Enterprise SaaS Telegram Bot Hosting System (v8.1.0)
🔒 Features: Lifetime Store Bots, Dual Payment, File Box Viewer for Admin, Multi Force Join, Store Manager, Broadcast.
"""

import os
import re
import logging
import subprocess
import sys
import asyncio
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# =============== কনফিগারেশন ===============
MAIN_BOT_TOKEN = '8173353411:AAF5XX9iOLg-pR7v_PZ2ka84c5KHOHTfnqk'
SUPER_ADMIN = 8257820157

# =============== পাথ সেটআপ ===============
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'host_data'
DB_DIR = DATA_DIR / 'user_databases'
USER_BOTS_DIR = DATA_DIR / 'hosted_files'
PREMIUM_STORE_DIR = DATA_DIR / 'premium_store_files'

for p in [DATA_DIR, DB_DIR, USER_BOTS_DIR, PREMIUM_STORE_DIR]:
    p.mkdir(exist_ok=True, parents=True)

MASTER_DB_PATH = DATA_DIR / 'master_system.db'

# =============== লগিং সিস্টেম ===============
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# =============== 🌈 বাটন স্টাইল ও কালার প্যাচিং কোড ===============
_old_inline_dict = InlineKeyboardButton.to_dict
def _new_inline_dict(self, *args, **kwargs):
    d = _old_inline_dict(self, *args, **kwargs)
    if hasattr(self, 'style'): d['style'] = self.style
    if hasattr(self, 'custom_copy_text') and self.custom_copy_text:
        d['copy_text'] = {'text': str(self.custom_copy_text)}
        if 'callback_data' in d: del d['callback_data']
    return d
InlineKeyboardButton.to_dict = _new_inline_dict

_old_kb_dict = KeyboardButton.to_dict
def _new_kb_dict(self, *args, **kwargs):
    d = _old_kb_dict(self, *args, **kwargs)
    if hasattr(self, 'style'): d['style'] = self.style
    return d
KeyboardButton.to_dict = _new_kb_dict

def ibtn(text, callback_data=None, url=None, style=None, copy_text_str=None):
    kwargs = {'text': text}
    if copy_text_str: kwargs['custom_copy_text'] = copy_text_str
    else:
        if callback_data: kwargs['callback_data'] = callback_data
        if url: kwargs['url'] = url
    btn = InlineKeyboardButton(**kwargs)
    if style: object.__setattr__(btn, 'style', style)
    return btn

def rbtn(text, style=None):
    btn = KeyboardButton(text=text)
    if style: object.__setattr__(btn, 'style', style)
    return btn

# =============== MASTER DATABASE SETUP ===============
def init_master_db():
    conn = sqlite3.connect(MASTER_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, name TEXT, 
        balance REAL DEFAULT 0.0, premium_until TEXT, is_admin INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS bots (
        bot_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
        bot_name TEXT, token TEXT UNIQUE, status TEXT DEFAULT 'inactive', is_premium_store INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS purchased_store_bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, store_id INTEGER, UNIQUE(user_id, store_id)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
        code TEXT PRIMARY KEY, amount REAL, max_uses INTEGER, used_count INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
        plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, days INTEGER, price REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS premium_store (
        store_id INTEGER PRIMARY KEY AUTOINCREMENT, bot_name TEXT, price REAL, py_file TEXT, req_file TEXT, ask_group_id INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS force_channels (
        channel_username TEXT PRIMARY KEY
    )''')
    
    default_settings = [
        ('premium_system', 'ON'), ('bkash', 'ON'), ('nagod', 'ON'), ('binance', 'ON'), 
        ('bkash_number', 'Not Set'), ('nagod_number', 'Not Set'), ('binance_uid', 'Not Set'),
        ('store_mode', 'PAID') # New feature: PAID or FREE store
    ]
    for key, val in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        
    conn.commit()
    conn.close()

init_master_db()

def get_db_conn():
    return sqlite3.connect(MASTER_DB_PATH)

def get_setting(key: str) -> str:
    conn = get_db_conn()
    res = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    conn.close()
    return res[0] if res else ""

def set_setting(key: str, value: str):
    conn = get_db_conn()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def is_user_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN: return True
    conn = get_db_conn()
    res = conn.execute('SELECT is_admin FROM users WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    return bool(res and res[0])

running_processes = {}
user_states = {}

async def force_join_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if is_user_admin(user_id): 
        return True 
        
    conn = get_db_conn()
    channels = [r[0] for r in conn.execute('SELECT channel_username FROM force_channels').fetchall()]
    conn.close()
    
    if not channels: return True
    
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ['left', 'kicked']: raise Exception()
        except:
            ch_list_str = "\n".join([f"📢 {c}" for c in channels])
            if update.message:
                await update.message.reply_text(f"❌ বটটি ব্যবহার করতে আমাদের নিচের চ্যানেলে জয়েন করুন!\n\n{ch_list_str}\n\nজয়েন করার পর আবার /start চাপুন।")
            elif update.callback_query:
                await update.callback_query.message.reply_text(f"❌ বটটি ব্যবহার করতে আমাদের নিচের চ্যানেলে জয়েন করুন!\n\n{ch_list_str}\n\nজয়েন করার পর আবার /start চাপুন।")
            return False
    return True

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db_conn()
    conn.execute('INSERT OR IGNORE INTO users (user_id, username, name) VALUES (?, ?, ?)', (user.id, user.username, user.first_name))
    conn.commit()
    conn.close()

    if not await force_join_check(update, context): return

    keyboard = [
        [rbtn("📥 ফাইল আপলোড করুন", style="primary"), rbtn("🛍️ প্রিমিয়াম বট স্টোর", style="success")],
        [rbtn("📋 আমার বট সমূহ", style="primary"), rbtn("💼 আমার ওয়ালেট", style="success")],
        [rbtn("➕ ডিপোজিট করুন", style="success")]
    ]
    if is_user_admin(user.id):
        keyboard.append([rbtn("👑 অ্যাডমিন প্যানেল", style="danger")])

    await update.message.reply_text(
        f"🤖 *স্বাগতম {user.first_name}!* এটি একটি অ্যাডভান্সড হোস্টিং ও প্রিমিয়াম রেডিমেড বট প্ল্যাটফর্ম।\n"
        f"আপনার নিজস্ব বট রান করতে ফাইল আপলোড করুন অথবা স্টোর থেকে রেডিমেড প্রিমিয়াম বট কিনুন।",
        parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if not await force_join_check(update, context): return

    if text == "⬅️ প্রধান মেনু":
        user_states.pop(user_id, None)
        await start_command(update, context)
        return
    
    elif text == "⬅️ ব্যাক অ্যাডমিন মেনু":
        user_states.pop(user_id, None)
        if is_user_admin(user_id):
            kb = [
                [rbtn("👥 ওল ইউজার", style="primary"), rbtn("⚙️ গেটওয়ে ও মেথড কন্ট্রোল", style="primary")],
                [rbtn("🎫 রিডিম কোড জেনারেটর", style="success"), rbtn("💰 ডাইনামিক প্ল্যান সেটআপ", style="success")],
                [rbtn("📤 প্রিমিয়াম ফাইল আপলোড", style="success"), rbtn("📢 ফোর্স জয়েন চ্যানেল", style="primary")],
                [rbtn("📢 ব্রডকাস্ট মেসেজ", style="primary"), rbtn("➕ অ্যাডমিন যোগ করুন", style="primary")],
                [rbtn("⬅️ প্রধান মেনু", style="danger")]
            ]
            await update.message.reply_text("👑 *স্বাগতম অ্যাডমিন মাস্টার কন্ট্রোলে:*", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    # --- একটিভ স্টেট হ্যান্ডলিং ---
    if user_id in user_states:
        state_data = user_states[user_id]
        current_state = state_data.get('state')
        
        # ব্রডকাস্ট হ্যান্ডলিং (Text)
        if current_state == 'WAITING_BROADCAST' and is_user_admin(user_id):
            conn = get_db_conn()
            users = conn.execute('SELECT user_id FROM users').fetchall()
            conn.close()
            success = 0
            await update.message.reply_text("⏳ ব্রডকাস্ট পাঠানো শুরু হয়েছে, দয়া করে অপেক্ষা করুন...")
            for u in users:
                try:
                    await update.message.copy(chat_id=u[0])
                    success += 1
                    await asyncio.sleep(0.05)
                except: pass
            await update.message.reply_text(f"✅ ব্রডকাস্ট সফলভাবে {success} জন ইউজারকে পাঠানো হয়েছে।")
            user_states.pop(user_id, None)
            return
            
        elif current_state == 'WAITING_NAME':
            bot_name = re.sub(r'[^a-zA-Z0-9]', '', text)
            if not bot_name:
                await update.message.reply_text("❌ নাম বৈধ নয়। আবার ইংরেজি অক্ষরে সুন্দর নাম দিন:")
                return
            user_states[user_id] = {'state': 'WAITING_FILE', 'bot_name': bot_name}
            await update.message.reply_text(f"✅ বটের নাম সংরক্ষিত: `{bot_name}`\nএখন বটের প্রধান পাইথন (.py) ফাইলটি ডকুমেন্ট হিসেবে সেন্ড করুন।", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
            return

        elif current_state == 'INPUT_DEPOSIT_AMOUNT':
            try:
                # বাংলা সংখ্যা কনভার্ট করার জন্য
                bn_to_en = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
                amount_str = text.translate(bn_to_en)
                amount = float(amount_str)
                if amount <= 0: raise ValueError()
                state_data['deposit_amount'] = amount
                state_data['state'] = 'CHOOSE_DEPOSIT_METHOD'
                
                kb = []
                if get_setting('bkash') == 'ON': kb.append([ibtn("বিকাশ (bKash)", callback_data=f"depmeth_bkash", style="success")])
                if get_setting('nagod') == 'ON': kb.append([ibtn("ন নগদ (Nagad)", callback_data=f"depmeth_nagod", style="success")])
                if get_setting('binance') == 'ON': kb.append([ibtn("বাইনান্স (Binance)", callback_data=f"depmeth_binance", style="primary")])
                
                await update.message.reply_text(f"💳 পরিমাণ: *{amount} টাকা*\nডিপোজিট করার মেথডটি সিলেক্ট করুন:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
            except:
                await update.message.reply_text("❌ সঠিক অংক লিখুন (যেমন: 100 বা ১০০):")
            return

        # --- প্রিমিয়াম বট উইজার্ড কনফিগারেশন ---
        elif current_state == 'PREM_WIZ_TOKEN':
            if ":" not in text:
                await update.message.reply_text("❌ ভুল টোকেন ফরমেট! সঠিক বট টোকেনটি দিন:")
                return
            state_data['user_token'] = text
            state_data['state'] = 'PREM_WIZ_ADMIN'
            await update.message.reply_text("👤 এবার আপনার টেলিগ্রাম অ্যাকাউন্ট আইডি (Admin ID) দিন:")
            return

        elif current_state == 'PREM_WIZ_ADMIN':
            if not text.isdigit():
                await update.message.reply_text("❌ আইডি শুধু সংখ্যায় হতে হবে। সঠিক আইডি দিন:")
                return
            state_data['user_admin_id'] = text
            
            if state_data.get('ask_group_id') == 1:
                state_data['state'] = 'PREM_WIZ_GROUP'
                await update.message.reply_text("🆔 এই বটের জন্য আপনার গ্রুপ আইডি (Group ID) টি দিন (যেমন: -10012345678):")
            else:
                state_data['user_group_id'] = "0"
                state_data['state'] = 'PREM_WIZ_CHANNEL'
                await update.message.reply_text("📢 এবার ফোর্স জয়েন ভেরিফিকেশনের জন্য আপনার চ্যানেলের ইউজারনেমটি দিন (যেমন: @mychannel):")
            return

        elif current_state == 'PREM_WIZ_GROUP':
            state_data['user_group_id'] = text
            state_data['state'] = 'PREM_WIZ_CHANNEL'
            await update.message.reply_text("📢 এবার ফোর্স জয়েন ভেরিফিকেশনের জন্য আপনার চ্যানেলের ইউজারনেমটি দিন (যেমন: @mychannel):")
            return

        elif current_state == 'PREM_WIZ_CHANNEL':
            channel_user = text if text.startswith('@') else f"@{text}"
            store_id = state_data['store_id']
            
            conn = get_db_conn()
            store_bot = conn.execute('SELECT bot_name, py_file, req_file FROM premium_store WHERE store_id=?', (store_id,)).fetchone()
            conn.close()
            
            b_name = f"{store_bot[0]}_{user_id}"
            b_dir = USER_BOTS_DIR / f"user_{user_id}_{b_name}"
            b_dir.mkdir(exist_ok=True, parents=True)
            
            src_py = PREMIUM_STORE_DIR / store_bot[1]
            dest_py = b_dir / f"{b_name}.py"
            
            if src_py.exists():
                code = src_py.read_text(encoding='utf-8')
                code = code.replace("BOT_TOKEN_HERE", state_data['user_token'])
                code = code.replace("ADMIN_ID_HERE", state_data['user_admin_id'])
                code = code.replace("GROUP_ID_HERE", state_data.get('user_group_id', '0'))
                code = code.replace("CHANNEL_USERNAME_HERE", channel_user)
                
                custom_db_filename = f"db_user_{user_id}_bot_{b_name}.db"
                fixed_code = f"import sqlite3\nimport os\nos.makedirs('{DB_DIR}', exist_ok=True)\ndef get_isolated_connection(): return sqlite3.connect('{DB_DIR / custom_db_filename}')\n" + code
                dest_py.write_text(fixed_code, encoding='utf-8')
            
            if store_bot[2] and (PREMIUM_STORE_DIR / store_bot[2]).exists():
                shutil.copy(PREMIUM_STORE_DIR / store_bot[2], b_dir / 'requirements.txt')
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(b_dir / 'requirements.txt')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            conn = get_db_conn()
            conn.execute('INSERT OR REPLACE INTO bots (user_id, bot_name, token, is_premium_store) VALUES (?, ?, ?, 1)', (user_id, b_name, state_data['user_token']))
            conn.commit()
            conn.close()
            
            proc = subprocess.Popen(['python3', str(dest_py)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            running_processes[b_name] = proc
            
            conn = get_db_conn()
            conn.execute('UPDATE bots SET status=\'active\' WHERE user_id=? AND bot_name=?', (user_id, b_name))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"🚀 প্রিমিয়াম বট `{b_name}` সফলভাবে কনফিগার হয়েছে এবং রান করা হয়েছে!", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
            user_states.pop(user_id, None)
            return

        elif current_state == 'PREM_ADD_NAME':
            user_states[user_id]['store_name'] = text
            user_states[user_id]['state'] = 'PREM_ADD_PRICE'
            await update.message.reply_text("💵 এই রেডিমেড বটটির মূল্য কত টাকা হবে তা লিখুন (0 লিখলে ফ্রি হবে):")
            return

        elif current_state == 'PREM_ADD_PRICE':
            try:
                bn_to_en = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
                amount_str = text.translate(bn_to_en)
                price = float(amount_str)
                user_states[user_id]['store_price'] = price
                kb = [[ibtn("হ্যাঁ, লাগবে", callback_data="g_req_yes"), ibtn("না, লাগবে না", callback_data="g_req_no")]]
                await update.message.reply_text("👥 এই বটটি কেনার সময় কি ইউজারের থেকে কোনো Group ID ইনপুট নেওয়ার প্রয়োজন আছে?", reply_markup=InlineKeyboardMarkup(kb))
            except:
                await update.message.reply_text("❌ মূল্য অবশ্যই সংখ্যায় হতে হবে। আবার সঠিক মূল্য দিন:")
            return

        elif current_state == 'SET_BKASH':
            set_setting('bkash_number', text)
            user_states.pop(user_id, None)
            await update.message.reply_text("✅ বিকাশ নাম্বার সফলভাবে আপডেট হয়েছে।")
            return

        elif current_state == 'SET_NAGOD':
            set_setting('nagod_number', text)
            user_states.pop(user_id, None)
            await update.message.reply_text("✅ নগদ নাম্বার সফলভাবে আপডেট হয়েছে।")
            return

        elif current_state == 'SET_BINANCE':
            set_setting('binance_uid', text)
            user_states.pop(user_id, None)
            await update.message.reply_text("✅ বাইনান্স UID সফলভাবে আপডেট হয়েছে।")
            return

        elif current_state == 'ADMIN_ADD_PLAN':
            try:
                parsed_text = text.replace('，', ',')
                parts = [p.strip() for p in parsed_text.split(',')]
                if len(parts) == 2:
                    p_days, p_price = int(parts[0]), float(parts[1])
                    p_name = f"{p_days} দিনের প্ল্যান"
                elif len(parts) == 3:
                    p_name, p_days, p_price = parts[0], int(parts[1]), float(parts[2])
                else: raise ValueError()
                conn = get_db_conn()
                conn.execute('INSERT INTO plans (name, days, price) VALUES (?, ?, ?)', (p_name, p_days, p_price))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"🎉 নতুন হোস্টিং প্ল্যান যুক্ত হয়েছে: `{p_name}`")
            except:
                await update.message.reply_text("❌ ফরম্যাট ভুল হয়েছে! উদাহরণ: `30,100`")
            user_states.pop(user_id, None)
            return

        elif current_state == 'INPUT_REDEEM':
            code = text.strip()
            conn = get_db_conn()
            res = conn.execute('SELECT amount, max_uses, used_count FROM redeem_codes WHERE code=?', (code,)).fetchone()
            if res and res[2] < res[1]:
                amount = res[0]
                conn.execute('UPDATE users SET balance = balance + ? WHERE user_id=?', (amount, user_id))
                conn.execute('UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?', (code,))
                conn.commit()
                await update.message.reply_text(f"🎉 কোড সফলভাবে ক্লেমড! আপনার ওয়ালেটে {amount} টাকা যোগ হয়েছে।")
            else:
                await update.message.reply_text("❌ অবৈধ অথবা এক্সপায়ার্ড রিডিম কোড!")
            conn.close()
            user_states.pop(user_id, None)
            return

        elif current_state == 'ADMIN_GEN_REDEEM':
            try:
                amt, max_u = text.replace('，', ',').split(',')
                code = f"REDEEM-{datetime.now().strftime('%M%S')}"
                conn = get_db_conn()
                conn.execute('INSERT INTO redeem_codes (code, amount, max_uses) VALUES (?, ?, ?)', (code, float(amt), int(max_u)))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ রিডিম কোড জেনারেট সফল:\n`{code}`", parse_mode='Markdown')
            except:
                await update.message.reply_text("❌ ফরম্যাট ভুল। আবার ট্রাই করুন (যেমন: 50,10):")
            user_states.pop(user_id, None)
            return

        elif current_state == 'ADMIN_ADD_CHANNEL_FORCE':
            ch_user = text if text.startswith('@') else f"@{text}"
            conn = get_db_conn()
            try:
                conn.execute('INSERT INTO force_channels (channel_username) VALUES (?)', (ch_user,))
                conn.commit()
                await update.message.reply_text(f"✅ চ্যানেল {ch_user} সফলভাবে ফোর্স জয়েন তালিকায় যোগ হয়েছে।")
            except:
                await update.message.reply_text("❌ এই চ্যানেলটি অলরেডি লিস্টে আছে!")
            conn.close()
            user_states.pop(user_id, None)
            return

        elif current_state == 'ADMIN_ADD_ADMIN':
            try:
                conn = get_db_conn()
                conn.execute('UPDATE users SET is_admin=1 WHERE user_id=?', (int(text),))
                conn.commit()
                conn.close()
                await update.message.reply_text("✅ নতুন সাব-অ্যাডমিন যোগ করা হয়েছে।")
            except:
                await update.message.reply_text("❌ ভুল আইডি।")
            user_states.pop(user_id, None)
            return

    # --- মেনু বাটন ক্লিক হ্যান্ডলারস ---
    if text == "📥 ফাইল আপলোড করুন":
        user_states[user_id] = {'state': 'WAITING_NAME'}
        await update.message.reply_text("📝 প্রথমে আপনার বটের একটি নাম দিন (শুধু ইংরেজিতে, যেমন: testbot):", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
        return

    elif text == "🛍️ প্রিমিয়াম বট স্টোর":
        conn = get_db_conn()
        items = conn.execute('SELECT store_id, bot_name, price FROM premium_store').fetchall()
        purchased = [r[0] for r in conn.execute('SELECT store_id FROM purchased_store_bots WHERE user_id=?', (user_id,)).fetchall()]
        conn.close()
        
        if not items:
            await update.message.reply_text("🛍️ বর্তমানে স্টোরে কোনো প্রিমিয়াম রেডিমেড বট আপলোড করা নেই।")
            return
            
        store_mode = get_setting('store_mode') # PAID or FREE
            
        kb = []
        for sid, name, price in items:
            if sid in purchased:
                kb.append([ibtn(f"✅ {name} (Owned - Lifetime)", callback_data=f"setupowned_{sid}", style="success")])
            elif store_mode == 'FREE':
                kb.append([ibtn(f"🎁 {name} - 0 টাকা (FREE)", callback_data=f"selectstore_{sid}", style="primary")])
            else:
                kb.append([ibtn(f"🤖 {name} - {price} টাকা", callback_data=f"selectstore_{sid}", style="primary")])
        await update.message.reply_text("🛍️ *প্রিমিয়াম রেডিমেড বট স্টোর:*\nনিচের তালিকা থেকে আপনার কাঙ্ক্ষিত বটটি সিলেক্ট করুন:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return
        
    elif text == "📋 আমার বট সমূহ":
        conn = get_db_conn()
        bots = conn.execute('SELECT bot_name, status FROM bots WHERE user_id=?', (user_id,)).fetchall()
        conn.close()
        if not bots:
            await update.message.reply_text("❌ আপনার কোনো হোস্ট করা বট নেই।")
            return
        msg = "📋 *আপনার সংরক্ষিত বট তালিকা:*\n\n"
        kb = []
        for name, st in bots:
            st_str = "🟢 রানিং" if st == 'active' else "🔴 বন্ধ"
            msg += f"🤖 *{name}* — [{st_str}]\n"
            kb.append([rbtn(f"⚙️ কন্ট্রোল: {name}", style="primary")])
        kb.append([rbtn("⬅️ প্রধান মেনু", style="danger")])
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    # Fixed: Accurate Bot Control Commands
    elif text.startswith("⚙️ কন্ট্রোল: "):
        bot_name = text.replace("⚙️ কন্ট্রোল: ", "").strip()
        user_states[user_id] = {'current_bot': bot_name}
        kb = [
            [rbtn(f"▶️ স্টার্ট {bot_name}", style="success"), rbtn(f"🛑 স্টপ {bot_name}", style="danger")],
            [rbtn(f"🗑️ রিমুভ {bot_name}", style="danger"), rbtn("📋 আমার বট সমূহ", style="primary")],
            [rbtn("⬅️ প্রধান মেনু", style="danger")]
        ]
        await update.message.reply_text(f"🤖 বট: *{bot_name}* এর কন্ট্রোল অপশন:", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    elif text.startswith("▶️ স্টার্ট ") or text.startswith("🛑 স্টপ ") or text.startswith("🗑️ রিমুভ "):
        # Fixed the string matching and split bug
        if text.startswith("▶️ স্টার্ট "):
            cmd = "▶️"
            b_name = text.replace("▶️ স্টার্ট ", "").strip()
        elif text.startswith("🛑 স্টপ "):
            cmd = "🛑"
            b_name = text.replace("🛑 স্টপ ", "").strip()
        elif text.startswith("🗑️ রিমুভ "):
            cmd = "🗑️"
            b_name = text.replace("🗑️ রিমুভ ", "").strip()
        else:
            return
            
        conn = get_db_conn()
        bot_info = conn.execute('SELECT is_premium_store FROM bots WHERE user_id=? AND bot_name=?', (user_id, b_name)).fetchone()
        u_data = conn.execute('SELECT premium_until FROM users WHERE user_id=?', (user_id,)).fetchone()
        conn.close()
        
        if not bot_info:
            await update.message.reply_text("❌ এই বটটি ডাটাবেজে পাওয়া যায়নি।")
            return
            
        is_prem = False
        if u_data and u_data[0]:
            is_prem = datetime.strptime(u_data[0], '%Y-%m-%d %H:%M:%S') > datetime.now()
        
        if bot_info and not bot_info[0]:
            if get_setting('premium_system') == 'ON' and not is_prem and cmd == "▶️":
                await update.message.reply_text("❌ আপনার হোস্টিং প্ল্যান একটিভ নেই! দয়া করে ওয়ালেট থেকে প্ল্যান কিনুন।")
                return
            
        bot_file = USER_BOTS_DIR / f"user_{user_id}_{b_name}" / f"{b_name}.py"
        
        if cmd == "▶️":
            if b_name in running_processes:
                await update.message.reply_text("⚠ বটটি ইতিমধ্যেই রানিং আছে।")
            else:
                proc = subprocess.Popen(['python3', str(bot_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                await asyncio.sleep(2)
                if proc.poll() is not None:
                    _, err = proc.communicate()
                    await update.message.reply_text(f"❌ ক্র্যাশ এরর:\n`{err.strip().split('\n')[-1]}`", parse_mode='Markdown')
                else:
                    running_processes[b_name] = proc
                    conn = get_db_conn()
                    conn.execute('UPDATE bots SET status=\'active\' WHERE user_id=? AND bot_name=?', (user_id, b_name))
                    conn.commit()
                    conn.close()
                    await update.message.reply_text(f"🟢 `{b_name}` সফলভাবে ব্যাকগ্রাউন্ডে চালু হয়েছে।")
                    
        elif cmd == "🛑":
            if b_name in running_processes:
                running_processes[b_name].terminate()
                del running_processes[b_name]
            conn = get_db_conn()
            conn.execute('UPDATE bots SET status=\'inactive\' WHERE user_id=? AND bot_name=?', (user_id, b_name))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"🛑 `{b_name}` স্টপ করা হয়েছে।")
            
        elif cmd == "🗑️":
            if b_name in running_processes:
                running_processes[b_name].terminate()
                del running_processes[b_name]
            conn = get_db_conn()
            conn.execute('DELETE FROM bots WHERE user_id=? AND bot_name=?', (user_id, b_name))
            conn.commit()
            conn.close()
            b_dir = USER_BOTS_DIR / f"user_{user_id}_{b_name}"
            if b_dir.exists(): shutil.rmtree(b_dir)
            await update.message.reply_text(f"🗑️ `{b_name}` সম্পূর্ণ রিমুভ করা হয়েছে।")
        return

    elif text == "💼 আমার ওয়ালেট":
        conn = get_db_conn()
        bal, prem = conn.execute('SELECT balance, premium_until FROM users WHERE user_id=?', (user_id,)).fetchone()
        conn.close()
        p_status = f"⌛ একটিভ (মেয়াদ: {prem})" if prem and datetime.strptime(prem, '%Y-%m-%d %H:%M:%S') > datetime.now() else "🔴 ইনএকটিভ"
        kb = [
            [rbtn("➕ ডিপোজিট করুন", style="success"), rbtn("💎 হোস্টিং প্ল্যান কিনুন", style="primary")],
            [rbtn("🪙 রিডিম কোড ব্যবহার", style="success"), rbtn("⬅️ প্রধান মেনু", style="danger")]
        ]
        await update.message.reply_text(f"💼 *আপনার ওয়ালেট প্রোফাইল:*\n\n💰 ব্যালেন্স: {bal} টাকা\n🌟 হোস্টিং স্ট্যাটাস: {p_status}", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    elif text == "➕ ডিপোজিট করুন":
        user_states[user_id] = {'state': 'INPUT_DEPOSIT_AMOUNT'}
        await update.message.reply_text("💵 আপনি কত টাকা ডিপোজিট করতে চান তার পরিমাণ লিখুন (যেমন: 500):", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
        return

    elif text == "💎 হোস্টিং প্ল্যান কিনুন":
        conn = get_db_conn()
        plans = conn.execute('SELECT plan_id, name, days, price FROM plans').fetchall()
        conn.close()
        if not plans:
            await update.message.reply_text("❌ হোস্টিং প্ল্যান উপলব্ধ নেই।")
            return
        kb = []
        for pid, name, days, price in plans:
            kb.append([ibtn(f"✨ {name} ({days} দিন) - {price} টাকা", callback_data=f"selectplan_{pid}", style="primary")])
        await update.message.reply_text("💎 *হোস্টিং প্ল্যান সমূহ:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return

    elif text == "🪙 রিডিম কোড ব্যবহার":
        user_states[user_id] = {'state': 'INPUT_REDEEM'}
        await update.message.reply_text("🔑 আপনার রিডিম কোডটি টাইপ করে পাঠান:", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
        return

    # --- অ্যাডমিন প্যানেল ---
    elif text == "👑 অ্যাডমিন প্যানেল" and is_user_admin(user_id):
        kb = [
            [rbtn("👥 ওল ইউজার", style="primary"), rbtn("⚙️ গেটওয়ে ও মেথড কন্ট্রোল", style="primary")],
            [rbtn("🎫 রিডিম কোড জেনারেটর", style="success"), rbtn("💰 ডাইনামিক প্ল্যান সেটআপ", style="success")],
            [rbtn("📤 প্রিমিয়াম ফাইল আপলোড", style="success"), rbtn("📢 ফোর্স জয়েন চ্যানেল", style="primary")],
            [rbtn("📢 ব্রডকাস্ট মেসেজ", style="primary"), rbtn("➕ অ্যাডমিন যোগ করুন", style="primary")],
            [rbtn("⬅️ প্রধান মেনু", style="danger")]
        ]
        await update.message.reply_text("👑 *স্বাগতম অ্যাডমিন মাস্টার কন্ট্রোলে:*", parse_mode='Markdown', reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    elif text == "📢 ব্রডকাস্ট মেসেজ" and is_user_admin(user_id):
        user_states[user_id] = {'state': 'WAITING_BROADCAST'}
        await update.message.reply_text("📢 ব্রডকাস্ট করার জন্য আপনার মেসেজ, ছবি, ভিডিও বা ফাইল পাঠান:\n(ক্যানসেল করতে '⬅️ ব্যাক অ্যাডমিন মেনু' চাপুন)", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ ব্যাক অ্যাডমিন মেনু", style="danger")]], resize_keyboard=True))
        return

    elif text == "👥 ওল ইউজার" and is_user_admin(user_id):
        conn = get_db_conn()
        users = conn.execute('SELECT user_id, name, balance FROM users').fetchall()
        conn.close()
        
        await update.message.reply_text("👥 *রেজিস্টার্ড ইউজার তালিকা:* \nনিচের বাটন থেকে ফাইল বক্স চেক করুন।")
        for uid, name, bal in users[:40]:
            kb = [[ibtn("⚙️ ফাইল ও ডিটেইলস", callback_data=f"adm_usr_box_{uid}", style="primary")]]
            await update.message.reply_text(f"👤 **ইউজার:** {name}\n🆔 **আইডি:** `{uid}`\n💰 **ব্যালেন্স:** {bal} টাকা", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return

    elif text == "🎫 রিডিম কোড জেনারেটর" and is_user_admin(user_id):
        user_states[user_id] = {'state': 'ADMIN_GEN_REDEEM'}
        await update.message.reply_text("🎫 *রিডিম কোড তৈরি ফরম্যাট:*\n\nটাকার পরিমাণ এবং সর্বোচ্চ কতজন ব্যবহার করতে পারবে তা কমা (,) দিয়ে লিখুন।\nযেমন: `50,10` (মানে ৫০ টাকা, ১০ জন ক্লেম করতে পারবে):")
        return

    elif text == "📢 ফোর্স জয়েন চ্যানেল" and is_user_admin(user_id):
        conn = get_db_conn()
        channels = [r[0] for r in conn.execute('SELECT channel_username FROM force_channels').fetchall()]
        conn.close()
        
        kb = [[ibtn("➕ নতুন চ্যানেল অ্যাড করুন", callback_data="add_f_chan", style="success")]]
        msg = "📢 *ফোর্স জয়েন চ্যানেল কন্ট্রোল প্যানেল:*\n\n"
        if not channels:
            msg += "❌ বর্তমানে কোনো বাধ্যতামূলক চ্যানেল সেট করা নেই।"
        else:
            msg += "চলতি চ্যানেল তালিকা (রিমুভ করতে ক্লিক করুন):\n"
            for ch in channels:
                kb.append([ibtn(f"❌ রিমুভ: {ch}", callback_data=f"rem_f_chan_{ch}", style="danger")])
        
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return

    elif text == "➕ অ্যাডমিন যোগ করুন" and is_user_admin(user_id):
        user_states[user_id] = {'state': 'ADMIN_ADD_ADMIN'}
        await update.message.reply_text("➕ যাকে সাব-অ্যাডমিন বানাতে চান তার টেলিগ্রাম অ্যাকাউন্ট ID (User ID) টি পাঠান:")
        return

    elif text == "💰 ডাইনামিক প্ল্যান সেটআপ" and is_user_admin(user_id):
        user_states[user_id] = {'state': 'ADMIN_ADD_PLAN'}
        await update.message.reply_text("💰 *নতুন হোস্টিং প্ল্যান যোগ করার নিয়ম:*\n\nদিন এবং মূল্য কমা দিয়ে লিখুন।\nযেমন: `30,150` (মানে ৩০ দিন, ১৫০ টাকা):")
        return

    elif text == "⚙️ গেটওয়ে ও মেথড কন্ট্রোল" and is_user_admin(user_id):
        p_sys, bk, ng, bn = get_setting('premium_system'), get_setting('bkash'), get_setting('nagod'), get_setting('binance')
        bk_num, ng_num, bn_uid = get_setting('bkash_number'), get_setting('nagod_number'), get_setting('binance_uid')
        kb = [
            [ibtn(f"🔄 হোস্টিং সিস্টেম: {p_sys}", callback_data="toggle_premium_system", style="primary")],
            [ibtn(f"বিকাশ: {bk}", callback_data="toggle_bkash", style="success"), ibtn(f"বিকাশ নং সেট", callback_data="set_bkash", style="primary")],
            [ibtn(f"নগদ: {ng}", callback_data="toggle_nagod", style="success"), ibtn(f"নগদ নং সেট", callback_data="set_nagod", style="primary")],
            [ibtn(f"বাইনান্স: {bn}", callback_data="toggle_binance", style="success"), ibtn(f"বাইনান্স UID সেট", callback_data="set_binance", style="primary")]
        ]
        await update.message.reply_text(f"⚙ *পেমেন্ট কনফিগারেশন ও গেটওয়ে কন্ট্রোল:*\n\n📞 বিকাশ: `{bk_num}`\n📞 নগদ: `{ng_num}`\n💳 বাইনান্স: `{bn_uid}`", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return

    elif text == "📤 প্রিমিয়াম ফাইল আপলোড" and is_user_admin(user_id):
        store_mode = get_setting('store_mode')
        kb = [
            [ibtn("➕ নতুন বট অ্যাড করুন", callback_data="prem_add_new", style="success")],
            [ibtn("📋 আপলোড করা বট ম্যানেজ", callback_data="prem_manage_list", style="primary")],
            [ibtn(f"🛒 স্টোর মোড: {store_mode}", callback_data="toggle_store_mode", style="danger")]
        ]
        await update.message.reply_text("📤 *প্রিমিয়াম স্টোর ম্যানেজার:*\nআপনি কি করতে চান তা সিলেক্ট করুন:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return


# ================= মাল্টিমিডিয়া ব্রডকাস্ট হ্যান্ডলার (ছবি, ভিডিও ইত্যাদি) =================
async def handle_multimedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id, {}).get('state') == 'WAITING_BROADCAST' and is_user_admin(user_id):
        conn = get_db_conn()
        users = conn.execute('SELECT user_id FROM users').fetchall()
        conn.close()
        success = 0
        await update.message.reply_text("⏳ মিডিয়া ব্রডকাস্ট পাঠানো শুরু হয়েছে, দয়া করে অপেক্ষা করুন...")
        for u in users:
            try:
                await update.message.copy(chat_id=u[0])
                success += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ ব্রডকাস্ট সফলভাবে {success} জন ইউজারকে পাঠানো হয়েছে।")
        user_states.pop(user_id, None)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    # প্রিমিয়াম স্টোর ম্যানেজমেন্ট কলব্যাকস
    if data == "prem_add_new":
        if not is_user_admin(user_id): return
        user_states[user_id] = {'state': 'PREM_ADD_NAME'}
        await query.message.reply_text("📝 রেডিমেড প্রিমিয়াম বটের একটি সুন্দর নাম দিন (যেমন: Instagram Task Bot):", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ ব্যাক অ্যাডমিন মেনু", style="danger")]], resize_keyboard=True))
        return
        
    elif data == "prem_manage_list":
        if not is_user_admin(user_id): return
        conn = get_db_conn()
        items = conn.execute('SELECT store_id, bot_name, price FROM premium_store').fetchall()
        conn.close()
        if not items:
            await query.message.edit_text("❌ স্টোরে কোনো বট আপলোড করা নেই।")
            return
        kb = []
        for sid, name, price in items:
            kb.append([ibtn(f"🗑️ রিমুভ: {name}", callback_data=f"del_storebot_{sid}", style="danger")])
        await query.message.edit_text("📋 *স্টোরে থাকা বট সমূহ (রিমুভ করতে ক্লিক করুন):*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return
        
    elif data.startswith("del_storebot_"):
        if not is_user_admin(user_id): return
        sid = data.split("_")[2]
        conn = get_db_conn()
        conn.execute('DELETE FROM premium_store WHERE store_id=?', (sid,))
        conn.commit()
        conn.close()
        await query.message.edit_text("✅ বটটি স্টোর থেকে সফলভাবে রিমুভ করা হয়েছে।")
        return
        
    elif data == "toggle_store_mode":
        if not is_user_admin(user_id): return
        current = get_setting('store_mode')
        new_mode = "FREE" if current == "PAID" else "PAID"
        set_setting('store_mode', new_mode)
        
        kb = [
            [ibtn("➕ নতুন বট অ্যাড করুন", callback_data="prem_add_new", style="success")],
            [ibtn("📋 আপলোড করা বট ম্যানেজ", callback_data="prem_manage_list", style="primary")],
            [ibtn(f"🛒 স্টোর মোড: {new_mode}", callback_data="toggle_store_mode", style="danger")]
        ]
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(kb))
        await query.message.reply_text(f"✅ স্টোর মোড পরিবর্তন করে {new_mode} করা হয়েছে।")
        return

    # ফোর্স জয়েন অ্যাড-রিমুভ হ্যান্ডলার
    if data == "add_f_chan":
        if not is_user_admin(user_id): return
        user_states[user_id] = {'state': 'ADMIN_ADD_CHANNEL_FORCE'}
        await query.message.reply_text("📢 চ্যানেল ইউজারনেমটি পাঠান (যেমন: @mychannel):")
        return
        
    elif data.startswith("rem_f_chan_"):
        if not is_user_admin(user_id): return
        ch_target = data.replace("rem_f_chan_", "")
        conn = get_db_conn()
        conn.execute('DELETE FROM force_channels WHERE channel_username=?', (ch_target,))
        conn.commit()
        conn.close()
        await query.message.edit_text(f"✅ {ch_target} সফলভাবে রিমুভ করা হয়েছে।")
        return

    # ওল ইউজার ফাইল বক্স ভিউয়ার
    elif data.startswith("adm_usr_box_"):
        if not is_user_admin(user_id): return
        target_uid = int(data.split("_")[3])
        
        conn = get_db_conn()
        usr_info = conn.execute('SELECT name, balance FROM users WHERE user_id=?', (target_uid,)).fetchone()
        user_bots = conn.execute('SELECT bot_name, status FROM bots WHERE user_id=?', (target_uid,)).fetchall()
        conn.close()
        
        if not usr_info: return
        
        msg = f"📦 *ইউজার ডিটেইলস বক্স*\n\n" \
              f"👤 **ফার্স্ট নেম:** {usr_info[0]}\n" \
              f"🆔 **আইডি:** `{target_uid}`\n" \
              f"💰 **ব্যালেন্স:** {usr_info[1]} টাকা\n\n" \
              f"📋 **রান করা ও হোস্টেড বটসমূহ:**\n"
              
        if not user_bots:
            msg += "❌ কোনো ফাইল বা বট হোস্টেড নেই।"
            await query.message.reply_text(msg, parse_mode='Markdown')
        else:
            await query.message.reply_text(msg, parse_mode='Markdown')
            for b_name, status in user_bots:
                st_str = "🟢 রানিং" if status == 'active' else "🔴 বন্ধ"
                await query.message.reply_text(f"🤖 **বটের নাম:** `{b_name}` [{st_str}]")
                
                b_dir = USER_BOTS_DIR / f"user_{target_uid}_{b_name}"
                if b_dir.exists():
                    all_files = [f for f in b_dir.iterdir() if f.is_file()]
                    if all_files:
                        for f in all_files:
                            try:
                                with open(f, 'rb') as doc_file:
                                    await context.bot.send_document(chat_id=user_id, document=doc_file, caption=f"📁 ফাইল: `{f.name}`\n🤖 বটের আন্ডারে: `{b_name}`", parse_mode='Markdown')
                            except Exception as e:
                                logger.error(f"Error sending file: {e}")
                    else:
                        await query.message.reply_text("📂 ফোল্ডারটি খালি (কোনো ফাইল নেই)।")
                else:
                    await query.message.reply_text("❌ বটের ফোল্ডার ডিরেক্টরি খুঁজে পাওয়া যায়নি।")
        return

    if data == "g_req_yes":
        user_states[user_id]['ask_group_id'] = 1
        user_states[user_id]['state'] = 'PREM_ADD_PY'
        await query.message.reply_text("📁 এবার এই বটের মূল পাইথন (.py) ফাইলটি ডকুমেন্ট হিসেবে আপলোড করুন:")
        return
    elif data == "g_req_no":
        user_states[user_id]['ask_group_id'] = 0
        user_states[user_id]['state'] = 'PREM_ADD_PY'
        await query.message.reply_text("📁 এবার এই বটের মূল পাইথন (.py) ফাইলটি ডকুমেন্ট হিসেবে আপলোড করুন:")
        return

    # প্রিমিয়াম বট স্টোর সিলেকশন
    if data.startswith("selectstore_"):
        store_id = data.split("_")[1]
        conn = get_db_conn()
        item = conn.execute('SELECT bot_name, price, ask_group_id FROM premium_store WHERE store_id=?', (store_id,)).fetchone()
        user_bal = conn.execute('SELECT balance FROM users WHERE user_id=?', (user_id,)).fetchone()[0]
        conn.close()
        
        if not item: return
        name, price, ask_group = item
        store_mode = get_setting('store_mode')
        
        # Free mode auto-buy logic
        if store_mode == 'FREE':
            conn = get_db_conn()
            conn.execute('INSERT OR IGNORE INTO purchased_store_bots (user_id, store_id) VALUES (?, ?)', (user_id, int(store_id)))
            conn.commit()
            conn.close()
            user_states[user_id] = {'state': 'PREM_WIZ_TOKEN', 'store_id': store_id, 'ask_group_id': ask_group}
            await query.message.edit_text(f"🎁 **ফ্রি পারচেজ সফল!**\n\n🤖 **বট:** `{name}`\n🔑 কনফিগার করতে আপনার বটের **বট টোকেন (Bot Token)** টি মেসেজ করুন:")
            return
        
        kb = []
        if float(user_bal) >= float(price):
            kb.append([ibtn(f"🪙 Wallet Balance থেকে কিনুন ({price} টাকা)", callback_data=f"buyvia_wallet_store_{store_id}", style="success")])
        else:
            kb.append([ibtn(f"❌ ওয়ালেট ব্যালেন্স কম ({user_bal} টাকা)", callback_data="insufficient_bal_alert", style="danger")])
        
        if get_setting('bkash') == 'ON': kb.append([ibtn("বিকাশ (bKash) দিয়ে সরাসরি কিনুন", callback_data=f"buyvia_bkash_store_{store_id}", style="primary")])
        if get_setting('nagod') == 'ON': kb.append([ibtn("নগদ (Nagad) দিয়ে সরাসরি কিনুন", callback_data=f"buyvia_nagod_store_{store_id}", style="primary")])
        
        await query.message.edit_text(f"🛒 *বট:* {name}\n💵 *মূল্য:* {price} টাকা\n\nআপনার পেমেন্ট মাধ্যমটি সিলেক্ট করুন:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data == "insufficient_bal_alert":
        await query.answer("❌ আপনার ওয়ালেটে পর্যাপ্ত টাকা নেই! ডিপোজিট করুন অথবা অন্য পেমেন্ট মেথড সিলেক্ট করুন।", show_alert=True)
        return

    elif data.startswith("setupowned_"):
        store_id = data.split("_")[1]
        conn = get_db_conn()
        item = conn.execute('SELECT ask_group_id FROM premium_store WHERE store_id=?', (store_id,)).fetchone()
        conn.close()
        user_states[user_id] = {'state': 'PREM_WIZ_TOKEN', 'store_id': store_id, 'ask_group_id': item[0]}
        await query.message.reply_text("🔑 আজীবন লাইসেন্স ভেরিফাইড! আপনার বটের জন্য নতুন **বট টোকেন (Bot Token)** টি মেসেজ করুন:")

    elif data.startswith("buyvia_"):
        parts = data.split("_")
        method, item_type, store_id = parts[1], parts[2], parts[3]
        
        conn = get_db_conn()
        item = conn.execute('SELECT bot_name, price, ask_group_id FROM premium_store WHERE store_id=?', (store_id,)).fetchone()
        conn.close()
        name, price, ask_group = item
        
        if method == "wallet":
            conn = get_db_conn()
            conn.execute('UPDATE users SET balance = balance - ? WHERE user_id=?', (price, user_id))
            conn.execute('INSERT OR IGNORE INTO purchased_store_bots (user_id, store_id) VALUES (?, ?)', (user_id, int(store_id)))
            conn.commit()
            conn.close()
            
            user_states[user_id] = {'state': 'PREM_WIZ_TOKEN', 'store_id': store_id, 'ask_group_id': ask_group}
            
            await query.message.edit_text(
                f"🛍️ **পারচেজ সফল হয়েছে! (ওয়ালেট পেমেন্ট)**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎉 আপনার ওয়ালেট থেকে সফলভাবে `{price} টাকা` কেটে নেওয়া হয়েছে।\n"
                f"🤖 **বটের নাম:** `{name}`\n\n"
                f"🔑 এবার আপনার বটের **বট টোকেন (Bot Token)** টি মেসেজ করে কনফিগারেশন সম্পন্ন করুন:"
            )
        else:
            number = get_setting(f"{method}_number")
            user_states[user_id] = {'state': 'WAITING_SCREENSHOT', 'pay_type': 'STORE', 'method': method.upper(), 'store_id': store_id, 'price': price, 'ask_group_id': ask_group}
            await query.message.edit_text(f"💰 {method.upper()} করুন `{number}` নাম্বারে। পরিমাণ: *{price} টাকা*। সেন্ড মানি করে স্ক্রিনশটটি ছবি (Photo) আকারে পাঠান।", parse_mode='Markdown')

    elif data.startswith("selectplan_"):
        plan_id = data.split("_")[1]
        conn = get_db_conn()
        plan = conn.execute('SELECT name, days, price FROM plans WHERE plan_id=?', (plan_id,)).fetchone()
        user_bal = conn.execute('SELECT balance FROM users WHERE user_id=?', (user_id,)).fetchone()[0]
        conn.close()
        
        p_name, p_days, p_price = plan
        kb = []
        if float(user_bal) >= float(p_price):
            kb.append([ibtn(f"🪙 Wallet Balance থেকে কিনুন ({p_price} টাকা)", callback_data=f"planvia_wallet_{plan_id}", style="success")])
        if get_setting('bkash') == 'ON': kb.append([ibtn("বিকাশ (bKash) দিয়ে কিনুন", callback_data=f"planvia_bkash_{plan_id}", style="primary")])
        if get_setting('nagod') == 'ON': kb.append([ibtn("নগদ (Nagad) দিয়ে কিনুন", callback_data=f"planvia_nagod_{plan_id}", style="primary")])
        
        await query.message.edit_text(f"🛒 *হোস্টিং প্ল্যান:* {p_name} ({p_price} টাকা)\nপেমেন্ট মেথড সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("planvia_"):
        parts = data.split("_")
        method, plan_id = parts[1], parts[2]
        conn = get_db_conn()
        plan = conn.execute('SELECT name, days, price FROM plans WHERE plan_id=?', (plan_id,)).fetchone()
        conn.close()
        p_name, p_days, p_price = plan
        
        if method == "wallet":
            expiry = (datetime.now() + timedelta(days=p_days)).strftime('%Y-%m-%d %H:%M:%S')
            conn = get_db_conn()
            conn.execute('UPDATE users SET balance = balance - ? WHERE user_id=?', (p_price, user_id))
            conn.execute('UPDATE users SET premium_until = ? WHERE user_id=?', (expiry, user_id))
            conn.commit()
            conn.close()
            await query.message.edit_text(
                f"💎 **হোস্টিং প্ল্যান পারচেজ সফল!**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎉 ওয়ালেট ব্যালেন্স দিয়ে হোস্টিং প্ল্যান সফলভাবে অ্যাক্টিভেট করা হয়েছে।\n"
                f"📦 **প্ল্যান:** `{p_name}`\n"
                f"⌛ **মেয়াদ:** `{expiry}`"
            )
        else:
            number = get_setting(f"{method}_number")
            user_states[user_id] = {'state': 'WAITING_SCREENSHOT', 'pay_type': 'PLAN', 'method': method.upper(), 'days': p_days, 'price': p_price, 'plan_name': p_name}
            await query.message.edit_text(f"💰 {method.upper()} করুন `{number}` নাম্বারে। পরিমাণ: *{p_price} টাকা*। এরপর স্ক্রিনশটটি ছবি আকারে পাঠান।", parse_mode='Markdown')

    elif data.startswith("depmeth_"):
        method = data.split("_")[1]
        number = get_setting(f"{method}_number") if method != 'binance' else get_setting("binance_uid")
        amount = user_states[user_id]['deposit_amount']
        
        user_states[user_id] = {'state': 'WAITING_SCREENSHOT', 'pay_type': 'DEPOSIT', 'method': method.upper(), 'price': amount}
        await query.message.edit_text(f"💰 আপনার সিলেক্ট করা পরিমাণ: *{amount} টাকা*।\nদয়া করে {method.upper()} করুন এই অ্যাড্রেসে: `{number}`।\n\nটাকা পাঠানো সম্পন্ন হলে স্ক্রিনশটটি ফটো আকারে এখানে আপলোড করুন।", parse_mode='Markdown')

    elif data.startswith("set_"):
        action = data.replace("set_", "").upper()
        user_states[user_id] = {'state': f'SET_{action}'}
        await query.message.reply_text(f"📞 নতুন {action} তথ্য বা নাম্বারটি টাইপ করে পাঠান:")

    elif data.startswith("toggle_"):
        if not is_user_admin(user_id): return
        key = data.replace("toggle_", "")
        set_setting(key, "OFF" if get_setting(key) == "ON" else "ON")
        await query.message.reply_text(f"⚙️ {key.upper()} সেটিং পরিবর্তিত হয়েছে।")

    # ================= সুন্দর নোটিফিকেশন সিস্টেম গেটওয়ে =================
    elif data.startswith("appr_") or data.startswith("rej_"):
        if not is_user_admin(user_id): return
        parts = data.split("_")
        action, target_uid, p_type = parts[0], parts[1], parts[2]
        
        try:
            chat_info = await context.bot.get_chat(chat_id=int(target_uid))
            target_name = chat_info.first_name
        except:
            target_name = "সম্মানিত গ্রাহক"
            
        if action == "appr":
            conn = get_db_conn()
            try:
                if p_type == "DEPOSIT":
                    amt = float(parts[3])
                    conn.execute('UPDATE users SET balance = balance + ? WHERE user_id=?', (amt, int(target_uid)))
                    total_bal = conn.execute('SELECT balance FROM users WHERE user_id=?', (int(target_uid),)).fetchone()[0]
                    conn.commit()
                    await query.message.edit_text(f"✅ ডিপোজিট অ্যাপ্রুভড! {amt} টাকা ইউজারের ওয়ালেটে যোগ হয়েছে।")
                    try: 
                        await context.bot.send_message(
                            chat_id=int(target_uid), 
                            text=f"💳 **ডিপোজিট সফল হয়েছে!**\n"
                                 f"━━━━━━━━━━━━━━━━━━\n"
                                 f"প্রিয় **{target_name}**, আপনার অ্যাকাউন্টে সফলভাবে টাকা যুক্ত হয়েছে।\n\n"
                                 f"💰 **ডিপোজিট পরিমাণ:** `{amt} ৳`\n"
                                 f"📈 **বর্তমান মোট ব্যালেন্স:** `{total_bal} ৳`\n\n"
                                 f"✨ এখন আপনি স্টোর বা প্ল্যান পেইজ থেকে আপনার কাঙ্ক্ষিত সার্ভিসটি উপভোগ করতে পারেন। ধন্যবাদ! 🎉"
                        )
                    except: pass
                    
                elif p_type == "PLAN":
                    p_days = int(parts[3])
                    expiry = (datetime.now() + timedelta(days=p_days)).strftime('%Y-%m-%d %H:%M:%S')
                    conn.execute('UPDATE users SET premium_until = ? WHERE user_id=?', (expiry, int(target_uid)))
                    conn.commit()
                    await query.message.edit_text(f"✅ হোস্টিং প্ল্যান অ্যাপ্রুভড!")
                    try: 
                        await context.bot.send_message(
                            chat_id=int(target_uid), 
                            text=f"💎 **হোস্টিং প্ল্যান সফলভাবে সক্রিয় হয়েছে!**\n"
                                 f"━━━━━━━━━━━━━━━━━━\n"
                                 f"প্রিয় **{target_name}**, আপনার পাঠানো পেমেন্ট ভেরিফাই করে হোস্টিং মেম্বারশিপটি অ্যাপ্রুভ করা হয়েছে।\n\n"
                                 f"📦 **মেয়াদের দিন:** `{p_days} দিন`\n"
                                 f"⌛ **শেষ হওয়ার তারিখ:** `{expiry}`\n\n"
                                 f"🚀 এখন আপনি আপনার বটগুলো নিরবচ্ছিন্নভাবে রান করতে পারবেন।"
                        )
                    except: pass
                    
                elif p_type == "STORE":
                    sid = int(parts[3])
                    conn.execute('INSERT OR IGNORE INTO purchased_store_bots (user_id, store_id) VALUES (?, ?)', (int(target_uid), sid))
                    s_name = conn.execute('SELECT bot_name FROM premium_store WHERE store_id=?', (sid,)).fetchone()[0]
                    conn.commit()
                    await query.message.edit_text(f"✅ প্রিমিয়াম বট পারচেজ অ্যাপ্রুভড!")
                    try: 
                        await context.bot.send_message(
                            chat_id=int(target_uid), 
                            text=f"🛍️ **প্রিমিয়াম স্টোর পারচেজ সফল!**\n"
                                 f"━━━━━━━━━━━━━━━━━━\n"
                                 f"প্রিয় **{target_name}**, আপনার প্রিমিয়াম বট পেমেন্ট অনুরোধটি সফলভাবে অ্যাপ্রুভ হয়েছে।\n\n"
                                 f"🤖 **বট প্রডাক্ট:** `{s_name}`\n"
                                 f"📜 **লাইসেন্স টাইপ:** `আজীবন (Lifetime Free)`\n\n"
                                 f"⚙️ এখন '🛍️ প্রিমিয়াম বট স্টোর' এ গিয়ে বটটি আপনার নিজস্ব টোকেন দিয়ে ইনস্ট্যান্টলি সেটআপ করুন।"
                        )
                    except: pass
            finally:
                conn.close()
        else:
            # 🔴 ক্যানসেল/রিজেক্টেড নোটিফিকেশন ফিক্সড
            await query.message.edit_text(f"❌ পেমেন্ট রিকোয়েস্ট রিজেক্ট/ক্যানসেল করা হয়েছে।")
            try: 
                await context.bot.send_message(
                    chat_id=int(target_uid), 
                    text=f"⚠️ **অনুরোধটি বাতিল করা হয়েছে**\n"
                         f"━━━━━━━━━━━━━━━━━━\n"
                         f"প্রিয় **{target_name}**, দুঃখিত! আপনার পাঠানো পেমেন্ট/ডিপোজিট অনুরোধটি অ্যাডমিন ভেরিফাই করতে পারেনি বিধায় বাতিল করা হয়েছে।\n\n"
                         f"❌ **টাইপ:** `{p_type}`\n"
                         f"📝 **করণীয়:** সঠিক ট্রানজেকশন স্ক্রিনশট ও তথ্য দিয়ে আবার রিকোয়েস্ট করুন অথবা এডমিন সাপোর্ট লাইনে যোগাযোগ করুন।"
                )
            except: pass

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not user_states.get(user_id) or user_states[user_id].get('state') != 'WAITING_SCREENSHOT': return
    state_data = user_states[user_id]
    photo = update.message.photo[-1]
    p_type = state_data['pay_type']
    
    if p_type == "DEPOSIT":
        kb = [[ibtn("✅ Approve Deposit", callback_data=f"appr_{user_id}_DEPOSIT_{state_data['price']}", style="success"), ibtn("❌ Cancel / Reject", callback_data=f"rej_{user_id}_DEPOSIT", style="danger")]]
        caption = f"📥 **নতুন ডিপোজিট অনুরোধ এসেছে!**\n━━━━━━━━━━━━━━━━━━\n👤 **ইউজার আইডি:** `{user_id}`\n💰 **পরিমাণ:** `{state_data['price']} টাকা`\n⚡ **মেথড:** `{state_data['method']}`\n\n🔽 ভেরিফাই করে একশন বাটন সিলেক্ট করুন:"
    elif p_type == "PLAN":
        kb = [[ibtn("✅ Approve Plan", callback_data=f"appr_{user_id}_PLAN_{state_data['days']}", style="success"), ibtn("❌ Cancel / Reject", callback_data=f"rej_{user_id}_PLAN", style="danger")]]
        caption = f"📥 **নতুন হোস্টিং প্ল্যান পারচেজ অনুরোধ!**\n━━━━━━━━━━━━━━━━━━\n👤 **ইউজার আইডি:** `{user_id}`\n📦 **প্ল্যান:** `{state_data['plan_name']}`\n💰 **মূল্য:** `{state_data['price']} টাকা`"
    elif p_type == "STORE":
        kb = [[ibtn("✅ Approve Store Bot", callback_data=f"appr_{user_id}_STORE_{state_data['store_id']}", style="success"), ibtn("❌ Cancel / Reject", callback_data=f"rej_{user_id}_STORE", style="danger")]]
        caption = f"📥 **নতুন প্রিমিয়াম স্টোর পারচেজ অনুরোধ!**\n━━━━━━━━━━━━━━━━━━\n👤 **ইউজার আইডি:** `{user_id}`\n💰 **মূল্য:** `{state_data['price']} টাকা`\n⚡ **মেথড:** `{state_data['method']}`"

    await context.bot.send_photo(chat_id=SUPER_ADMIN, photo=photo.file_id, caption=caption, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    user_states.pop(user_id, None)
    await update.message.reply_text("⏳ স্ক্রিনশট সফলভাবে পাঠানো হয়েছে! অ্যাডমিন ভেরিফাই করলেই আপনার একশনটি সম্পন্ন হবে।")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    filename = doc.file_name.lower()
    
    if user_id in user_states and 'state' in user_states[user_id]:
        c_state = user_states[user_id]['state']
        
        if c_state == 'PREM_ADD_PY' and filename.endswith('.py'):
            py_save_name = f"prem_src_{datetime.now().strftime('%M%S')}.py"
            t_file = await context.bot.get_file(doc.file_id)
            await t_file.download_to_drive(PREMIUM_STORE_DIR / py_save_name)
            
            user_states[user_id]['py_file'] = py_save_name
            user_states[user_id]['state'] = 'PREM_ADD_REQ'
            await update.message.reply_text("📄 এবার এই বটের জন্য `requirements.txt` ফাইলটি আপলোড করুন। না লাগলে কীবোর্ড থেকে সরাসরি /skip লিখুন।")
            return
            
        elif c_state == 'PREM_ADD_REQ':
            req_save_name = f"prem_req_{datetime.now().strftime('%M%S')}.txt"
            if not filename.startswith('/skip'):
                t_file = await context.bot.get_file(doc.file_id)
                await t_file.download_to_drive(PREMIUM_STORE_DIR / req_save_name)
            else:
                req_save_name = ""
            
            s_data = user_states[user_id]
            conn = get_db_conn()
            conn.execute('INSERT INTO premium_store (bot_name, price, py_file, req_file, ask_group_id) VALUES (?, ?, ?, ?, ?)', (s_data['store_name'], s_data['store_price'], s_data['py_file'], req_save_name, s_data.get('ask_group_id', 0)))
            conn.commit()
            conn.close()
            await update.message.reply_text("🎉 প্রিমিয়াম রেডিমেড বটটি ডাইনামিক ফিল্ডসহ স্টোরে সফলভাবে আপলোড হয়েছে!", reply_markup=ReplyKeyboardMarkup([[rbtn("👑 অ্যাডমিন প্যানেল", style="danger")]], resize_keyboard=True))
            user_states.pop(user_id, None)
            return

    if filename.endswith('.txt') or filename == 'requirements.txt':
        conn = get_db_conn()
        last_bot = conn.execute('SELECT bot_name FROM bots WHERE user_id=? ORDER BY bot_id DESC LIMIT 1', (user_id,)).fetchone()
        conn.close()
        if (user_id in user_states and 'bot_name' in user_states[user_id]) or last_bot:
            b_name = user_states[user_id]['bot_name'] if (user_id in user_states and 'bot_name' in user_states[user_id]) else last_bot[0]
            b_dir = USER_BOTS_DIR / f"user_{user_id}_{b_name}"
            b_dir.mkdir(exist_ok=True, parents=True)
            
            dest = b_dir / 'requirements.txt'
            t_file = await context.bot.get_file(doc.file_id)
            await t_file.download_to_drive(dest)
            
            await update.message.reply_text(f"⚡ রিকোয়ারমেন্টস ফাইল রিসিভড! মডিউল ইনস্টল হয়ে বটটি অটোমেটিক চালু হচ্ছে...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(dest)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            bot_file = b_dir / f"{b_name}.py"
            if bot_file.exists():
                if b_name in running_processes: running_processes[b_name].terminate()
                proc = subprocess.Popen(['python3', str(bot_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                running_processes[b_name] = proc
                conn = get_db_conn()
                conn.execute('UPDATE bots SET status=\'active\' WHERE user_id=? AND bot_name=?', (user_id, b_name))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"🟢 সব মডিউল ইনস্টল শেষে আপনার `{b_name}` বটটি ব্যাকগ্রাউন্ডে সফলভাবে অটো-রান হয়েছে!")
        return

    if user_id in user_states and 'bot_name' in user_states[user_id]:
        state_data = user_states[user_id]
        if state_data.get('state') == 'WAITING_FILE' and filename.endswith('.py'):
            b_name = state_data['bot_name']
            b_dir = USER_BOTS_DIR / f"user_{user_id}_{b_name}"
            b_dir.mkdir(exist_ok=True, parents=True)
            dest = b_dir / f"{b_name}.py"
            t_file = await context.bot.get_file(doc.file_id)
            await t_file.download_to_drive(dest)
            
            custom_db_filename = f"db_user_{user_id}_bot_{b_name}.db"
            code = dest.read_text(encoding='utf-8')
            match = re.search(r'[0-9]{8,10}:[a-zA-Z0-9_-]{35}', code)
            token = match.group(0) if match else f"demo_{user_id}_{b_name}"
            
            fixed_code = f"import sqlite3\nimport os\nos.makedirs('{DB_DIR}', exist_ok=True)\ndef get_isolated_connection(): return sqlite3.connect('{DB_DIR / custom_db_filename}')\n" + code
            dest.write_text(fixed_code, encoding='utf-8')
            
            conn = get_db_conn()
            conn.execute('INSERT OR REPLACE INTO bots (user_id, bot_name, token) VALUES (?, ?, ?)', (user_id, b_name, token))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ মেইন স্ক্রিপ্ট আপলোড সম্পূর্ণ। কোনো টেক্সট বা রিকোয়ারমেন্টস ফাইল থাকলে পাঠান, নয়তো সরাসরি '📋 আমার বট সমূহ' থেকে রান করুন।", reply_markup=ReplyKeyboardMarkup([[rbtn("⬅️ প্রধান মেনু", style="danger")]], resize_keyboard=True))
            user_states[user_id]['state'] = 'WAITING_REQ_OPTIONAL'

def main():
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    app = Application.builder().token(MAIN_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT & ~filters.Document.ALL, handle_multimedia)) # For Broadcast Media
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    logger.info("🚀 অল-ইন-ওয়ান হোস্টিং ও প্রিমিয়াম স্টোর সিস্টেম সাকসেসফুলি রানিং...")
    app.run_polling()

if __name__ == '__main__':
    main()
