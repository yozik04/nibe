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


class WriteDeniedException(WriteException):
    """Raised a write of a value was rejected by the pump."""


class WriteIOException(WriteException):
    """Use this and child exceptions if IO has failed and you want to retry."""

    pass


class CoilWriteSendException(WriteIOException):
    pass


class WriteTimeoutException(WriteIOException):
    pass


class ReadException(NibeException):
    pass


class ReadIOException(ReadException):
    """Use this and child exception if IO has failed and you want to retry."""

    pass


class ReadExceptionGroup(ExceptionGroup, ReadException):
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
