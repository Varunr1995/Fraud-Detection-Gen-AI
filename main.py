import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils import (
    extract_text_from_image,
    extract_amount,
    extract_date,
    extract_city,
    generate_summary_with_qwen,
    generate_json_from_receipt,
    generate_llm_answer
)
from db_init import init_db, get_connection

# === Load environment variables ===
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# === Initialize DB ===
init_db()

# === Discord Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"🤖 Bot is ready. Logged in as {bot.user}")


@bot.command(name="upload")
async def upload_receipt(ctx):
    await ctx.send("📎 Please upload your receipt image(s) (JPG/JPEG). You can upload multiple.")


@bot.command(name="summarize")
async def summarize_receipt(ctx):
    await ctx.send("📎 Upload the receipt image you want to summarize (JPG/JPEG).")


@bot.command(name="jsonify")
async def jsonify_receipt(ctx):
    await ctx.send("📎 Upload the receipt image to extract structured JSON data.")


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.author.bot:
        return

    if bot.user.mentioned_in(message):
        await message.channel.send("👋 Need to verify a receipt? Use `!upload`, `!summarize`, or `!jsonify`.")

    if message.attachments:
        for att in message.attachments:
            if not att.filename.lower().endswith((".jpg", ".jpeg")):
                continue

            await message.channel.send(f"📥 Processing **{att.filename}**...")
            path = f"temp_{att.filename}"
            await att.save(path)

            try:
                # Extract text via OCR
                text = extract_text_from_image(path)
                print("\n===== OCR TEXT =====\n", text, "\n===================\n")

                # Handle !summarize
                if message.content.startswith("!summarize"):
                    summary = await generate_summary_with_qwen(text)
                    await message.channel.send(f"🧾 **{att.filename}** — Summary:\n> {summary}")
                    continue

                # Handle !jsonify
                elif message.content.startswith("!jsonify"):
                    json_output = await generate_json_from_receipt(text)
                    await message.channel.send(f"🧾 **{att.filename}** — Extracted JSON:\n```json\n{json_output}\n```")
                    continue

                # Handle !upload (default)
                amount = extract_amount(text)
                date = extract_date(text)
                city = extract_city(text)

                # Check for missing fields
                if not all([amount, date, city]):
                    missing = []
                    if not amount: missing.append("amount")
                    if not date: missing.append("date")
                    if not city: missing.append("city")
                    await message.channel.send(f"❌ Could not extract: {', '.join(missing)}")
                    continue

                # Respond with result
                await message.channel.send(
                    f"🧾 **{att.filename}** — Verified ✅\n"
                    f"- Amount: {amount}\n"
                    f"- Date: {date}\n"
                    f"- City: {city}"
                )

                # Save to DB
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO receipts (user_id, amount, date, city, image_path) VALUES (?,?,?,?,?)",
                        (str(message.author.id), amount, date, city, path)
                    )
                    conn.commit()
                    conn.close()
                    await message.channel.send("✅ Receipt saved to local database!")
                except Exception as db_err:
                    await message.channel.send(f"❌ Failed to save to DB: {db_err}")

            except Exception as e:
                await message.channel.send(f"❌ Error: {e}")

            finally:
                if os.path.exists(path):
                    os.remove(path)


# === Run the bot ===
bot.run(DISCORD_BOT_TOKEN)
