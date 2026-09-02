# ======================================================================
# ld2410_config.py — LD2410/LD2410C configuration-protocol client
#
# This is the OTHER half of the LD2410 UART protocol from the one your
# person-detect script already speaks. Your script reads the continuous
# "target data" frames (header F4 F3 F2 F1 / footer F8 F7 F6 F5) that the
# radar streams out during normal operation. This module speaks the
# "command frames" (header FD FC FB FA / footer 04 03 02 01) that let
# you reconfigure the radar itself — its max detection range and its
# per-gate sensitivity.
#
# Frame formats (from Hi-Link's HLK-LD2410 Serial Communication Protocol,
# little-endian throughout):
#
#   Command frame:  FD FC FB FA | len(2B) | cmd_word(2B) + value(N B) | 04 03 02 01
#   ACK frame:      FD FC FB FA | len(2B) | (cmd_word|0x0100)(2B) + return(N B) | 04 03 02 01
#
# IMPORTANT: while the radar is in "config mode" (after Enable Config,
# before End Config), it stops streaming normal target-data frames. Do
# all your configuration before you start reading the normal data
# stream, not interleaved with it.
# ======================================================================

import struct
import time

CMD_HEADER = b'\xFD\xFC\xFB\xFA'
CMD_FOOTER = b'\x04\x03\x02\x01'

# Command words (16-bit, little-endian on the wire)
CMD_ENABLE_CONFIG   = 0x00FF
CMD_END_CONFIG      = 0x00FE
CMD_SET_MAX_GATE    = 0x0060   # max moving gate, max static gate, no-one duration
CMD_READ_PARAMS     = 0x0061
CMD_SET_SENSITIVITY = 0x0064   # per-gate (or all-gates) motion/static sensitivity

ALL_GATES = 0xFFFF  # sentinel: apply sensitivity to every gate at once

# Default distance resolution is 0.75 m per gate, gates 0-8 (9 gates,
# covering 0-6.75m nominal / ~6m rated max). If you've switched the
# module to the 0.2m-per-gate mode via command 0x00A8, GATE_SIZE_MM
# needs to change to match — that mode isn't implemented here.
GATE_SIZE_MM = 750
MAX_GATE_INDEX = 8


def mm_to_gate(distance_mm: float, gate_size_mm: int = GATE_SIZE_MM,
               max_gate: int = MAX_GATE_INDEX) -> int:
    """Convert a distance in mm to the gate index that contains it, clamped to range."""
    gate = int(distance_mm // gate_size_mm)
    return max(0, min(gate, max_gate))


def build_command_frame(cmd_word: int, value: bytes = b'') -> bytes:
    intra = struct.pack('<H', cmd_word) + value
    length = struct.pack('<H', len(intra))
    return CMD_HEADER + length + intra + CMD_FOOTER


def read_ack_frame(ser, timeout_s: float = 1.0):
    """
    Read one command-protocol frame (header FD FC FB FA ... footer 04 03 02 01)
    off *ser* within timeout_s. Returns the intra-frame data (cmd_word bytes +
    return value bytes) on success, or None on timeout/malformed frame.
    """
    deadline = time.monotonic() + timeout_s
    buf = bytearray()

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue
        buf.extend(chunk)

        start = buf.find(CMD_HEADER)
        if start == -1:
            # keep only enough tail in case the header is split across reads
            if len(buf) > len(CMD_HEADER):
                buf = buf[-(len(CMD_HEADER) - 1):]
            continue

        if len(buf) < start + 6:
            continue  # haven't got the length field yet

        length = struct.unpack('<H', bytes(buf[start + 4:start + 6]))[0]
        frame_end = start + 6 + length + len(CMD_FOOTER)
        if len(buf) < frame_end:
            continue  # haven't got the full frame yet

        intra = bytes(buf[start + 6:start + 6 + length])
        footer = bytes(buf[start + 6 + length:frame_end])

        if footer != CMD_FOOTER:
            # false header match — drop past it and keep scanning
            buf = buf[start + 1:]
            continue

        return intra

    return None


def send_command(ser, cmd_word: int, value: bytes = b'', timeout_s: float = 1.0):
    """
    Send a command frame and wait for its ACK.
    Returns (status, extra_bytes) where status is 0 (success), 1 (failure),
    or None (no/garbled ACK received). extra_bytes is whatever return data
    followed the status word (may be empty).
    """
    ser.write(build_command_frame(cmd_word, value))

    intra = read_ack_frame(ser, timeout_s)
    if intra is None or len(intra) < 2:
        return None, None

    ack_cmd = struct.unpack('<H', intra[0:2])[0]
    if ack_cmd != (cmd_word | 0x0100):
        return None, None  # ACK for a different command, or garbage

    if len(intra) >= 4:
        status = struct.unpack('<H', intra[2:4])[0]
        extra = intra[4:]
    else:
        status = None
        extra = b''

    return status, extra


class LD2410Config:
    """
    Thin wrapper over the config-protocol commands. Construct with an
    already-open serial.Serial (same port/baud your normal data-frame
    reader uses — configuration and data streaming share the connection,
    just not at the same time).
    """

    def __init__(self, ser, timeout_s: float = 1.0):
        self.ser = ser
        self.timeout_s = timeout_s
        self._in_config = False

    def enter_config_mode(self):
        status, _ = send_command(self.ser, CMD_ENABLE_CONFIG,
                                  struct.pack('<H', 0x0001), self.timeout_s)
        if status != 0:
            raise RuntimeError(f"Enable Configuration failed (status={status})")
        self._in_config = True

    def end_config_mode(self):
        status, _ = send_command(self.ser, CMD_END_CONFIG, b'', self.timeout_s)
        self._in_config = False
        if status != 0:
            raise RuntimeError(f"End Configuration failed (status={status})")

    def set_max_gate(self, max_moving_gate: int, max_static_gate: int,
                      no_one_duration_s: int):
        """
        Cap the radar's own reporting range. Gates are 0-8 (see GATE_SIZE_MM);
        the radar will not report a target beyond the configured gate at all
        — this is a hard cutoff enforced on the module itself, not a filter
        you'd otherwise apply in your Python code.
        no_one_duration_s: how long the radar waits with nothing detected
        before it settles into a stable "no target" report.
        """
        value = (
            struct.pack('<H', 0x0000) + struct.pack('<I', max_moving_gate) +
            struct.pack('<H', 0x0001) + struct.pack('<I', max_static_gate) +
            struct.pack('<H', 0x0002) + struct.pack('<I', no_one_duration_s)
        )
        status, _ = send_command(self.ser, CMD_SET_MAX_GATE, value, self.timeout_s)
        if status != 0:
            raise RuntimeError(f"Set Max Distance Gate failed (status={status})")

    def set_gate_sensitivity(self, gate: int, motion_sensitivity: int,
                              static_sensitivity: int):
        """
        gate: 0-8 for a single gate, or ALL_GATES (0xFFFF) to set every gate
        to the same value in one call.
        motion_sensitivity / static_sensitivity: 0-100 (higher = more
        sensitive, i.e. triggers on weaker reflections).
        """
        value = (
            struct.pack('<H', 0x0000) + struct.pack('<I', gate) +
            struct.pack('<H', 0x0001) + struct.pack('<I', motion_sensitivity) +
            struct.pack('<H', 0x0002) + struct.pack('<I', static_sensitivity)
        )
        status, _ = send_command(self.ser, CMD_SET_SENSITIVITY, value, self.timeout_s)
        if status != 0:
            raise RuntimeError(f"Set Gate Sensitivity failed for gate {gate} (status={status})")

    def read_parameters(self):
        """
        Reads back the radar's current configuration. Returns a dict:
          max_gate                    - highest gate index the module supports (0x08)
          configured_max_moving_gate  - currently configured max moving gate
          configured_max_static_gate  - currently configured max static gate
          motion_sensitivity          - list, index = gate, 0-100
          static_sensitivity          - list, index = gate, 0-100
          no_one_duration_s           - seconds
        """
        status, extra = send_command(self.ser, CMD_READ_PARAMS, b'', self.timeout_s)
        if status != 0 or extra is None:
            raise RuntimeError(f"Read Parameters failed (status={status})")

        # extra layout: header(0xAA,1B) + max_gate_N(1B) +
        # configured_max_moving_gate(1B) + configured_max_static_gate(1B) +
        # motion_sensitivity[0..N](N+1 bytes) + static_sensitivity[0..N](N+1 bytes)
        # + no_one_duration(2B, LE uint16)
        if len(extra) < 4 or extra[0] != 0xAA:
            raise RuntimeError(f"Unexpected Read Parameters response: {extra.hex()}")

        max_gate_n = extra[1]
        n = max_gate_n + 1
        offset = 4
        motion_sens = list(extra[offset:offset + n]); offset += n
        static_sens = list(extra[offset:offset + n]); offset += n
        no_one_duration = (struct.unpack('<H', extra[offset:offset + 2])[0]
                            if len(extra) >= offset + 2 else None)

        return {
            "max_gate": max_gate_n,
            "configured_max_moving_gate": extra[2],
            "configured_max_static_gate": extra[3],
            "motion_sensitivity": motion_sens,
            "static_sensitivity": static_sens,
            "no_one_duration_s": no_one_duration,
        }
