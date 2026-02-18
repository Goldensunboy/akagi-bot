import discord, asyncio, sys, logging, requests, traceback, re
from discord.ext import commands
from get_image import GetImage
from minecraft_connector import MinecraftConnector

#===================================================================================
#=== Static definitions ============================================================
#===================================================================================

# Role and channel IDs
MOD_ROLE_ID = 803579561362063390
ROLE_JARI_ID = 566355710670012533
LOG_CHANNEL_ID = 638208991587205120

# Age roles
ROLE_SS = 705783318246850812
ROLE_DD = 703260124621570074
ROLE_CL = 703259878206078976
ROLE_CV = 703259629018284092
ROLE_BB = 717611783614890006

# Commodore color roles
ROLE_COMMODORE = 1183790559324807258
COLOR_ROLES = {
    "grey": 1216455609709363281,
    "purple": 1216455321396973598,
    "yellow": 1216454050912931981,
    "red": 1216454500425007307,
    "cyan": 1216454226650206258,
    "blue": 1216454278613307563,
    "green": 1216454315015671808
}

BOT_ADMINS = [
    188646158636285952, # crocdent
    202142045114990592  # goldensunboy
]

DISCORD_MESSAGE_URL_PATTERN = re.compile(
    r"^<?https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/\d+/\d+/\d+(?:[/?#].*)?>?$",
    re.IGNORECASE,
)

#===================================================================================
#=== Environment configuration =====================================================
#===================================================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

token_file = 'prod-token.txt'
if len(sys.argv) == 2:
    token_file = sys.argv[1] # Allow token file override E.G. running against a PPE env

bot = commands.Bot(command_prefix='a!', intents=intents, help_command=None)

get_img = GetImage(logger)
mc_connector = MinecraftConnector(bot, logger)

#===================================================================================
#=== Core command code =============================================================
#===================================================================================

class LoggingWrapper(commands.Command):
    async def invoke(self, ctx):
        logger.info(f"User {ctx.author} invoked command '{ctx.message.content}'")
        try:
            await super().invoke(ctx)
        except Exception as e:
            st = traceback.format_exc()
            await ctx.send(f"Oh dear, Shikikan-sama... I seem to have tripped while trying to service your request. I'm so sorry! Here are some details which might be of use:\n```{e}\n{st}```")

@bot.event
async def on_ready():
    logger.info(f'Bot is online as {bot.user}')

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.lower()

    if content.startswith(".iam jari squad"):
        await handle_jari_command(message)
    elif content.startswith(".iamnot jari squad") or content.startswith(".iamn jari squad"):
        role = message.guild.get_role(ROLE_JARI_ID)
        await message.author.remove_roles(role)
        await message.channel.send("Your Jari role has been removed, Shikikan.")

    await bot.process_commands(message)

async def handle_jari_command(message: discord.Message):
    member = message.author
    roles = member.roles
    guild = message.guild
    jari_role = guild.get_role(ROLE_JARI_ID)

    if any(role.id in [ROLE_CL, ROLE_CV, ROLE_BB] for role in roles):
        await member.add_roles(jari_role)
        await message.channel.send("Looks like you are old enough Shikikan, here is your Jari role.")
    elif any(role.id in [ROLE_DD, ROLE_SS] for role in roles):
        await message.channel.send("Sorry Shikikan, you aren't old enough. Atago may be interested in you, though...")
    else:
        await message.channel.send("Sorry Shikikan, but you don't have the age role yet. Complete the birthyear form, or wait if you have.")

@bot.command(cls=LoggingWrapper)
async def help(ctx: commands.Context):
    await ctx.send("My current commands are: mute, color")

@bot.command(cls=LoggingWrapper)
async def mute(ctx: commands.Context, member: discord.Member = None, minutes: int = None):
    if not (ctx.author.guild_permissions.administrator or MOD_ROLE_ID in [role.id for role in ctx.author.roles]):
        await ctx.send("Sorry Shikikan, but you aren't allowed to use this command.")
        return

    if not member or not minutes:
        await ctx.send("Shikikan, you need to mention a user and provide a duration!")
        return

    if minutes < 1:
        await ctx.send("Shikikan, are you making fun of me...?")
        return

    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    await member.add_roles(mute_role)
    await ctx.send(f"Fufufu~ The troublemaker has been muted for {minutes} minute(s) as instructed, Shikikan~")
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    await log_channel.send(f"{member.name} has been muted for {minutes} minutes by moderator {ctx.author.name}.")

    await asyncio.sleep(minutes * 60)
    await member.remove_roles(mute_role)
    await log_channel.send(f"{member.name} has been unmuted.")

@bot.command(cls=LoggingWrapper)
async def color(ctx: commands.Context, color_name: str = None):
    member = ctx.author
    if ROLE_COMMODORE not in [role.id for role in member.roles]:
        await ctx.send("Sorry Shikikan, but only Commodore can change color.")
        return

    if not color_name:
        await ctx.send("Shikikan, you need to tell me which color you want.")
        return

    color_name = color_name.lower()
    if color_name not in COLOR_ROLES:
        await ctx.send("Sorry Shikikan, I do not recognize that color.")
        return

    # Remove all color roles
    for role_id in COLOR_ROLES.values():
        role = ctx.guild.get_role(role_id)
        await member.remove_roles(role)

    # Add selected color role
    new_role = ctx.guild.get_role(COLOR_ROLES[color_name])
    await member.add_roles(new_role)
    await ctx.send("There you go Shikikan, you look great in that color!")

@bot.command(cls=LoggingWrapper)
async def host(ctx: commands.Context):
    if ctx.guild is not None:
        return # this command can only be used in a DM
    if ctx.author.id not in BOT_ADMINS:
        await ctx.send("Sorry Shikikan, but you aren't allowed to use this command.")
        return
    
    response = requests.get("https://api.ipify.org/")
    if response.status_code == 200:
        ip = response.text
        await ctx.send(f"Shikikan, I am currently located at: {ip}")

@bot.command(cls=LoggingWrapper)
async def get(ctx: commands.Context, arg = None):
    if arg is None:
        await ctx.send("Shikikan, you need to tell me which message to get, or how many recent embeds to retrieve.")
    elif arg.isdigit():
        value = int(arg)
        await get_img.get_img_from_history(ctx, value)
    else:
        normalized_arg = arg.strip()
        if DISCORD_MESSAGE_URL_PATTERN.match(normalized_arg):
            normalized_arg = normalized_arg.removeprefix("<").removesuffix(">")
            await get_img.get_img_from_message_link(ctx, normalized_arg)
        else:
            await ctx.send("Shikikan, I don't understand your request.")

#===================================================================================
#=== Run the bot ===================================================================
#===================================================================================

# Load bot token from a local file
def load_token(filepath=token_file):
    try:
        with open(filepath, 'r') as file:
            return file.read().strip()
    except FileNotFoundError:
        logger.error(f"Error: File '{filepath}' not found.")

# Replace with your bot token
bot.run(load_token())