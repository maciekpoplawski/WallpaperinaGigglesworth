import logging
import os
import json
import base64
import asyncio

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import make_response
from slack_bolt import App
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(level=logging.DEBUG)

app = App()

slack_web_client = WebClient(token=os.getenv("SLACK_TOKEN"))

base_url = os.getenv("AUTOMATIC1111_URL")
user_image_count = {}

EXCLUDED_CHANNELS = []  # here put names of channels you want to exclude from checking limits
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


@app.event("app_mention")
def event_test(body, say, logger):
    logger.info(body)
    handle_mention(body, say)


def handle_mention(body, say):
    print("entered handle_mention")
    channel_id = body.get("event").get("channel")
    user_id = body.get("event").get("user")
    text = body.get("event").get("text")

    prompt = text.split(">")[1].strip()

    if prompt.startswith("SET_WALLPAPER_SIZE="):
        wallpaper_size = prompt.split("=")[1]
        wallpaper_sizes[user_id] = wallpaper_size

        with open("wallpaper_sizes.json", "w") as f:
            json.dump(wallpaper_sizes, f)

        say(f"Set wallpaper size for user {user_id} to {wallpaper_size}")
        return make_response("", 200)

    if channel_id not in EXCLUDED_CHANNELS:
        if user_id in user_image_count:
            if user_image_count[user_id] >= MAX_WALLPAPER_GENERATION_PER_DAY:
                say("Sorry, you have reached your image generation limit for the day.")
                return make_response("", 200)

    wallpaper_size = wallpaper_sizes.get(user_id)
    if wallpaper_size:
        width, height = wallpaper_sizes.get(user_id).split("x")
        width, height = int(width), int(height)
        if width > 3088 or height > 3088:
            say("Whoa there, that's too big. Try something smaller.")
            return make_response("", 200)
    else:
        width, height = 1024, 1024
        say("Remember to set your wallpaper size with `SET_WALLPAPER_SIZE=widthxheight`.")
    generate_and_send_images(channel_id, text, width, height)

    if user_id in user_image_count:
        user_image_count[user_id] += 1
    else:
        user_image_count[user_id] = 1

    # asyncio.ensure_future(remove_user_count_after_24h(user_id))

    return make_response("", 200)


def send_message(channel_id, message):
    try:
        slack_web_client.chat_postMessage(channel=channel_id, text=message)
    except SlackApiError as e:
        print(f"Error: {e}")


def generate_and_send_images(channel_id, prompt, width, height):
    print("entered generating image!")
    img_path = generate_images(prompt, width, height)

    try:
        slack_web_client.files_upload(channels=channel_id, file=img_path)
    except SlackApiError as e:
        print(f"Error: {e}")


async def remove_user_count_after_24h(user_id):
    await asyncio.sleep(86400)
    user_image_count.pop(user_id, None)


if __name__ == "__main__":
    app.start(3000)
