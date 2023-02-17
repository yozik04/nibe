from pytest import raises

from nibe.coil import Coil, CoilData
from nibe.connection import Connection
from nibe.exceptions import CoilReadException, CoilWriteException


async def test_read_coils():
    coil1 = Coil(123, "test", "test", "u8")
    coil2 = Coil(231, "test2", "test", "u8")
    coil3 = Coil(231, "test3", "test", "u8")

    class MyConnection(Connection):
        async def read_coil(self, coil: Coil, timeout: float = ...) -> CoilData:
            if coil is coil2:
                raise CoilReadException(f"{coil.address}")
            return CoilData(coil, 1)

        async def verify_connectivity(self):
            return True

        async def write_coil(self, coil_data: CoilData, timeout: float = ...) -> None:
            raise CoilWriteException()

    connection = MyConnection()

    coils = []
    with raises(CoilReadException) as excinfo:
        async for coil_data in connection.read_coils([coil1, coil2, coil3]):
            coils.append(coil_data.coil)
    assert str(excinfo.value) == "Failed to read some or all coils (231)"
    assert coils == [coil1, coil3]
