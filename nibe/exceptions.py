class NibeException(Exception):
    pass


class DecodeException(NibeException):
    pass


class EncodeException(NibeException):
    pass


class CoilWriteException(NibeException):
    pass


class CoilReadException(NibeException):
    pass
