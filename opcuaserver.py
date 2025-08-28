

from opcua import Server
import time
import threading
import random
import argparse
import os
import xml.etree.ElementTree as ET
from opcua import ua


def parse_xml_config(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {'ua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd'}

    def get_tag(tag):
        return tag if root.find(tag) is not None else '{http://opcfoundation.org/UA/2011/03/UANodeSet.xsd}' + tag


    ns_uri = None
    ns_uris = root.find(get_tag('NamespaceUris'))
    if ns_uris is not None:
        uri_elem = ns_uris.find(get_tag('Uri'))
        if uri_elem is not None:
            ns_uri = uri_elem.text

    variables = []
    for var in root.findall(get_tag('UAVariable')):
        name = var.find(get_tag('DisplayName'))
        dtype = var.attrib.get('DataType')
        if name is not None and dtype is not None:
            variables.append({
                'name': name.text,
                'dtype': dtype
            })
    return variables, ns_uri

def random_value(dtype):

    if dtype in ('Boolean', 'i=1'):
        return random.choice([True, False])
    elif dtype in ('SByte', 'i=2'):
        return random.randint(-128, 127)
    elif dtype in ('Byte', 'i=3'):
        return random.randint(0, 255)
    elif dtype in ('Int16', 'i=4'):
        return random.randint(-32768, 32767)
    elif dtype in ('UInt16', 'i=5'):
        return random.randint(0, 65535)
    elif dtype in ('Int32', 'i=6'):
        return random.randint(-2147483648, 2147483647)
    elif dtype in ('UInt32', 'i=7'):
        return random.randint(0, 4294967295)
    elif dtype in ('Int64', 'i=8'):
        return random.randint(-9223372036854775808, 9223372036854775807)
    elif dtype in ('UInt64', 'i=9'):
        return random.randint(0, 18446744073709551615)
    elif dtype in ('Float', 'i=10'):
        return random.uniform(-1e6, 1e6)
    elif dtype in ('Double', 'i=11'):
        return random.uniform(-1e12, 1e12)
    elif dtype in ('String', 'i=12'):
        return ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
    elif dtype in ('DateTime', 'i=13'):
        return time.strftime('%Y-%m-%dT%H:%M:%S')
    elif dtype in ('Guid', 'i=14'):
        import uuid
        return str(uuid.uuid4())
    elif dtype in ('ByteString', 'i=15'):
        return bytes(random.getrandbits(8) for _ in range(8))
    elif dtype in ('XmlElement', 'i=16'):
        return '<val>{}</val>'.format(random.randint(0, 1000))
    elif dtype in ('NodeId', 'i=17'):
        return random.randint(1, 10000)
    elif dtype in ('ExpandedNodeId', 'i=18'):
        return random.randint(1, 10000)
    elif dtype in ('StatusCode', 'i=19'):
        return random.choice([0, 1, 2, 3, 4])
    elif dtype in ('QualifiedName', 'i=20'):
        return 'Q_{}'.format(random.randint(1, 1000))
    elif dtype in ('LocalizedText', 'i=21'):
        return 'Text_{}'.format(random.randint(1, 1000))
    elif dtype in ('Structure', 'i=22'):
        return {'field': random.randint(0, 100)}
    elif dtype in ('Number', 'i=26'):
        return random.uniform(-1e6, 1e6)
    elif dtype in ('Integer', 'i=27'):
        return random.randint(-2147483648, 2147483647)
    elif dtype in ('UInteger', 'i=28'):
        return random.randint(0, 4294967295)

    elif dtype.startswith('i=') and int(dtype[2:]) > 30:
        return 0
    else:
        return 0

def main():
    parser = argparse.ArgumentParser(description='OPC UA Server with XML config')
    parser.add_argument('-f', '--file', type=str, default='opc_ua_test_model.xml', help='XML config file')
    args = parser.parse_args()
    config_path = args.file if os.path.isfile(args.file) else os.path.join(os.getcwd(), 'opc_ua_test_model.xml')
    if not os.path.isfile(config_path):
        print(f"Config file not found: {config_path}")
        return

    variables, ns_uri = parse_xml_config(config_path)

    server = Server()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")

    uri = ns_uri if ns_uri else "http://examples.org/s7simulator/"
    idx = server.register_namespace(uri)
    objects = server.get_objects_node()

    var_objs = []
    for v in variables:
        var = objects.add_variable(idx, v['name'], random_value(v['dtype']))
        var.set_writable()
        try:
            var.UserAccessLevel = 3
            var.AccessLevel = 3
        except Exception:
            pass
        var_objs.append((var, v['dtype']))

    def update_vars():
        while True:
            for var, dtype in var_objs:
                var.set_value(random_value(dtype))
            time.sleep(3)

    t = threading.Thread(target=update_vars, daemon=True)
    t.start()

    server.start()
    print("OPC UA Server started at opc.tcp://0.0.0.0:4840/freeopcua/server/")
    try:
        while True:
            time.sleep(1)
    finally:
        server.stop()
        print("OPC UA Server stopped.")


if __name__ == "__main__":
    main()
