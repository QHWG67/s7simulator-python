

import sys
import time
import struct
import snap7
import os
import json
import re
import argparse

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


def parse_address(addr_str):
    # Support %DBn.DBXb.x, %DBn.DBBb, %DBn.DBWw, %DBn.DBDd
    m = re.match(r"%DB(\d+)\.(DBX|DBB|DBW|DBD)(\d+)(?:\.(\d+))?", addr_str)
    if not m:
        raise ValueError(f"Unsupported address string: {addr_str}")
    db_num = int(m.group(1))
    area_type = m.group(2)
    byte_offset = int(m.group(3))
    bit_offset = int(m.group(4)) if m.group(4) is not None else None
    return db_num, area_type, byte_offset, bit_offset

def parse_offset(addr_str):
    _, _, byte_offset, _ = parse_address(addr_str)
    return byte_offset


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-f', '--file', dest='config_path', help='Path to config file')
    parser.add_argument('--help', action='store_true', help='Show help')
    args, unknown = parser.parse_known_args()
    return args

def load_s7_classic_config(config_path=None):
    if config_path:
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        else:
            raise RuntimeError(f"Config file not found: {config_path}")
    # Default: current directory
    default_path = os.path.join(os.getcwd(), "s7_classic_connection.json")
    if os.path.exists(default_path):
        with open(default_path, "r") as f:
            return json.load(f)
    return {}

def main():
    args = parse_args()
    if args.help:
        print("Usage: python s7client.py [-f config_path] [--help]\nDefault config file is s7_classic_connection.json in current directory.")
        return
    # Load config
    s7_cfg = load_s7_classic_config(args.config_path)
    connections = s7_cfg.get("configs", [{}])[0].get("config", {}).get("connections", [])
    if not connections:
        print("No connections found in s7_classic_connection.json")
        return
    conn = connections[0]
    datapoints = conn.get("datapoints", [])

    # Connection parameters
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
                db_num, area_type, byte_offset, bit_offset = parse_address(addr_str)
                # 类型自动推断
                if area_type == "DBX":
                    dtype = "Bool"
                    size = 1
                elif area_type == "DBW":
                    dtype = "Int"
                    size = 2
                elif area_type == "DBD":
                    dtype = "Real"
                    size = 4
                elif area_type == "DBB":
                    size = TYPE_SIZE.get(dtype, 1)
                else:
                    size = TYPE_SIZE.get(dtype, 1)
                offset = byte_offset
                data = client.db_read(db_num, offset, size)
                if dtype == "Bool":
                    if bit_offset is not None:
                        val = bool((data[0] >> bit_offset) & 1)
                    else:
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
