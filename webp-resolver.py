from discord import Message

# class for resolving alternative versions of webp images
class WebpResolver:
    def __init__(self, logger):
        self.logger = logger

    def resolve(self, message : Message):
        """
        Stub: Given a URL to a webp image, try to find an alternative version of the image.
        Args:
            url (str): The URL to the webp image.
        Returns:
            None
        """
        webps = [e.url for e in message.embeds if '.webp' in e.url]
        if len(webps) == 0:
            return None

        self.logger.info(f"Attempting to find non-webp URLs for: {webps}")
        resolved = []
        for url in webps:
            pass # TODO: Implement actual resolution logic

        return resolved if len(resolved) > 0 else None
