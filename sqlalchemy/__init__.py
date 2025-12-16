from .orm import declarative_base, sessionmaker


class Engine:
    def __init__(self, url: str, echo: bool = False, future: bool = True):
        self.url = url
        self.echo = echo
        self.future = future


def create_engine(url: str, echo: bool = False, future: bool = True):
    return Engine(url, echo=echo, future=future)


def engine_from_config(config: dict, prefix: str = "sqlalchemy.", poolclass=None):
    url = config.get("url") or config.get("sqlalchemy.url") or config.get("url")
    return Engine(url, future=True)


class pool:
    class NullPool:
        pass
