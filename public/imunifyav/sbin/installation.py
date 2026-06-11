#!/usr/bin/env python

import atexit
import base64
import json
import os
import socket
import subprocess
import sys
import time


# this code is copy-pasted because execute.py is
# copied into /usr/bin directory in .spec
# also present in execute.py
class Status:
    INSTALLING = "installing"
    OK = "running"
    NOT_INSTALLED = "not_installed"
    FAILED_TO_INSTALL = "failed_to_install"
    STOPPED = "stopped"
    SOCKET_INACCESSIBLE = "socket_inaccessible"
    DOWNGRADING = "downgrading"


class ImunifyPluginName:
    IMUNIFY_360 = "360"
    IMUNIFY_AV = "AV"


class ImunifyPluginDeployScript:
    IMUNIFY_360 = "i360deploy.sh"
    IMUNIFY_AV = "imav-deploy.sh"


class ImunifyPluginLogs:
    IMUNIFY_360 = "/var/log/i360deploy.log"
    IMUNIFY_AV = "/var/log/imav-deploy.log"

def is_i360_downgrade_running():
    try:
        proc = subprocess.Popen(["ps", "ax", "-o", "args="], stdout=subprocess.PIPE)
        out = proc.stdout.read()
        try:
            ps_text = out.decode("utf-8", "ignore")
        except Exception:
            ps_text = out
        for line in ps_text.splitlines():
            if ImunifyPluginDeployScript.IMUNIFY_360 in line:
                tokens = line.split()
                if ("-d" in tokens) or ("--downgrade" in tokens):
                    return True
    except Exception:
        pass
    return False

def get_status():
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
            try:
                sock.connect("/var/run/defence360agent/simple_rpc.sock")
            except socket.error as e:
                if e.errno == 13:
                    return Status.SOCKET_INACCESSIBLE
                raise e
            return Status.OK
        except Exception:  # noqa
            if os.path.exists("/usr/bin/imunify360-agent"):
                return Status.STOPPED
            else:
                if os.path.exists(
                    "/usr/local/psa/var/modules/imunify360/installation.log"
                ):
                    return Status.FAILED_TO_INSTALL
                return Status.NOT_INSTALLED
        finally:
            if sock is not None:
                sock.close()


var_dir = "/usr/local/psa/var/modules/imunify360"
file_prefix = var_dir + "/installation."
socket_path = file_prefix + "sock"


def print_response(data):
    json.dump(data, sys.stdout)
    sys.stdout.write("\n")


class Daemon:
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """

    def __init__(self):
        self.stdin = "/dev/null"
        self.stdout = "/dev/null"
        self.stderr = "/dev/null"
        self.pidfile = file_prefix + "pid"
        if not os.path.exists(var_dir):
            os.makedirs(var_dir)
        self.log_file = open(file_prefix + "log", "w")

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                # https://unix.stackexchange.com/questions/447898/why-does-a-program-with-fork-sometimes-print-its-output-multiple-times
                # plesk collects stdout from all forked processes
                time.sleep(1)
                print_response(
                    dict(
                        result="success",
                        data=None,
                        messages=[],
                        status=get_status(),
                    )
                )
                # exit first parent
                sys.exit(0)
        except OSError as e:
            sys.stderr.write(
                "fork #1 failed: %d (%s)\n" % (e.errno, e.strerror)
            )
            sys.exit(1)
        self.log_file.write("Installation daemon forked first time\n")
        # buffer will be duplicated
        self.log_file.flush()
        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError as e:
            sys.stderr.write(
                "fork #2 failed: %d (%s)\n" % (e.errno, e.strerror)
            )
            sys.exit(1)
        self.log_file.write("Installation daemon forked second time\n")

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(self.stdin, mode="rb")
        so = open(self.stdout, mode="a+b")
        se = open(self.stderr, mode="a+b", buffering=0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        open(self.pidfile, "w+").write("%s\n" % pid)
        self.log_file.write("Installation daemon initialized\n")

    def delpid(self):
        os.remove(self.pidfile)
        self.log_file.close()

    def start(self, params):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = open(self.pidfile, "r")
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(0)
        self.log_file.write(
            "Installation daemon created pid file " + str(self.pidfile) + "\n"
        )
        # daemonization will duplicate buffer
        self.log_file.flush()

        # Start the daemon
        self.daemonize()
        self.run(params)

    def run(self, params):
        deploy_scripts_mapping = {
            ImunifyPluginName.IMUNIFY_AV: ImunifyPluginDeployScript.IMUNIFY_AV,
            ImunifyPluginName.IMUNIFY_360: ImunifyPluginDeployScript.IMUNIFY_360,
        }
        deploy_script = deploy_scripts_mapping.get(
            params.get("plugin_name"), ImunifyPluginDeployScript.IMUNIFY_AV
        )
        license_key = params.get("license_key", None)
        self.log_file.write("Starting {}\n".format(deploy_script))
        deploy_script_dir = "/usr/local/psa/admin/sbin/modules/imunify360"
        command = [
            os.path.join(deploy_script_dir, deploy_script),
            "-y",
            "--force",
        ]
        if license_key:
            command.extend(["--key", license_key])
        # flush to make i360deploy.sh write AFTER logs of this file
        self.log_file.flush()

        def preexec_fn():
            os.setsid()
            # need to set working directory, since deployscript can update
            # itself only if located inside working directory
            os.chdir(deploy_script_dir)

        deploy_env = os.environ.copy()
        deploy_env["I360_FROM_PLESK_EXTENSION"] = "1"

        p = subprocess.Popen(
            command,
            preexec_fn=preexec_fn,
            stdout=self.log_file.fileno(),
            stderr=self.log_file.fileno(),
            universal_newlines=True,
            env=deploy_env,
        )

        p.wait(60 * 60)


def run_deploy_in_systemd(params):
    systemd_run_command = "/usr/bin/systemd-run"
    if os.path.exists(systemd_run_command):
        log_file = open(file_prefix + "log", "w")
        log_file.write("Installation by systemd-run initialized\n")
        # for SELinux we have to temporary change selinux mode to permissive
        p = subprocess.Popen(
            [systemd_run_command, "--version"], stdout=subprocess.PIPE
        )
        out, _ = p.communicate()
        systemd_version = out.decode().split()[1]
        log_file.write("systemd version = %s\n" % systemd_version)

        prefix = [systemd_run_command]

        if systemd_version < "235":
            log_mapping = {
                ImunifyPluginName.IMUNIFY_AV: ImunifyPluginLogs.IMUNIFY_AV,
                ImunifyPluginName.IMUNIFY_360: ImunifyPluginLogs.IMUNIFY_360,
            }

            log_file.write(
                "We can't redirect log, look at %s\n"
                % log_mapping.get(
                    params.get("plugin_name"), ImunifyPluginLogs.IMUNIFY_AV
                )
            )
        else:
            prefix += ["-P"]

        unenforce = False
        if os.path.exists("/etc/selinux/config"):
            p = subprocess.Popen(["getenforce"], stdout=subprocess.PIPE)
            out, _ = p.communicate()
            log_file.write("semode = %s" % out.decode())
            if b"Enforcing" in out:
                res = subprocess.call(["setenforce", "0"])
                unenforce = True
                log_file.write("selinux mode changed %r\n" % res)

        prefix = prefix + [
            "-p",
            "SendSIGKILL=no",
            "--slice=imunify_install",
            "--setenv=I360_FROM_PLESK_EXTENSION=1",
            "--",
        ]
        deploy_scripts_mapping = {
            ImunifyPluginName.IMUNIFY_AV: ImunifyPluginDeployScript.IMUNIFY_AV,
            ImunifyPluginName.IMUNIFY_360: ImunifyPluginDeployScript.IMUNIFY_360,
        }
        deploy_script = deploy_scripts_mapping.get(
            params.get("plugin_name"), ImunifyPluginDeployScript.IMUNIFY_AV
        )
        log_file.write("Starting {}\n".format(deploy_script))
        license_key = params.get("license_key", None)
        deploy_script_dir = "/usr/local/psa/admin/sbin/modules/imunify360"
        command = prefix + [
            os.path.join(deploy_script_dir, deploy_script),
            "-y",
            "--force",
        ]
        if license_key:
            command.extend(["--key", license_key])
        log_file.flush()

        def preexec_fn():
            os.setsid()
            # need to set working directory, since deployscript can update
            # itself only if located inside working directory
            os.chdir(deploy_script_dir)

        subprocess.Popen(
            command,
            preexec_fn=preexec_fn,
            stdout=log_file.fileno(),
            stderr=log_file.fileno(),
            universal_newlines=True,
        )
        time.sleep(3)
        if unenforce:
            res = subprocess.call(["setenforce", "1"])
            log_file.write("selinux mode return-back %r\n" % res)
            log_file.flush()
        print_response(
            dict(
                result="success",
                data=None,
                messages=[],
                status=get_status(),
            )
        )
        return True
    else:
        return False


def _get_chunk(offset, limit):
    try:
        with open(file_prefix + "log", "r") as f:
            f.seek(offset)
            # can not use select
            for i in range(10):
                chunk = f.read(limit)
                if chunk == "":
                    time.sleep(1)
                else:
                    return chunk
    except:  # noqa
        pass
    return ""


def status(offset, limit):
    chunk = _get_chunk(offset, limit)
    print_response(
        dict(
            status=get_status(),
            result="success",
            messages=[],
            data=dict(
                items=dict(
                    log=chunk,
                    offset=offset + len(chunk),
                )
            ),
        )
    )


if __name__ == "__main__":
    request = json.loads(base64.b64decode(sys.argv[1]))
    method = request["method"]
    if method == ["start"]:
        if not run_deploy_in_systemd(request["params"]):
            Daemon().start(request["params"])
    elif method == ["status"]:
        status(request["params"]["offset"], request["params"]["limit"])
    else:
        sys.stderr.write("Could not parse input " + str(sys.argv))
