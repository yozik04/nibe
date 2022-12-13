from exceptiongroup import ExceptionGroup


class NibeException(Exception):
    pass


class AddressInUseException(NibeException):
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


class CoilWriteSendException(CoilWriteException):
    pass


class CoilWriteTimeoutException(CoilWriteException):
    pass


class ReadException(NibeException):
    pass


class CoilReadException(ReadException):
    pass


class CoilReadExceptionGroup(ExceptionGroup, CoilReadException):
    def __str__(self) -> str:
        messages = ", ".join(str(exception) for exception in self._exceptions)
        return f"{self.message} ({messages})"


class CoilReadSendException(CoilReadException):
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
