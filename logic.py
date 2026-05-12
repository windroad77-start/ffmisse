from .setup import P


class Logic:
    @staticmethod
    def plugin_load():
        P.logger.info("FFMisse logic plugin_load")

    @staticmethod
    def plugin_unload():
        P.logger.info("FFMisse logic plugin_unload")
