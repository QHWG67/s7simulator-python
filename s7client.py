

import sys
import time
import struct
import snap7
import os
import json
import re

# ANSI color codes
COLOR_INT = '\033[94m'      # Blue
COLOR_FLOAT = '\033[92m'    # Green
COLOR_BOOL = '\033[93m'     # Yellow
COLOR_STRING = '\033[95m'   # Magenta
COLOR_DATETIME = '\033[91m' # Red
COLOR_RESET = '\033[0m'

TYPE_SIZE = {"Bool": 1, "Int": 2, "Real": 4, "String": 20, "DateTime": 8}

def bcd_to_int(b):
    return ((b >> 4) * 10) + (b & 0x0F)

def parse_datetime(data):
    year = bcd_to_int(data[0])
    month = bcd_to_int(data[1])
    day = bcd_to_int(data[2])
    hour = bcd_to_int(data[3])
    minute = bcd_to_int(data[4])
    second = bcd_to_int(data[5])
    ms = bcd_to_int(data[6]) * 10 + bcd_to_int(data[7])
    return f"20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}.{ms:03d}"

def parse_offset(addr_str):
    m = re.match(r"%DB1\.DBB(\d+)", addr_str)
    if not m:
        raise ValueError(f"Unsupported address string: {addr_str}")
    return int(m.group(1))


def load_s7_classic_config():
    config_path = os.path.join(os.path.dirname(__file__), "s7_classic_connection.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
    return {}

def main():
    # 读取配置
    s7_cfg = load_s7_classic_config()
    connections = s7_cfg.get("configs", [{}])[0].get("config", {}).get("connections", [])
    if not connections:
        print("No connections found in s7_classic_connection.json")
        return
    conn = connections[0]
    datapoints = conn.get("datapoints", [])

    # 连接参数
    params = conn.get("parameters", {})
    address = params.get("ip_address", "127.0.0.1")
    rack = int(params.get("rack_number", 0))
    slot = int(params.get("slot_number", 2))

    client = snap7.client.Client()
    client.connect(address, rack, slot)
    print(f'Connected to server {address}, reading datapoints:')
    try:
        while True:
            for dp in datapoints:
                name = dp.get("name", "")
                dtype = dp.get("data_type", "")
                addr_str = dp["address"]["address_string"]
                offset = parse_offset(addr_str)
                size = TYPE_SIZE.get(dtype, 1)
                data = client.db_read(1, offset, size)
                if dtype == "Bool":
                    val = bool(data[0])
                    color = COLOR_BOOL
                elif dtype == "Int":
                    val = int.from_bytes(data, byteorder='big')
                    color = COLOR_INT
                elif dtype == "Real":
                    val = struct.unpack('>f', data)[0]
                    color = COLOR_FLOAT
                elif dtype == "String":
                    val = data.decode('ascii', errors='ignore').rstrip('\x00')
                    color = COLOR_STRING
                elif dtype == "DateTime":
                    val = parse_datetime(data)
                    color = COLOR_DATETIME
                else:
                    val = data.hex()
                    color = COLOR_RESET
                print(f"{color}{name} ({dtype}) @ {addr_str}: {val}{COLOR_RESET}")
            print('-' * 40)
            time.sleep(1)
    except KeyboardInterrupt:
        print('Disconnecting...')
        client.disconnect()

if __name__ == '__main__':
    main()
