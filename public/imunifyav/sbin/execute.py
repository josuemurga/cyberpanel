#!/opt/imunify360/venv/bin/python3

import base64
import subprocess
import json
import os
import pwd
import time
import fileinput
import socket
import select
import shutil
import random
import stat
import string
import sys
from urllib.parse import urlencode

# this code is duplicated in installation.py because execute.py file is
# copied into /usr/bin directory in .spec. To handle it we can:
# 1. Create package in /opt/alt, but:
#     1.1 In plesk extension case python38 is installed after this code
# 2. Save code in var/etc directories and use symlinks technique, but:
#     2.1 Again, plesk extension
#     2.2 Symlinks may be disabled in the system
#         (so endusers will not be able to use extension)
#     2.3 This directories are not intended for such usage
#         (var is even deletable)
# 3. Store this files in new place in each extension
#     3.1 There are 4 extensions * 2 os types
# also present in installation.py


class Status:
    INSTALLING = "installing"
    UPGRADING = "upgrading"
    OK = "running"
    NOT_INSTALLED = "not_installed"
    DOWNGRADING = "downgrading"
    FAILED_TO_INSTALL = "failed_to_install"
    STOPPED = "stopped"
    SOCKET_INACCESSIBLE = "socket_inaccessible"


class ImunifyPluginDeployScript:
    IMUNIFY_360 = "i360deploy.sh"
    IMUNIFY_AV = "imav-deploy.sh"


def is_i360_downgrade_running() -> bool:
    try:
        proc = subprocess.run(["ps", "ax", "-o", "args="], stdout=subprocess.PIPE, check=False)
        ps_text = proc.stdout.decode("utf-8", "ignore")
        for line in ps_text.splitlines():
            if ImunifyPluginDeployScript.IMUNIFY_360 in line:
                tokens = line.split()
                if ("-d" in tokens) or ("--downgrade" in tokens):
                    return True
    except Exception:
        # be conservative: failure to detect should not break regular flow
        pass
    return False


def get_status():
    if is_in_upgrade_process():
        return Status.UPGRADING

    # Fast path: lightweight check if deploy scripts are running
    proc = subprocess.Popen(["ps", "ax"], stdout=subprocess.PIPE)
    output = proc.stdout.read()
    is_i360_running = ImunifyPluginDeployScript.IMUNIFY_360.encode() in output
    is_imav_running = ImunifyPluginDeployScript.IMUNIFY_AV.encode() in output

    if is_i360_running and is_i360_downgrade_running():
        return Status.DOWNGRADING

    if is_i360_running or is_imav_running:
        return Status.INSTALLING
    else:
        sock = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect("/var/run/defence360agent/simple_rpc.sock")
            return Status.OK
        except PermissionError:
            return Status.SOCKET_INACCESSIBLE
        except Exception:
            if os.path.exists("/usr/bin/imunify360-agent"):
                return Status.STOPPED
            else:
                try:
                    if os.path.exists(
                        "/usr/local/psa/var/modules/"
                        "imunify360/installation.log"
                    ):
                        return Status.FAILED_TO_INSTALL
                except:  # noqa
                    pass
                return Status.NOT_INSTALLED
        finally:
            if sock is not None:
                sock.close()


SOCKET_PATH_ROOT = "/var/run/defence360agent/simple_rpc.sock"
SOCKET_PATH_USER = "/var/run/defence360agent/non_root_simple_rpc.sock"
UPGRADE_MARKER_FILE = "/var/imunify360/upgrade_process_started"


class ExecuteError(Exception):
    def __str__(self):
        return "ExecuteError: " + super(ExecuteError, self).__str__()


def is_in_upgrade_process():
    return os.path.isfile(UPGRADE_MARKER_FILE)


def execute(command):
    if is_in_upgrade_process():
        handle_upgrading(command)
        return

    socket_path = SOCKET_PATH_ROOT if os.getegid() == 0 else SOCKET_PATH_USER

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(socket_path)
            sock.sendall(str.encode(command) + b"\n")

            fd_list = [sock.fileno()]
            rwx_list = select.select(fd_list, [], [], 180)

            if sock.fileno() not in rwx_list[0]:
                raise Exception("Request timeout")

            response = sock.makefile(encoding="utf-8").readline()
            if not response:
                raise Exception("Empty response from socket")

            print(response)
    except (ConnectionRefusedError, FileNotFoundError, PermissionError):
        print_response()


def print_response(resp_data=None, resp_status=None, result="error"):
    if resp_status is None:
        resp_status = get_status()

    print(
        json.dumps(
            dict(
                result=result,
                messages=[],
                data=resp_data,
                status=resp_status,
            )
        )
    )


def _get_chunk(offset, limit):
    try:
        with open("/var/log/i360deploy.log", "r") as f:
            f.seek(offset)
            for i in range(10):
                chunk = f.read(limit)
                if chunk == "":
                    time.sleep(1)
                else:
                    return chunk
    except (IOError, OSError, ValueError):
        return "Error reading file i360deploy.log"
    return ""


def print_upgrading_status(offset, limit):
    chunk = _get_chunk(offset, limit)
    resp_data = dict(
        items=dict(
            log=chunk,
            offset=offset + len(chunk),
        )
    )
    print_response(
        resp_data,
        resp_status=Status.UPGRADING,
        result="success",
    )


def handle_upgrading(command):
    request = json.loads(command)

    if request.get("command") == ["upgrading", "status"]:
        params = request.get("params")
        print_upgrading_status(params["offset"], params["limit"])
    else:
        print_response(resp_status=get_status(), result="error")


def upload_file(params):
    params = json.loads(params)
    upload_path = "/var/imunify360/uploads"
    uploaded = []

    for tmp_path, file_name in params.get("files", {}).items():
        file_name = os.path.basename(file_name)
        if not file_name:
            raise ValueError("Empty filename after sanitization")
        file_name = file_name.encode("utf-8")
        path = os.path.join(bytes(upload_path, "utf-8"), file_name)
        real_path = os.path.realpath(path)
        real_base = os.path.realpath(upload_path).encode("utf-8")
        if not real_path.startswith(real_base + b"/"):
            raise ValueError("File path outside upload directory")
        # Source path is also user-controlled (dict key from panel JSON);
        # without these checks an attacker could move arbitrary system
        # files since shutil.move/chown/chmod run as root.
        tmp_path_bytes = tmp_path.encode("utf-8")
        st = os.lstat(tmp_path_bytes)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("Source is not a regular file")
        if st.st_uid == 0:
            raise ValueError("Refusing to move root-owned source file")
        shutil.move(tmp_path_bytes, path)
        os.chown(path, 0, 0)
        os.chmod(path, 0o600)
        uploaded.append(path)

    random_name = "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )
    zip_file = random_name + ".zip"
    zip_path = os.path.join("/var/imunify360/uploads", zip_file)
    subprocess.call(
        ["zip", "-j", "-m", "--password", "1", zip_path] + uploaded,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    os.chown(zip_path, 0, 0)
    os.chmod(zip_path, 0o600)

    result = {
        "result": "success",
        "data": zip_path,
    }

    print(json.dumps(result))


#  Imunify Email
#
# This dispatch is reached by the cPanel Perl plugin
# (cpanel/handlers/Imunify/Wrapper.pm::imunfyEmailRequest), which forwards
# the IE request to IE-quarantine through this script. Authentication on
# the IE side is peercred-based on cPanel: the WHM/cpanel CGI runs under
# the calling user's UID and IE-quarantine accepts that identity directly.
#
# The Generic PHP plugin does NOT use this dispatch — it talks to
# IE-quarantine through ui/agent/plugins/common/classes/ImunifyEmailClient
# with an HS256 JWT.

IMUNIFYEMAIL_SOCKET_PATH = "/var/run/imunifyemail/quarantine.sock"

if os.path.exists(IMUNIFYEMAIL_SOCKET_PATH):
    import urllib3.connection

    class HttpUdsConnection(urllib3.connection.HTTPConnection):
        def __init__(self, socket_path, *args, **kw):
            self.socket_path = socket_path
            super().__init__(*args, **kw)

        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect(self.socket_path)


_IE_PUBLIC_NON_ADMIN_ROUTES = frozenset({("version",)})


def _ie_segment_is_safe(segment):
    return (
        isinstance(segment, str)
        and segment
        and segment != "."
        and segment != ".."
        and "/" not in segment
        and "\\" not in segment
        and "\x00" not in segment
    )


def imunifyemail(command):
    command = json.loads(command)
    segments = command["command"]
    # The JSON payload is caller-controlled (any local user can invoke
    # this script directly); admin status and account scope must come
    # from EUID, which the Perl wrapper drops before exec for non-admins.
    # Validate segments before any URL construction so a non-admin
    # cannot smuggle traversal artefacts past the {account_name} gate.
    if not isinstance(segments, list) or not segments or not all(
        _ie_segment_is_safe(seg) or seg == "{account_name}"
        for seg in segments
    ):
        print(
            json.dumps(
                {"result": "error", "messages": ["Permission denied"]}
            )
        )
        return
    euid = os.geteuid()
    if euid == 0:
        account_name = command.get("username", "")
    elif "{account_name}" in segments:
        account_name = pwd.getpwuid(euid).pw_name
    elif tuple(segments) in _IE_PUBLIC_NON_ADMIN_ROUTES:
        account_name = ""
    else:
        print(
            json.dumps(
                {"result": "error", "messages": ["Permission denied"]}
            )
        )
        return
    method_path = "/".join(segments)
    con = HttpUdsConnection(IMUNIFYEMAIL_SOCKET_PATH, "localhost")
    url = ("/quarantine/api/v1/" + method_path).format(
        account_name=account_name
    )
    try:
        con.request(
            command["params"]["request_method"].upper(),
            url + "?" + urlencode(command["params"], doseq=True),
            body=json.dumps(command["params"]),
        )
    except Exception as e:
        print(
            json.dumps(
                {
                    "messages": str(e),
                    "result": "error",
                }
            )
        )
        return

    data = []
    response = con.getresponse()
    response_text = response.read()
    if response_text:
        response_text = json.loads(response_text) or []
        if "items" in response_text:
            data = response_text
        else:
            data = dict(items=response_text)

    messages = (
        "Something went wrong please try again"
        if response.status != 200
        else ""
    )

    print(
        json.dumps(
            dict(
                result="success" if response.status == 200 else "error",
                messages=messages,
                status=response.status,
                data=data,
            )
        )
    )


if __name__ == "__main__":
    action = sys.argv[1]
    encoded_data = fileinput.input(files=sys.argv[2:]).readline()
    data = base64.b64decode(encoded_data).decode()
    dispatcher = {
        "execute": execute,
        "uploadFile": upload_file,
        "imunifyEmail": imunifyemail,
    }

    try:
        dispatcher.get(action, execute)(data)
    except Exception as e:
        print(
            json.dumps(
                {
                    "messages": str(e),
                    "result": "error",
                }
            )
        )
