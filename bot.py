import io
import json
import os
import asyncio
import base64

import requests
import discord
from dotenv import load_dotenv


load_dotenv()

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

token = os.getenv("DISCORD_TOKEN")
base_url = os.getenv("AUTOMATIC1111_URL")

user_image_count = {}

EXCLUDED_GUILDS = []  # here put names of guilds you want to exclude from checking limits
MAX_WALLPAPER_GENERATION_PER_DAY = 10


if not os.path.exists("outputs"):
    os.makedirs("outputs")


def generate_images(prompt, width=1024, height=1024):
    url = f"{base_url}/sdapi/v1/txt2img"
    headers = {"Content-type": "application/json"}

    hiresfix = False
    if width > 1280 or height > 1280:
        hiresfix = True
        width = width // 2
        height = height // 2

    data = {
        "prompt": prompt,
        "batch_size": 1,
        "width": width,
        "height": height,
        "enable_hr": hiresfix,
        "hr_scale": 2,
        "hr_upscaler": "4x-UltraSharp",
        "cfg_scale": 5,
        "steps": 20,
        "sampler_name": "Euler a",
        "negative_prompt": "",
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        json_data = response.json()
        image_data = json_data["images"][0]

        max_index = 0
        for filename in os.listdir("outputs"):
            if filename.startswith("image_") and filename.endswith(".png"):
                index = int(filename[6:-4])
                if index > max_index:
                    max_index = index

        img_bytes = base64.b64decode(image_data)
        img_path = f"./outputs/image_{max_index + 1}.png"
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        return img_path


if os.path.isfile("wallpaper_sizes.json") and os.path.getsize("wallpaper_sizes.json") > 0:
    with open("wallpaper_sizes.json", "r") as f:
        wallpaper_sizes = json.load(f)
else:
    wallpaper_sizes = {}


@client.event
async def on_message(message):
    user_id = str(message.author.id)

    if message.author == client.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        await message.channel.send("Don't be shy. Create in common channels.")
        return

    if client.user.mentioned_in(message) and message.mention_everyone is False:
        prompt = message.content.replace(f"<@{client.user.id}>", "").strip()
        if prompt.strip().startswith("SET_WALLPAPER_SIZE="):
            wallpaper_size = message.content.split("=")[1]
            wallpaper_sizes[user_id] = wallpaper_size

            with open("wallpaper_sizes.json", "w") as f:
                json.dump(wallpaper_sizes, f)

            await message.channel.send(f"Set wallpaper size for user {message.author.name} to {wallpaper_size}")
            return

        if message.guild.name not in EXCLUDED_GUILDS:
            if user_id in user_image_count:
                if user_image_count[user_id] >= MAX_WALLPAPER_GENERATION_PER_DAY:
                    await message.channel.send("Sorry, you have reached your image generation limit for the day.")
                    return

        wallpaper_size = wallpaper_sizes.get(user_id)
        if wallpaper_size:
            width, height = wallpaper_sizes.get(user_id).split("x")
            width, height = int(width), int(height)
            if width > 3088 or height > 3088:
                await message.channel.send("Whoa there, that's too big. Try something smaller.")
                return
        else:
            width, height = 1024, 1024
            await message.channel.send("Remember to set your wallpaper size with `SET_WALLPAPER_SIZE=widthxheight`.")
        await asyncio.create_task(generate_and_send_images(message, prompt, width, height))

        if user_id in user_image_count:
            user_image_count[user_id] += 1
        else:
            user_image_count[user_id] = 1

        asyncio.create_task(remove_user_count_after_24h(user_id))


async def generate_and_send_images(message, prompt, width, height):
    img_path = generate_images(prompt, width, height)

    with open(img_path, "rb") as f:
        file_content = f.read()
    filename = os.path.basename(img_path)
    await message.channel.send("", file=discord.File(io.BytesIO(file_content), filename))


async def remove_user_count_after_24h(user_id):
    await asyncio.sleep(86400)
    user_image_count.pop(user_id, None)


client.run(token)
