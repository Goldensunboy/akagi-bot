import glob, os, json, flask, requests, threading, time, logging, asyncio, queue
from logging import Logger
from urllib3.exceptions import ConnectTimeoutError

##############################################################
####   Static functions   ####################################
##############################################################

props_file_pattern = 'minecraft_connector_props*.json'

'''
Attributes from all matching properties files are coalesced,
as well as shared and role-specific sections.
'''
def load_props(role: str, logger: Logger):
    props_files = glob.glob(props_file_pattern)
    combined_props = {}
    for pf in props_files:
        logger.info(f"Loading Minecraft connector properties from {pf}")
        with open(pf, 'r') as f:
            file_props = json.load(f)
            shared_props = file_props.get("shared", {})
            role_props = file_props.get(role, {})
            combined_props.update(shared_props)
            combined_props.update(role_props)
    return combined_props

##############################################################
####   Client-side connector (runs on akagi-bot)   ###########
##############################################################

class MinecraftConnector:

    def __init__(self, bot, logger: Logger):
        self.bot = bot
        self.logger = logger
        self.client_props = self.load_client_props()
        self.http_client = self.create_client()
        self.configure_cron_job(self.client_props["update_interval_seconds"])

    '''
    Load Minecraft server connection properties
      Put public attributes in a committed file matching the props_file_pattern
      Put private attributes in a .gitignored file matching the props_file_pattern
      Attributes are coalesced from all matching files, with later files overriding earlier ones
    '''
    def load_client_props(self):
        props = load_props("client", self.logger)
        for key in ["server_host", "server_port", "auth_token", "announcement_channel_id", "update_interval_seconds"]:
            if key not in props:
                msg = f"Missing required Minecraft connector client property: {key}"
                self.logger.error(msg)
                raise ValueError(msg)
        return props
    
    '''
    Create and configure the HTTP client for communicating with the Minecraft server connector
    '''
    def create_client(self):
        return ConfiguredHTTPClient(
            host=self.client_props["server_host"],
            port=self.client_props["server_port"],
            auth_token=self.client_props["auth_token"],
            logger=self.logger
        )
    
    '''
    Configure a cron job to periodically fetch new advancement messages from the server connector
    '''
    def configure_cron_job(self, interval_seconds: int):
        def run_periodically():
            while True:
                time.sleep(interval_seconds)
                self.cron_job_worker()
        thread = threading.Thread(target=run_periodically, daemon=True)
        thread.start()
        self.logger.info(f"Started background cron job with {interval_seconds}s interval")

    '''
    Worker function for the cron job to fetch and send new advancement messages
    to the designated Discord channel
    '''
    def cron_job_worker(self):
        msgs = self.get_messages()
        if len(msgs) > 0:
            msg = "Shikikan, " + "\n".join([f'{m}!' for m in msgs])
            self.logger.info(msg)
            channel_id = self.client_props["announcement_channel_id"]
            asyncio.run_coroutine_threadsafe(
                self.send_to_channel(channel_id, msg),
                self.bot.loop
            )

    async def send_to_channel(self, channel_id: int, message: str):
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
        else:
            self.logger.error(f"Could not find channel with ID {channel_id}")
        
    '''
    Unwraps message list from the server connector's JSON response
    '''
    def get_messages(self):
        resp = self.http_client.get("messages")
        if resp is not None:
            return resp.get("messages", [])
        else:
            return []

class ConfiguredHTTPClient:
    def __init__(self, host: str, port: int, auth_token: str, logger: Logger):
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.logger = logger

    '''
    Perform a GET request to the specified endpoint
    self.auth_token is included in the Authorization header to act as a symmetric key
    '''
    def get(self, endpoint: str):
        try:
            response = requests.get(f"http://{self.host}:{self.port}/{endpoint}", headers={"Authorization": self.auth_token}, timeout=5)
        except ConnectTimeoutError:
            self.logger.warning(f"Minecraft server connector not detected at {self.host}:{self.port} (timed out)")
            return None
        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error(f"HTTP GET request to {endpoint} failed with status code {response.status_code}")
            return None

##############################################################
####   Server-side connector (runs on server.pro)   ##########
##############################################################

first_time_announcements = {
    "minecraft:story/mine_diamond": "Diamonds!",
    "minecraft:story/enter_the_nether": "We Need to Go Deeper",
    "minecraft:story/shiny_gear": "Cover Me with Diamonds",
    "minecraft:story/follow_ender_eye": "Eye Spy",
    "minecraft:story/enter_the_end": "The End?",
    "minecraft:nether/obtain_ancient_debris": "Hidden in the Depths",
    "minecraft:nether/find_fortress": "A Terrible Fortress",
    "minecraft:nether/get_wither_skull": "Spooky Scary Skeleton",
    "minecraft:nether/explore_nether": "Hot Tourist Destinations",
    "minecraft:nether/create_beacon": "Bring Home the Beacon",
    "minecraft:end/kill_dragon": "Free the End",
    "minecraft:end/find_end_city": "The City at the End of the Game",
    "minecraft:adventure/hero_of_the_village": "Hero of the Village",
    "minecraft:adventure/totem_of_undying": "Postmortal",
    "minecraft:adventure/sniper_duel": "Sniper Duel",
    "minecraft:husbandry/silk_touch_nest": "Total Beelocation",
    "minecraft:husbandry/obtain_netherite_hoe": "Serious Dedication",
    "minecraft:end/elytra": "Sky's the Limit"
}

always_announcements = {
    "minecraft:nether/uneasy_alliance": "Uneasy Alliance",
    "minecraft:nether/netherite_armor": "Cover Me in Debris",
    "minecraft:nether/summon_wither": "Withering Heights",
    "minecraft:nether/all_potions": "A Furious Cocktail",
    "minecraft:nether/all_effects": "How Did We Get Here?",
    "minecraft:adventure/kill_all_mobs": "Monsters Hunted",
    "minecraft:adventure/arbalistic": "Arbalistic",
    "minecraft:adventure/adventuring_time": "Adventuring Time",
    "minecraft:adventure/very_very_frightening": "Very Very Frightening",
    "minecraft:husbandry/bred_all_animals": "Two by Two",
    "minecraft:husbandry/complete_catalogue": "A Complete Catalogue",
    "minecraft:husbandry/balanced_diet": "A Balanced Diet"
}

class MinecraftConnectorServer:

    def __init__(self, logger: Logger):
        self.logger = logger
        self.server_props = self.load_server_props()
        self.app = flask.Flask(__name__)
        
        self.get_initial_advancement_messages()
        self.configure_cron_job(self.server_props["update_interval_seconds"])
        self.setup_routes()

    '''
    Load Minecraft server properties
      Put public attributes in a committed file matching the props_file_pattern
      Put private attributes in a .gitignored file matching the props_file_pattern
    '''
    def load_server_props(self):
        props = load_props("server", self.logger)
        for key in ["minecraft_world_name", "minecraft_home", "auth_token", "update_interval_seconds"]:
            if key not in props:
                msg = f"Missing required Minecraft connector server property: {key}"
                self.logger.error(msg)
                raise ValueError(msg)
        return props

    '''
    Load player names from whitelist JSON file to map UUIDs to names in advancement messages
    '''
    def load_player_names(self) -> dict:
        whitelist_path = os.path.join(self.server_props["minecraft_home"], "whitelist.json")
        if os.path.exists(whitelist_path):
            with open(whitelist_path, 'r') as f:
                whitelist = json.load(f)
                mapping = {entry["uuid"]: entry["name"] for entry in whitelist}
                self.logger.info(f"Loaded {len(mapping)} player names from whitelist")
                return mapping
        else:
            self.logger.warning(f"Whitelist file not found at {whitelist_path}, player names will not be resolved")
            return {}
    
    '''
    Load the list of advancements achieved by a player from their advancements JSON file
    '''
    def get_advancement_list(self, player_uuid: str) -> list:
        advancements_path = os.path.join(self.server_props["minecraft_home"], self.server_props["minecraft_world_name"], "advancements", f"{player_uuid}.json")
        announcement_whitelist = set(first_time_announcements).union(set(always_announcements))
        if os.path.exists(advancements_path):
            with open(advancements_path, 'r') as f:
                data = json.load(f)
                return [k for k in data if k in announcement_whitelist and data[k].get("done", False)]
        else:
            self.logger.warning(f"Advancement file not found for player {player_uuid} at {advancements_path}")
            return []

    '''
    Initialize data structures for storing advancement messages
    The baseline set of messages is established at startup to avoid reporting old messages
    '''
    def get_initial_advancement_messages(self):
        self.msg_mutex = threading.Lock()
        self.messages = queue.Queue()
        self.player_advancements = {}
        self.player_names = {}
        self.already_achieved = set()

        # Populate initial advancement lists for all players by reading advancements files, and store player names from whitelist
        advancements_dir = os.path.join(self.server_props["minecraft_home"], self.server_props["minecraft_world_name"], "advancements")
        if os.path.exists(advancements_dir):
            for filename in os.listdir(advancements_dir):
                if filename.endswith(".json"):
                    player_uuid = filename[:-5]
                    self.player_advancements[player_uuid] = set(self.get_advancement_list(player_uuid))
                    self.already_achieved.update(self.player_advancements[player_uuid])
        else:
            self.logger.warning(f"Advancements directory not found at {advancements_dir}, no baseline will be established and all advancements will be reported as new on startup")
        self.logger.info(f"Initial advancement messages established, {len(self.already_achieved)} advancements already achieved by players at startup")

        self.get_new_advancement_messages()

    '''
    Configure a cron job to periodically fetch new advancement messages from the world files
    '''
    def configure_cron_job(self, interval_seconds: int):
        def run_periodically():
            while True:
                time.sleep(interval_seconds)
                self.get_new_advancement_messages()
        thread = threading.Thread(target=run_periodically, daemon=True)
        thread.start()
        self.logger.info(f"Started background cron job with {interval_seconds}s interval")

    '''
    Worker function for the cron job to to update the advancement message list
    with new messages from the Minecraft world files
    '''
    def get_new_advancement_messages(self):
        self.player_names = self.load_player_names()
        advancements_dir = os.path.join(self.server_props["minecraft_home"], self.server_props["minecraft_world_name"], "advancements")
        if os.path.exists(advancements_dir):
            for filename in os.listdir(advancements_dir):
                if filename.endswith(".json"):

                    # Get list of new advancements for this player by comparing current advancements in file to previously stored advancements
                    player_uuid = filename[:-5]
                    player_name = self.player_names.get(player_uuid, player_uuid)
                    current_advancements = set(self.get_advancement_list(player_uuid))
                    previous_advancements = set(self.player_advancements.get(player_uuid, set()))
                    new_advancements = current_advancements - previous_advancements

                    self.logger.info(f"Player {player_name} has {len(new_advancements)} new advancements since last check")

                    # Create messages for any new advancements and add them to the queue, then update stored advancements for this player
                    for adv in new_advancements:
                        first_or_not_text = "is the first player to make"
                        if adv in first_time_announcements:
                            if adv not in self.already_achieved:
                                self.msg_mutex.acquire()
                                try:
                                    msg = f"{player_name} {first_or_not_text} the advancement [{first_time_announcements[adv]}]"
                                    self.logger.info(f"Queuing new advancement message: {msg}")
                                    self.messages.put(msg)
                                finally:
                                    self.msg_mutex.release()
                                self.already_achieved.add(adv)
                        elif adv in always_announcements:
                            if adv in self.already_achieved:
                                first_or_not_text = "has made"
                            self.msg_mutex.acquire()
                            try:
                                msg = f"{player_name} {first_or_not_text} the advancement [{always_announcements[adv]}]"
                                self.logger.info(f"Queuing new advancement message: {msg}")
                                self.messages.put(msg)
                            finally:
                                self.msg_mutex.release()
                            self.already_achieved.add(adv)
                        else:
                            self.logger.warning(f"Advancement {adv} is not in either announcement list, skipping")
                    self.player_advancements[player_uuid] = current_advancements
        else:
            self.logger.warning(f"Advancements directory not found at {advancements_dir}, no messages will be generated")
    
    '''
    Setup Flask routes for the HTTP server
      messages: GET - fetch all queued advancement messages
    '''
    def setup_routes(self):

        @self.app.route("/messages", methods=["GET"])
        def get_messages():
            auth_header = flask.request.headers.get("Authorization")
            if auth_header != self.server_props["auth_token"]:
                return flask.jsonify({"error": "Unauthorized"}), 401
            
            messages = self.fetch_messages()
            return flask.jsonify({"messages": messages})

    '''
    Helper to fetch and return all queued advancement messages in a threadsafe manner
    '''
    def fetch_messages(self):
        messages = []
        self.msg_mutex.acquire()
        try:
            while not self.messages.empty():
                try:
                    messages.append(self.messages.get_nowait())
                except queue.Empty:
                    break
        finally:
            self.msg_mutex.release()
        return messages

#===================================================================================
####   Server entry point   ########################################################
#===================================================================================

if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not logger.hasHandlers():
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    server = MinecraftConnectorServer(logger)
    server.app.run(host="0.0.0.0", port=8080)