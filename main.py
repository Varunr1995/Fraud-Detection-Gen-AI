# App ID: 1363217653938000053
# Public Key: 445a53fb368e3a11b5eda2627472d39af7922572a5af0608124c523a4b77451c
# Bot Token loaded via DISCORD_BOT_TOKEN env

import discord
from discord.ext import commands
from PIL import Image
import pytesseract
import os
import re
import spacy
import requests
from dotenv import load_dotenv
from transformers import pipeline
from supabase import create_client, Client

# Load environment
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Tesseract configuration
pytesseract.pytesseract.tesseract_cmd = "/opt/homebrew/bin/tesseract"

# NLP models
nlp = spacy.load("en_core_web_sm")
ner = pipeline("ner", model="dslim/bert-base-NER", grouped_entities=True)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def is_valid_city(name):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": name, "format": "json", "limit": 1},
            headers={"User-Agent": "receipt-bot"},
            timeout=5
        )
        data = resp.json()
        if data and data[0].get("type", "") in ("city", "town", "village"):
            return True
    except Exception:
        pass
    return False


def extract_city_name(txt):
    for ent in ner(txt):
        if ent.get('entity_group') in ('LOC', 'GPE'):
            candidate = ent.get('word')
            if is_valid_city(candidate):
                return candidate
    for ent in nlp(txt).ents:
        if ent.label_ == 'GPE' and is_valid_city(ent.text):
            return ent.text
    return None


def extract_fields(txt):
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    amount = None
    for line in reversed(lines):
        if re.search(r"\bTotal\b", line, re.I):
            m = re.search(r"([\d,]+(?:\.\d{2})?)", line)
            if m:
                amount = m.group(1).replace(",", "")
            break
    if not amount:
        for line in reversed(lines):
            m2 = re.search(r"(?:₹|Rs\.?)+\s*([\d,]+(?:\.\d{2})?)", line)
            if m2:
                amount = m2.group(1).replace(",", "")
                break
    if not amount:
        m3 = re.search(r"([\d,]+(?:\.\d{2})?)", txt)
        if m3:
            amount = m3.group(1).replace(",", "")
    date = None
    d = re.search(r"delivered on\s*([A-Za-z]+\s*\d{1,2},\s*\d{1,2}:\d{2}\s*[AP]M)", txt, re.I)
    if d:
        date = d.group(1)
    else:
        d2 = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b", txt)
        if d2:
            date = d2.group(1)
    city = extract_city_name(txt)
    return {"amount": amount, "date": date, "city": city}


def save_receipt(user_id, fields, image_path):
    # upload image to Supabase Storage
    bucket = supabase.storage.from_('receipts')
    filename = os.path.basename(image_path)
    with open(image_path, 'rb') as f:
        bucket.upload(filename, f)
    url = supabase.storage.from_('receipts').get_public_url(filename)
    # insert record
    supabase.table('receipts').insert({
        'user_id': user_id,
        'amount': fields['amount'],
        'date': fields['date'],
        'city': fields['city'],
        'image_url': url
    }).execute()


@bot.event
async def on_ready():
    print(f"Bot is ready. Logged in as {bot.user}")


@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send("📎 Upload receipt image(s) now.")


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return
    if bot.user.mentioned_in(message):
        await message.channel.send("👋 Mention me? Use `!upload`.")
    if message.attachments:
        for attachment in message.attachments:
            if not attachment.filename.lower().endswith((".jpg", ".jpeg")):
                continue
            await message.channel.send(f"📥 Processing {attachment.filename}...")
            path = f"temp_{attachment.filename}"
            await attachment.save(path)
            try:
                text = pytesseract.image_to_string(Image.open(path))
                fields = extract_fields(text)
                if not all(fields.values()):
                    await message.channel.send("❌ Invalid receipt. Upload a valid one.")
                    os.remove(path)
                    return
                status = "Genuine"
                await message.channel.send(
                    f"🧾 {attachment.filename} — **{status}**\n"
                    f"- Amount: {fields['amount']}\n"
                    f"- Date: {fields['date']}\n"
                    f"- City: {fields['city']}"
                )
                # collect employee info
                keys = ['Employee ID','Expense Amount','Date','City']
                answers = {}
                for idx, label in enumerate(keys,1):
                    await message.channel.send(f"{idx}. {label}? (or 'Cancel')")
                    resp = await bot.wait_for('message', check=lambda m: m.author==message.author)
                    if resp.content.lower()=='cancel':
                        await message.channel.send("🚫 Cancelled.")
                        os.remove(path)
                        return
                    answers[label] = resp.content.strip()
                # save to DB
                save_receipt(message.author.id, fields, path)
                await message.channel.send("✅ Saved to database!")
            except Exception as e:
                await message.channel.send(f"❌ Error: {e}")
            finally:
                if os.path.exists(path):
                    os.remove(path)

bot.run(DISCORD_BOT_TOKEN)