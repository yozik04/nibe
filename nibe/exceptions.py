class NibeException(Exception):
    pass


class CoilNotFoundException(NibeException):
    pass


class DecodeException(NibeException):
    pass


class EncodeException(NibeException):
    pass


class CoilWriteException(NibeException):
    pass


class CoilWriteTimeoutException(CoilWriteException):
    pass


class CoilReadException(NibeException):
    pass


class CoilReadTimeoutException(CoilReadException):
    pass
