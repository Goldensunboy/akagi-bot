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
        
        image_urls = self.extract_image_urls_from_message(msg)
        if not image_urls:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any images in that message's embeds or attachments.")
            return

        await self.get_img_from_urls(ctx, image_urls)

    # Use a number to look back through recent messages with embeds
    async def get_img_from_history(self, ctx: commands.Context, lookback: int):
        self.logger.info(f"Fetching image from history, lookback: {lookback}")

        if lookback < 1 or lookback > 10:
            await ctx.send("Shikikan, please provide a number of recent embed messages between 1 and 10.")
            return

        found = []
        try:
            async for msg in ctx.channel.history(limit=1000, oldest_first=False):
                if self.extract_image_urls_from_message(msg):
                    found.append(msg)
                    if len(found) >= lookback:
                        break
        except discord.Forbidden:
            self.logger.error(f"Missing permission to read message history in channel ID: {ctx.channel.id}")
            await ctx.send("I'm sorry Shikikan, but I don't have permission to read message history in this channel.")
            return
        except discord.HTTPException as e:
            self.logger.error(f"Error reading message history in channel ID: {ctx.channel.id}, error: {e}")
            await ctx.send("I'm sorry Shikikan, but I ran into an error while reading recent messages.")
            return

        if not found:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any recent messages with images in embeds or attachments.")
            return
        
        # Collect image URLs from found messages
        image_urls = []
        for message in found:
            image_urls.extend(self.extract_image_urls_from_message(message))
        if len(image_urls) > 10:
            image_urls = image_urls[:10]

        if not image_urls:
            await ctx.send("I'm sorry Shikikan, but I couldn't find any images in the recent messages.")
            return
        
        await self.get_img_from_urls(ctx, image_urls)

    def extract_image_urls_from_message(self, msg: discord.Message) -> list:
        image_urls = []

        for embed in msg.embeds:
            if embed.image and embed.image.url:
                image_urls.append(embed.image.url)
            if embed.thumbnail and embed.thumbnail.url:
                image_urls.append(embed.thumbnail.url)

        for attachment in msg.attachments:
            is_image_content_type = attachment.content_type is not None and attachment.content_type.startswith("image/")
            is_image_filename = attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
            if is_image_content_type or is_image_filename:
                image_urls.append(attachment.url)

        return image_urls

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
        pattern = r"https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)(?:[/?#].*)?$"
        match = re.match(pattern, url)
        if not match:
            self.logger.error(f"Invalid Discord message URL: {url}")
            return None
        guild_id, channel_id, message_id = match.groups() 

        guild = ctx.bot.get_guild(int(guild_id))
        if not guild:
            try:
                guild = await ctx.bot.fetch_guild(int(guild_id))
            except discord.NotFound:
                self.logger.error(f"Guild not found for ID: {guild_id}")
                return None
            except discord.Forbidden:
                self.logger.error(f"Missing permission to fetch guild for ID: {guild_id}")
                return None
            except discord.HTTPException as e:
                self.logger.error(f"Error fetching guild from ID: {guild_id}, error: {e}")
                return None
            
        channel_id_int = int(channel_id)
        channel = guild.get_channel(channel_id_int)
        if channel is None and hasattr(guild, "get_thread"):
            channel = guild.get_thread(channel_id_int)
        if channel is None:
            try:
                channel = await ctx.bot.fetch_channel(channel_id_int)
            except discord.NotFound:
                self.logger.error(f"Channel not found for ID: {channel_id}")
                return None
            except discord.Forbidden:
                self.logger.error(f"Missing permission to fetch channel for ID: {channel_id}")
                return None
            except discord.HTTPException as e:
                self.logger.error(f"Error fetching channel from ID: {channel_id}, error: {e}")
                return None

        if not channel:
            self.logger.error(f"Channel not found for ID: {channel_id}")
            return None
        try:
            message = await channel.fetch_message(int(message_id))
            return message
        except discord.NotFound:
            self.logger.error(f"Message not found for ID: {message_id}")
            return None
        except discord.Forbidden:
            self.logger.error(f"Missing permission to fetch message for ID: {message_id}")
            return None
        except discord.HTTPException as e:
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