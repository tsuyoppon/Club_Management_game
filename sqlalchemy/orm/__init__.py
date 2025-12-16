from typing import Any, Callable


class MetaData:
    pass


def declarative_base():
    class Base:
        metadata = MetaData()

    return Base


class Session:
    def __init__(self, bind=None, autocommit=False, autoflush=False, future=True):
        self.bind = bind
        self.autocommit = autocommit
        self.autoflush = autoflush
        self.future = future

    def close(self):
        pass


def sessionmaker(autocommit=False, autoflush=False, bind=None, future=True):
    def factory():
        return Session(bind=bind, autocommit=autocommit, autoflush=autoflush, future=future)

    return factory
