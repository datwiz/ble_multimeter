import pytest
import ble_multimeter.mm_ble_message as mm_ble_message


@pytest.mark.parametrize(
    "message_length,fixed_header",
    [
        (-1, b"\x00\x01"),
        (0, b"\x00\x01"),
        (3, b"\x00\x01\x02\x03"),
        (4, b"\x00\x01\x02\x03"),
    ],
)
def test_mm_ble_message_invalid_args(message_length, fixed_header):
    """
    Test that boundary checking is in place
    """
    with pytest.raises(ValueError):
        _ = mm_ble_message.MmBleMessage(message_length, fixed_header)


def test_mm_ble_message_valid_args():
    """
    Test sunny day msg object creation
    """
    msg = mm_ble_message.MmBleMessage(5, b"\x00\x01\x02\x03")
    assert len(msg.buffer) == 0
    assert msg.header_idx == 0


def test_mm_ble_message_do_byte():
    """
    Test single message parsing
    """
    msg = mm_ble_message.MmBleMessage(5, b"\x00\x01\x02\x03")
    packet = bytearray(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09")
    p_idx = 0
    # process a header
    for i in range(4):
        msg.do_byte(packet[p_idx])
        p_idx += 1
        assert len(msg.buffer) == i + 1
        assert msg.header_idx == i + 1

    # add a message
    msg.do_byte(packet[p_idx])
    p_idx += 1
    assert len(msg.buffer) == 0
    assert msg.header_idx == 0
    assert msg.payload == packet[0:5]

    # finally test the next byte leaves the payload in place
    msg.do_byte(packet[p_idx])
    assert msg.payload == packet[0:5]


def test_mm_ble_message_do_byte_packet_stream():
    """
    Test processing a stream of packets
    """
    msg = mm_ble_message.MmBleMessage(5, b"\x00\x01")
    p1 = bytearray(b"\x00\x01\xf1\xf2\xf3")
    p2 = bytearray(b"\x00\x01\xf1\xf2\xf3")
    p_noise = bytearray(b"\xff\xff\xff")
    p3 = bytearray(b"\x00\x01\xf1\xf2\xf3")
    p_stream = p1 + p2 + p_noise + p3

    for i, b in enumerate(p_stream):
        msg.do_byte(b)
        if i == len(p1):
            assert msg.payload == p1
        if i == len(p1) + len(p2):
            assert msg.payload == p2
        if i == len(p1) + len(p2) + len(p_noise):
            assert msg.payload == p2
        if i == len(p1) + len(p2) + len(p_noise) + len(p3):
            assert msg.payload == p3
    assert msg.payload == p3
