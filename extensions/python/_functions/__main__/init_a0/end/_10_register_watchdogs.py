from helpers.extension import Extension


class RegisterWatchDogs(Extension):
    """Register file-system watchdogs for hot-reload.

    Extension watchdogs are registered separately in prepare.py during
    initial startup (when all extension directories are guaranteed to exist).
    This hook only registers plugin watchdogs as a safety net.
    """

    def execute(self, **kwargs):
        from helpers.plugins import register_watchdogs as register_plugins_watchdogs

        register_plugins_watchdogs()
