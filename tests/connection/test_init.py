from pytest import raises

from nibe.coil import Coil
from nibe.connection import Connection
from nibe.exceptions import CoilReadException, CoilWriteException


async def test_read_coils():
    coil1 = Coil(123, "test", "test", "u8")
    coil2 = Coil(231, "test2", "test", "u8")
    coil3 = Coil(231, "test3", "test", "u8")

    class MyConnection(Connection):
        async def read_coil(self, coil: Coil, timeout: float = ...) -> Coil:
            if coil is coil2:
                raise CoilReadException(f"{coil.address}")
            return coil

        async def verify_connectivity(self):
            return True

        async def write_coil(self, coil: Coil, timeout: float = ...) -> Coil:
            raise CoilWriteException()

    connection = MyConnection()

    result = []
    with raises(CoilReadException) as excinfo:
        async for coil in connection.read_coils([coil1, coil2, coil3]):
            result.append(coil)
    assert str(excinfo.value) == "Failed to read some or all coils (231)"
    assert result == [coil1, coil3]
