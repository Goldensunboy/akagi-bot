import path, json, flask, requests, threading, time, asyncio, queue
from logging import Logger

##############################################################
####   Static functions   ####################################
##############################################################

props_file_pattern = 'minecraft_connector_props*.json'

'''
Attributes from all matching properties files are coalesced,
as well as shared and role-specific sections.
'''
def load_props(role: str, logger: Logger):
    props_files = path.glob(props_file_pattern)
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
        response = requests.get(f"http://{self.host}:{self.port}/{endpoint}", headers={"Authorization": self.auth_token})
        if response.status_code == 200:
            return response.json()
        else:
            self.logger.error(f"HTTP GET request to {endpoint} failed with status code {response.status_code}")
            return None

##############################################################
####   Server-side connector (runs on server.pro)   ##########
##############################################################

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

    '''
    Initialize data structures for storing advancement messages
    The baseline set of messages is established at startup to avoid reporting old messages
    '''
    def get_initial_advancement_messages(self):
        self.msg_mutex = threading.Lock()
        self.messages = queue.Queue()
        # TODO

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
        pass
    
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