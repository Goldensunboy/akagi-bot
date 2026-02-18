import requests, re, discord, io
from logging import Logger
from discord.ext import commands

class GetImage:
    def __init__(self, logger: Logger):
        self.logger = logger

    # Use a link to a specific message to retrieve and reupload its embeds
    async def get_img_from_message_link(self, ctx: commands.Context, url: str):
        self.logger.info(f"Fetching message from URL: {url}")
        msg = await self.get_message_from_url(ctx, url)

        if msg is None:
            await ctx.send("I'm sorry Shikikan, but I couldn't find that message.")
            return
        
        embeds = msg.embeds

        #========== TESTING

        self.logger.debug(f"Embeds found in message: {len(embeds)}")
        for e in embeds:
            self.logger.debug(f"Embed: title={e.title}, image_url={e.image.url if e.image else 'None'}")

        #==================

        image_urls = [e.image.url for e in embeds if e.image is not None and e.image.url is not None]
        if not image_urls:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any images in that message.")
            return

        await self.get_img_from_urls(ctx, image_urls)

    # Use a number to look back through recent messages with embeds
    async def get_img_from_history(self, ctx: commands.Context, lookback: int):
        self.logger.info(f"Fetching image from history, lookback: {lookback}")

        if lookback < 1 or lookback > 10:
            await ctx.send("Shikikan, please provide a number of recent embed messages between 1 and 10.")
            return

        found = []
        async for msg in ctx.channel.history(limit=1000):
            if msg.embeds:
                found.append(msg)
                if len(found) >= lookback:
                    break

        if not found:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any messages with embeds posted recently.")
            return
        
        # Collect image URLs from embeds
        image_urls = []
        for message in found:
            for embed in message.embeds:
                if embed.image and embed.image.url:
                    image_urls.append(embed.image.url)
        if len(image_urls) > 10:
            image_urls = image_urls[:10]

        if not image_urls:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any images in the embeds.")
            return
        
        await self.get_img_from_urls(ctx, image_urls)

    # Helper to download images and reupload them with a message
    async def get_img_from_urls(self, ctx: commands.Context, urls: list):
        self.logger.info(f"Fetching images from URLs: {urls}")

        images = []
        n = 0
        for url in urls:
            content = await self.download_image(url)
            if content:
                images.append(discord.File(io.BytesIO(content), filename=f"image{n}.png"))
                n += 1

        if not images:
            await ctx.send("I'm sorry Shikikan, but I couldn't download any images.")
            return
        
        plural_msg = f"{len(images)} images" if len(images) > 1 else "the image"
        await ctx.send(f"Shikikan-sama, I have retrieved {plural_msg} for you.", files=images)

    # Helper to get a message object from a Discord message URL
    async def get_message_from_url(self, ctx: commands.Context, url: str) -> discord.Message:
        pattern = r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)"
        match = re.match(pattern, url)
        if not match:
            self.logger.error(f"Invalid Discord message URL: {url}")
            return None
        guild_id, channel_id, message_id = match.groups()
        guild = ctx.bot.get_guild(int(guild_id))
        if not guild:
            self.logger.error(f"Guild not found for ID: {guild_id}")
            return None
        channel = guild.get_channel(int(channel_id))
        if not channel:
            self.logger.error(f"Channel not found for ID: {channel_id}")
            return None
        try:
            message = await channel.fetch_message(int(message_id))
            return message
        except Exception as e:
            self.logger.error(f"Error fetching message from id: {message_id}, error: {e}")
            return None
    
    # Helper to download an image from a URL
    async def download_image(self, url: str) -> bytes:
        self.logger.info(f"Downloading image from URL: {url}")
        response = requests.get(url)
        if response.status_code == 200:
            return response.content
        else:
            self.logger.error(f"Failed to download image from {url}. Status code: {response.status_code}")
            return None