class NibeException(Exception):
    pass


class CoilNotFoundException(NibeException):
    pass


class DecodeException(NibeException):
    pass


class NoMappingException(DecodeException):
    pass


class EncodeException(NibeException):
    pass


class WriteException(NibeException):
    pass


class CoilWriteException(WriteException):
    pass


class CoilWriteTimeoutException(CoilWriteException):
    pass


class ReadException(NibeException):
    pass


class CoilReadException(ReadException):
    pass


class CoilReadTimeoutException(CoilReadException):
    pass


class ProductInfoReadException(ReadException):
    pass


class ProductInfoReadTimeoutException(ProductInfoReadException):
    pass


class ModelIdentificationFailed(NibeException):
    pass


class ModbusUrlException(NibeException, ValueError):
    pass
