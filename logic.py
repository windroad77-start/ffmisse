from .setup import P


class Logic:
    @staticmethod
    def plugin_load():
        P.logger.info("MissKon logic plugin_load")

    @staticmethod
    def plugin_unload():
        P.logger.info("MissKon logic plugin_unload")
