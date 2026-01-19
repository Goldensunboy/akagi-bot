import path, json, flask
from logging import Logger

##############################################################
####   Static functions   ####################################
##############################################################

props_file_pattern = 'minecraft_connector_props*.json'
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

    def __init__(self, logger: Logger):
        self.logger = logger
        self.client_props = self.load_props()
        self.http_client = self.create_client()

    '''
    Load Minecraft server connection properties
      Put public attributes in a committed file matching the props_file_pattern
      Put private attributes in a .gitignored file matching the props_file_pattern
    '''
    def load_client_props(self):
        props = load_props("client", self.logger)
        for key in ["server_host", "server_port", "auth_token", "announcement_channel_id", "update_interval_seconds"]:
            if key not in props:
                msg = f"Missing required Minecraft connector client property: {key}"
                self.logger.error(msg)
                raise ValueError(msg)
    
    def create_client(self):
        pass

    def get_messages(self):
        pass

##############################################################
####   Server-side connector (runs on server.pro)   ##########
##############################################################

class MicecraftConnectorServer:

    def __init__(self, logger: Logger):
        self.logger = logger
        self.server_props = self.load_props()
        self.app = flask.Flask(__name__)
        self.setup_routes()

    '''
    Load Minecraft server properties
      Put public attributes in a committed file matching the props_file_pattern
      Put private attributes in a .gitignored file matching the props_file_pattern
    '''
    def load_server_props(self):
        props = load_props("server", self.logger)
        for key in ["world_path", "auth_token", "update_interval_seconds"]:
            if key not in props:
                msg = f"Missing required Minecraft connector server property: {key}"
                self.logger.error(msg)
                raise ValueError(msg)

    def setup_routes(self):
        pass