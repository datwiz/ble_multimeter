import pendulum
from ble_multimeter.bit_flag_decoder import bit_flag_is_set


class MmBleMessage:
    """
    message parser and decoder for the ble messages.

    Messages are expected to be fixed length with a fixed header of 1 or more bytes.

    A zero length header is considered valid.
    """

    mode_settings = {
        0x01: "VAC",
        0x02: "VDC",
        0x04: "Resistance",
        0x05: "Capacitance",
        0x06: "Temperature",
        0x07: "Amps-DC",
        0x08: "mAmps-DC",
        0x09: "uAmps-DC",
        0x0C: "Amps-AC",
        0x0D: "mAmps-AC",
        0x0E: "uAmps-AC",
        0x0F: "Diode test",
        0x10: "Frequency",
        0x20: "Continuity",
    }

    mode_units = {
        0x01: "V",
        0x02: "A",
        0x03: "Ohms",
        0x04: "Hz",
        0x05: "F",
        0x06: "Ohms continuity",
        0x07: "V diode test",
        0x08: "Deg C",
        0x09: "Deg F",
        0x10: "%",
    }

    units_multiplier = {
        0x00: [1.0, ""],
        0x01: [1_000.0, "k"],
        0x02: [1_000_000.0, "M"],
        0x03: [10.0**-9, "n"],
        0x04: [10.0**-6, "u"],
        0x05: [10.0**-3, "m"],  # Amps
        0x06: [10.0**-3, "m"],  # Volts
    }

    def __init__(self, message_length: int, fixed_header: bytearray) -> None:
        self.reset_parser()
        # the last valid message parsed
        self.payload = bytearray(0)

        # invalid message length is less than 1
        if message_length < 1:
            raise ValueError(
                f"Invalid message_length {message_length}.  message_length must be greater than 0"
            )

        # header length is greater than message length - no message will ever be found
        if message_length <= len(fixed_header):
            raise ValueError(
                f"message_length {message_length} is less than fixed_header length {len(fixed_header)}"
            )

        self.message_length = message_length
        self.fixed_header = fixed_header
        self.last_msg_dttm = pendulum.now()

    def reset_parser(self) -> None:
        """
        Reset the parser buffer and header index.
        """
        self.header_idx = 0
        self.buffer = bytearray(0)

    def do_byte(self, next_byte: int) -> None:
        """
        Process the next byte of the message.

        If a message is found, the payload will be stored in self.payload
        """

        # in the header sync/search state
        if self.header_idx < len(self.fixed_header):
            if self.fixed_header[self.header_idx] == next_byte:
                self.header_idx += 1
                self.buffer.append(next_byte)
            else:
                self.reset_parser()
        # else in the message assembly state
        else:
            if (len(self.buffer) + 1) < self.message_length:
                self.buffer.append(next_byte)
            else:
                # this works because the buffer will get re-initialiezd with a new empty bytearray
                # so rather than copy and destroy the buffer, just assign the buffer to the payload
                self.payload = self.buffer
                self.last_msg_dttm = pendulum.now()
                self.payload.append(next_byte)
                self.reset_parser()

    def mm_mode(self) -> str:
        return self.mode_settings.get(self.payload[4], "Unknown")

    def mm_value_raw(self) -> str:
        """ """
        pass

    def mm_decimal_places(self) -> int:
        return self.payload[9] * 1

    def mm_value(self) -> float:
        """
        Parsed value from the meter reading
        """

        if self.payload[5] == 0x0B or self.payload[5] == 0x0F:
            raise ValueError("undefined overload value")

        val = 0.0
        # print(f"payload: {self.payload.hex('-')}")
        # print(f"payload[5:9]: {self.payload[5:9].hex('-')}")
        if self.payload[8] == 0x0F:
            return 0.0

        for i, v in enumerate(self.payload[5:9]):
            val += v * 10.0 ** (i)

        if bit_flag_is_set(self.payload[12], 0):
            val = -val
        # raise ValueError("temp output")
        return val / (10.0 ** self.mm_decimal_places())

    def mm_units(self) -> str:
        """
        return the unit, including multiplier
        """
        units = self.mode_units.get(self.payload[10], None)
        multiplier = self.units_multiplier.get(self.payload[11], None)
        if units is None or multiplier is None:
            raise ValueError("Unknown units or multiplier")
        return f"{multiplier[1]}{units}"
