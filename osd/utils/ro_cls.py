# idea borrowed from https://github.com/oz123/read-only-properties

from typing import Any

"""
decorator to make class attributes readonly
"""
def read_only_class(cls):

    class NewClass(cls):
        def __setattr__(self, __name: str, _: Any) -> None:
            raise AttributeError("Can't touch {}".format(__name))                

    return NewClass
