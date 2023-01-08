def bit_flag_is_set(flags: int, flag_bit: int) -> bool:
    """Check if a particular bit flag is set.

    Args:
        flags (int): The value comprised of bit flags.
        flag_bit (int): The bit flag position to check, starting with rightmost bit as 0.

    Returns:
        bool: True if the bit flag is set, False otherwise.

    Raises:
        ValueError: If the flag_bit is out of range.
    """

    # just return false if all flags are false to guard against truncation
    if flags == 0:
        return False

    if flag_bit < 0 or flag_bit > flags.bit_length():
        raise ValueError(
            f"bit flag {flag_bit} is out of range for flags {flags} with bit length {flags.bit_length()}"
        )
    return ((flags >> flag_bit) & 1) == 1
