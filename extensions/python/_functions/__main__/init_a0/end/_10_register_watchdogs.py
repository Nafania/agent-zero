from helpers.extension import Extension


class RegisterWatchDogs(Extension):

    def execute(self, **kwargs):
        from helpers.extension import register_extensions_watchdogs
        from helpers.plugins import register_watchdogs as register_plugins_watchdogs

        register_extensions_watchdogs()
        register_plugins_watchdogs()
