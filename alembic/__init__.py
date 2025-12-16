class Config:
    def __init__(self, ini_path: str | None = None):
        self.ini_path = ini_path
        self.config_ini_section = "alembic"
        self.config_file_name = ini_path
        self._options = {}

    def set_main_option(self, key: str, value: str):
        self._options[key] = value

    def get_main_option(self, key: str, default=None):
        return self._options.get(key, default)

    def get_section(self, section: str):
        return self._options


class Context:
    def __init__(self):
        self.config = Config()

    def configure(self, **kwargs):
        self._configured = kwargs

    def begin_transaction(self):
        from contextlib import nullcontext

        return nullcontext()

    def run_migrations(self):
        pass

    def is_offline_mode(self):
        return True


context = Context()


class op:
    pass
