import os
import json
import logging
import sys
import threading
import time
import random
import ctypes
import struct
from snap7.server import Server
from snap7 import SrvArea
import re

# ---------------------- Configuration and Parameter Priority ----------------------
def get_config_param(key, env_key, cfg, default):
    return os.environ.get(env_key) or cfg.get(key) or default

def load_s7_classic_config():
    # First check current working directory, then script directory
    for path in [os.getcwd(), os.path.dirname(__file__)]:
        config_path = os.path.join(path, "s7_classic_connection.json")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
    return {}

# Parse configuration file
s7_cfg = load_s7_classic_config()
connections = s7_cfg.get("configs", [{}])[0].get("config", {}).get("connections", [])
if not connections:
    raise RuntimeError("No connections found in s7_classic_connection.json")
conn = connections[0]
params = conn.get("parameters", {})
datapoints = conn.get("datapoints", [])

# Parameter priority: Environment variable > Config file > Default value
ADDRESS = get_config_param("ip_address", "S7SERVER_ADDRESS", params, "0.0.0.0")
PORT = int(get_config_param("port", "S7SERVER_PORT", params, 102))
RACK = int(get_config_param("rack_number", "S7SERVER_RACK", params, 0))
SLOT = int(get_config_param("slot_number", "S7SERVER_SLOT", params, 2))
FREQUENCY = float(get_config_param("frequency", "S7SERVER_FREQUENCY", params, 1))
DB_NUMBER = 1

# Calculate DB area size: find max offset + type length for all datapoints
TYPE_SIZE = {"Bool": 1, "Int": 2, "Real": 4, "String": 20, "DateTime": 8}

def parse_offset(addr_str):
    m = re.match(r"%DB1\.DBB(\d+)", addr_str)
    if not m:
        raise ValueError(f"Unsupported address string: {addr_str}")
    return int(m.group(1))

max_offset = 0
for dp in datapoints:
    offset = parse_offset(dp["address"]["address_string"])
    size = TYPE_SIZE.get(dp["data_type"], 1)
    max_offset = max(max_offset, offset + size)
DB_SIZE = max(256, max_offset)

# ---------------------- Logging Configuration ----------------------
LOG_DEST = os.environ.get("S7SERVER_LOG", "stdout")
logger = logging.getLogger("s7server")
logger.setLevel(logging.INFO)
if LOG_DEST == "stdout":
    handler = logging.StreamHandler(sys.stdout)
else:
    handler = logging.FileHandler(LOG_DEST, encoding="utf-8")
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
# Remove old handlers to avoid duplication
logger.handlers.clear()
logger.addHandler(handler)
logger.info(f"log output to: {LOG_DEST}")

# ANSI color codes (same as client)
COLOR_INT = '\033[94m'      # Blue
COLOR_FLOAT = '\033[92m'    # Green
COLOR_DOUBLE = '\033[96m'   # Cyan
COLOR_BOOL = '\033[93m'     # Yellow
COLOR_STRING = '\033[95m'   # Magenta
COLOR_DATETIME = '\033[91m' # Red
COLOR_RESET = '\033[0m'


# ---------------------- S7 Server Initialization ----------------------
server = Server()
db_buffer = ctypes.create_string_buffer(DB_SIZE)
server.register_area(SrvArea.DB, DB_NUMBER, db_buffer)

# ---------------------- Data Writing Threads ----------------------
def int_to_bcd(val):
    return ((val // 10) << 4) | (val % 10)

def write_bool_points(points):
    value = True
    while True:
        value = not value
        for dp in points:
            offset = parse_offset(dp["address"]["address_string"])
            db_buffer[offset] = b'\x01'[0] if value else b'\x00'[0]
            logger.info(f"{COLOR_BOOL}Wrote bool: {value} to {dp['address']['address_string']}{COLOR_RESET}")
        time.sleep(FREQUENCY)

def write_int_points(points):
    while True:
        for dp in points:
            offset = parse_offset(dp["address"]["address_string"])
            value = random.randint(0, 65535)
            db_buffer[offset:offset+2] = value.to_bytes(2, byteorder='big')
            logger.info(f"{COLOR_INT}Wrote int: {value} to {dp['address']['address_string']}{COLOR_RESET}")
        time.sleep(FREQUENCY)

def write_real_points(points):
    while True:
        for dp in points:
            offset = parse_offset(dp["address"]["address_string"])
            value = random.uniform(0, 100)
            db_buffer[offset:offset+4] = struct.pack('>f', value)
            logger.info(f"{COLOR_FLOAT}Wrote real: {value:.2f} to {dp['address']['address_string']}{COLOR_RESET}")
        time.sleep(FREQUENCY)

def write_string_points(points):
    while True:
        for dp in points:
            offset = parse_offset(dp["address"]["address_string"])
            s = f"Hello_{random.randint(100,999)}"
            b = s.encode('ascii')
            max_len = 18  # S7 standard string max content length
            actual_len = min(len(b), max_len)
            buf = bytearray(20)
            buf[0] = max_len
            buf[1] = actual_len
            buf[2:2+actual_len] = b[:actual_len]
            db_buffer[offset:offset+20] = buf
            logger.info(f"{COLOR_STRING}Wrote string: {s} to {dp['address']['address_string']}{COLOR_RESET}")
        time.sleep(FREQUENCY)

def write_datetime_points(points):
    while True:
        for dp in points:
            offset = parse_offset(dp["address"]["address_string"])
            now = time.localtime()
            year = now.tm_year % 100
            month = now.tm_mon
            day = now.tm_mday
            hour = now.tm_hour
            minute = now.tm_min
            second = now.tm_sec
            ms = int((time.time() % 1) * 1000)
            ms_high = int_to_bcd(ms // 10)
            ms_low = int_to_bcd(ms % 10)
            dt_bytes = bytearray(8)
            dt_bytes[0] = int_to_bcd(year)
            dt_bytes[1] = int_to_bcd(month)
            dt_bytes[2] = int_to_bcd(day)
            dt_bytes[3] = int_to_bcd(hour)
            dt_bytes[4] = int_to_bcd(minute)
            dt_bytes[5] = int_to_bcd(second)
            dt_bytes[6] = ms_high
            dt_bytes[7] = ms_low
            db_buffer[offset:offset+8] = dt_bytes
            logger.info(f"{COLOR_DATETIME}Wrote S7 DT: {' '.join(f'{b:02X}' for b in dt_bytes)} to {dp['address']['address_string']}{COLOR_RESET}")
        time.sleep(FREQUENCY)

# ---------------------- Monitoring Threads ----------------------
def monitor_status():
    while True:
        try:
            status, cpu, clients = server.get_status()
            logger.info(f"Server status: {status}, CPU: {cpu}, Clients: {clients}")
        except Exception as e:
            logger.error(f"Status error: {e}")
        time.sleep(5)

def monitor_events():
    while True:
        try:
            event = server.pick_event()
            if event:
                text = server.event_text(event)
                logger.info(f"Event: {text}")
        except Exception as e:
            logger.error(f"Event error: {e}")
        time.sleep(1)

# ---------------------- Main Startup Process ----------------------
def start_server():
    try:
        server.start()
        logger.info(f"Snap7 server started at {ADDRESS}:{PORT} rack={RACK} slot={SLOT}")
    except Exception as e:
        logger.error(f"Server start error: {e}")
        raise


def main():
    start_server()
    # Categorize datapoints
    bool_points = [dp for dp in datapoints if dp["data_type"] == "Bool"]
    int_points = [dp for dp in datapoints if dp["data_type"] == "Int"]
    real_points = [dp for dp in datapoints if dp["data_type"] == "Real"]
    string_points = [dp for dp in datapoints if dp["data_type"] == "String"]
    datetime_points = [dp for dp in datapoints if dp["data_type"] == "DateTime"]

    if bool_points:
        threading.Thread(target=write_bool_points, args=(bool_points,), daemon=True).start()
    if int_points:
        threading.Thread(target=write_int_points, args=(int_points,), daemon=True).start()
    if real_points:
        threading.Thread(target=write_real_points, args=(real_points,), daemon=True).start()
    if string_points:
        threading.Thread(target=write_string_points, args=(string_points,), daemon=True).start()
    if datetime_points:
        threading.Thread(target=write_datetime_points, args=(datetime_points,), daemon=True).start()

    threading.Thread(target=monitor_status, daemon=True).start()
    threading.Thread(target=monitor_events, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping server...")
        server.stop()
        server.destroy()
        logger.info("Server stopped.")


def print_help():
    help_text = """
Snap7 S7 Server Simulator Help

Usage:
    python s7server.py [--help]

Configuration:
    The server reads its configuration from 's7_classic_connection.json' in the current directory or script directory.
    You must provide connection and datapoint information in this file. Example structure:

    {
        "configs": [
            {
                "config": {
                    "connections": [
                        {
                            "parameters": {
                                "ip_address": "0.0.0.0",
                                "port": 102,
                                "rack_number": 0,
                                "slot_number": 2,
                                "frequency": 1
                            },
                            "datapoints": [
                                {
                                    "address": {"address_string": "%DB1.DBB0"},
                                    "data_type": "Bool"
                                    "name": "100ms_6K_NOPT.BoolTag1",
                                    "comment": "",
                                    "acquisition_cycle": 1000,
                                    "acquisition_mode": "CyclicOnChange",
                                    "access_mode": "r"
                                },
                                ...
                            ]
                        }
                    ]
                }
            }
        ]
    }

	address_string format must be like %DB1.DBB0, %DB1.DBB2, etc. the last number indicates the byte offset in DB1.
	data_type can be Bool, Int, Real, String, DateTime.
	other fields are optional, but if import to SIMATIC S7 Connector of IE App, they should be filled properly.

    You can override parameters using environment variables:
        S7SERVER_ADDRESS, S7SERVER_PORT, S7SERVER_RACK, S7SERVER_SLOT, S7SERVER_FREQUENCY, S7SERVER_LOG

    Log output defaults to stdout, or set S7SERVER_LOG to a file path.

To start the server:
    python s7server.py

To show this help:
    python s7server.py --help
"""
    print(help_text)

if __name__ == "__main__":
    if "--help" in sys.argv:
        print_help()
    else:
        main()

