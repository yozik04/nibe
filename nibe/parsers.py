from construct import Transformed


def swapwords(data):
    r"""
    Performs a 2 byte word swap on byte-string.

    Example:

        >>> swapwords(b'abcd')
        b'cdab'
    """
    if len(data) % 2:
        raise ValueError(f"data length {len(data)} must be a multiple of 2")

    return b"".join(data[p : p + 2] for p in range(len(data) - 2, -1, -2))


def WordSwapped(subcon):
    r"""
    Swaps the 2-byte word order within boundaries of given subcon. Requires a fixed sized subcon.

    :param subcon: Construct instance

    :raises SizeofError: ctor or compiler could not compute subcon size
    :raises ValueError: subcon size is not multiple of 2

    See :class:`~construct.core.Transformed` and :class:`~construct.core.Restreamed` for raisable exceptions.

    Example::

        Int24ul <--> ByteSwapped(Int24ub) <--> BytesInteger(3, swapped=True) <--> ByteSwapped(BytesInteger(3))
    """

    size = subcon.sizeof()
    return Transformed(subcon, swapwords, size, swapwords, size)
