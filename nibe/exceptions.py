from exceptiongroup import ExceptionGroup


class NibeException(Exception):
    pass


class AddressInUseException(NibeException):
    pass


class CoilNotFoundException(NibeException):
    pass


class DecodeException(NibeException):
    pass


class ValidationError(NibeException):
    pass


class NoMappingException(ValidationError):
    pass


class EncodeException(NibeException):
    pass


class WriteException(NibeException):
    pass


class WriteIOException(WriteException):
    pass


class CoilWriteSendException(WriteIOException):
    pass


class WriteTimeoutException(WriteIOException):
    pass


class ReadException(NibeException):
    pass


class ReadIOException(ReadException):
    pass


class ReadExceptionGroup(ExceptionGroup, ReadIOException):
    def __str__(self) -> str:
        messages = ", ".join(str(exception) for exception in self.exceptions)
        return f"{self.message} ({messages})"


class ReadSendException(ReadIOException):
    pass


class ReadTimeoutException(ReadIOException):
    pass


class ProductInfoReadTimeoutException(ReadIOException):
    pass


class ModelIdentificationFailed(NibeException):
    pass


class ModbusUrlException(NibeException, ValueError):
    pass
