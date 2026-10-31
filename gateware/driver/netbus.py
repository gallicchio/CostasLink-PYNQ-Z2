"""netbus.py: the CostasLink driver across the network, so one program on the bench PC drives the board and the
lab instruments together and logs both (bring-up, 2026-10-28).

    # on the PYNQ-Z2, as root (pynq_serve.sh sources PYNQ's Python first):
    sudo ./pynq_serve.sh                         # the overlay beside it; port 5800 on every interface
    # on a PC without the board (rehearsal): the same server around the RTL simulation (tb_pipe.v, Icarus)
    python3 netbus.py serve --sim

    # on the bench PC
    from netbus import RemoteCostasLink
    cl = RemoteCostasLink("192.168.2.99")      # the PYNQ's address
    cl.info(); cl.bringup_stage1(); cl.detectors()
    cl.capture("tx_event", post=256, start=cl.tx_one)    # a method passed as an argument runs on the board
    cl.rd("ID"); cl.bus.read(0x00)             # registers by name, or the raw bus

Every CostasLink method runs ON THE BOARD, one request and one reply each, so a capture's 8192 register reads cost
one round trip, not 8192.  `NetBus` is also a plain bus (read / write), for a CostasLink built on this side.

The protocol: one JSON object a line each way over TCP.  Requests {"op": "call", "name": "detectors", "args": [],
"kwargs": {}}, {"op": "get", "name": "ser"}, {"op": "rd", "reg": 0}, {"op": "wr", "reg": 1, "value": 3},
{"op": "batch", "ops": [...]}, {"op": "ping"}, {"op": "names"}; replies {"ok": true, "result": ...} or
{"ok": false, "error": "...", "traceback": "..."}.  An argument {"__method__": "tx_one"} becomes the board's own
bound method.  Only the CostasLink's public names are reachable (no leading underscore), one request at a time
(a lock), no authentication: run it on the lab's network or a direct cable, not the internet.
"""
import argparse
import hashlib
import json
import os
import socket
import socketserver
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PORT = 5800
# requests that only look: they do not make the caller the board's driver (linkd stays active, the status page does not
# say 'being driven'): the bench's watchdog reads the detectors every half minute (BRINGUP_LOG 4.15)
OBSERVE_OPS = {"ping", "names", "get", "rd"}
OBSERVE_CALLS = {"detectors", "info", "status", "pll_locked", "ihold_state", "shold_state", "cdr_state", "cmp_state",
                 "dac_volts", "ber", "i2c_lines", "temperature", "adc", "adc_all", "det_adc", "lock_state"}


def driver_id(path=None):
    """the driver's identity: the first 12 hex digits of costaslink.py's sha256.  The server reports the one it
    loaded, the client compares its own: a server started from an older copy runs the older defaults (2026-10-31: the
    weekend's interference hold released at 1 ms, the PYNQ's copy older than the repository's 20 ms)"""
    with open(path or os.path.join(HERE, "costaslink.py"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def _jsonable(o):
    """json.dumps' fallback: tuples are lists already; bytes as a list of ints; anything else by name"""
    if isinstance(o, (bytes, bytearray)):
        return list(o)
    if hasattr(o, "name") and hasattr(o, "msgs"):          # a Scheme
        return {"scheme": o.name, "text": o.text}
    return repr(o)


# ---------------------------------------------------------------------------------------------------------
# the server (on the board)
# ---------------------------------------------------------------------------------------------------------
class Server:
    def __init__(self, cl):
        self.cl = cl
        self.lock = threading.Lock()
        self.t0 = time.time()
        self.requests = 0
        self.last = {"peer": None, "op": None, "name": None, "t": None}   # who drove the board last (the dashboard shows it)
        try:
            self.driver = driver_id(sys.modules[type(cl).__module__].__file__)
        except (OSError, AttributeError, KeyError):
            self.driver = None

    def _public(self, name):
        if not isinstance(name, str) or name.startswith("_") or not hasattr(self.cl, name):
            raise AttributeError("no public name %r on the board's CostasLink" % (name,))
        return getattr(self.cl, name)

    def _resolve(self, a):
        if isinstance(a, dict) and set(a) == {"__method__"}:
            return self._public(a["__method__"])
        if isinstance(a, list):
            return [self._resolve(x) for x in a]
        return a

    def _reg(self, reg):
        import regmap
        return regmap.BY_NAME[reg] if isinstance(reg, str) else int(reg)

    def op(self, req):
        op = req.get("op")
        if op == "ping":
            return {"time": time.time(), "host": socket.gethostname(), "uptime_s": time.time() - self.t0,
                    "requests": self.requests, "pid": os.getpid(), "driver": self.driver}
        if op == "names":
            methods, values = [], {}
            for n in dir(self.cl):
                if n.startswith("_"):
                    continue
                v = getattr(self.cl, n)
                if callable(v):
                    methods.append(n)
                elif isinstance(v, (int, float, str, bool, type(None), dict, list, tuple)):
                    values[n] = v
            return {"methods": methods, "values": values}
        if op == "rd":
            return self.cl.bus.read(self._reg(req["reg"]))
        if op == "wr":
            self.cl.bus.write(self._reg(req["reg"]), int(req["value"]))
            return None
        if op == "get":
            v = self._public(req["name"])
            if callable(v):
                raise TypeError("%s is a method: use call" % req["name"])
            return v
        if op == "call":
            fn = self._public(req["name"])
            if not callable(fn):
                raise TypeError("%s is not a method: use get" % req["name"])
            args = self._resolve(req.get("args") or [])
            kwargs = {k: self._resolve(v) for k, v in (req.get("kwargs") or {}).items()}
            return fn(*args, **kwargs)
        if op == "batch":
            return [self.op(r) for r in req["ops"]]
        raise ValueError("unknown op %r" % (op,))

    def handle_line(self, line, peer=None):
        try:
            req = json.loads(line)
            with self.lock:
                self.requests += 1
                if not (req.get("op") in OBSERVE_OPS or (req.get("op") == "call" and req.get("name") in OBSERVE_CALLS)):
                    self.last = {"peer": peer, "op": req.get("op"), "name": req.get("name") or req.get("reg"), "t": time.time()}
                result = self.op(req)
            return json.dumps({"ok": True, "result": result}, default=_jsonable)
        except Exception as e:                                       # noqa: BLE001 - every error goes back to the caller
            return json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                               "traceback": traceback.format_exc()})

    def tcp_server(self, bind="0.0.0.0", port=PORT, quiet=False):
        """the listening socket (port 0: any free one, tcp.server_address says which); serve_forever() runs it"""
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                peer = "%s:%d" % self.client_address[:2]
                if not quiet:
                    print("connect", peer, flush=True)
                for raw in self.rfile:
                    line = raw.decode("utf-8", "replace").strip()
                    if line:
                        self.wfile.write((server.handle_line(line, peer) + "\n").encode())
                        self.wfile.flush()
                if not quiet:
                    print("disconnect", peer, flush=True)

        class TCP(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        return TCP((bind, port), Handler)

    def serve(self, bind="0.0.0.0", port=PORT, dashboard=None, linkd=False):
        """dashboard: a port for the read-only status page (dashboard.py), or None; linkd: the link's automatic
        recovery (linkd.py), active whenever no client has driven the board for a minute"""
        self.linkd = None
        if linkd:
            try:
                from linkd import LinkD
                self.linkd = LinkD(self).start()
            except Exception as e:                                   # noqa: BLE001 - the driver is served regardless
                print("no linkd: %s: %s" % (type(e).__name__, e), flush=True)
        if dashboard:
            try:
                from dashboard import Dashboard
                Dashboard(self, port=dashboard).start()
            except Exception as e:                                   # noqa: BLE001 - the driver is served regardless
                print("no dashboard: %s: %s" % (type(e).__name__, e), flush=True)
        with self.tcp_server(bind, port) as tcp:
            print("CostasLink netbus on %s:%d (%s)" % (bind, port, json.dumps(self.cl.info(), default=_jsonable)),
                  flush=True)
            tcp.serve_forever()


# ---------------------------------------------------------------------------------------------------------
# the client (on the bench PC)
# ---------------------------------------------------------------------------------------------------------
class RemoteError(Exception):
    """an exception on the board, with its traceback there"""

    def __init__(self, error, tb=""):
        super().__init__(error)
        self.remote_traceback = tb


class NetBus:
    """the connection: request() for any op, and read / write so it is a bus as well"""

    def __init__(self, host, port=PORT, timeout=120.0):
        self.host, self.port = host, port
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.f = self.sock.makefile("rwb")
        self.lock = threading.Lock()

    def request(self, req, timeout=None):
        with self.lock:
            if timeout is not None:
                self.sock.settimeout(timeout)
            self.f.write((json.dumps(req, default=_jsonable) + "\n").encode())
            self.f.flush()
            line = self.f.readline()
        if not line:
            raise IOError("the board's server closed the connection")
        rep = json.loads(line)
        if not rep["ok"]:
            raise RemoteError(rep["error"], rep.get("traceback", ""))
        return rep["result"]

    def read(self, reg):
        return self.request({"op": "rd", "reg": reg})

    def write(self, reg, value):
        self.request({"op": "wr", "reg": reg, "value": int(value)})

    def ping(self):
        t0 = time.time()
        r = self.request({"op": "ping"})
        r["round_trip_ms"] = (time.time() - t0) * 1e3
        return r

    def close(self):
        try:
            self.f.close()
        finally:
            self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _Method:
    def __init__(self, bus, name):
        self._bus, self._name = bus, name

    def __call__(self, *args, net_timeout=None, **kwargs):
        return self._bus.request({"op": "call", "name": self._name, "args": [_arg(a) for a in args],
                                  "kwargs": {k: _arg(v) for k, v in kwargs.items()}}, timeout=net_timeout)

    def __repr__(self):
        return "<the board's CostasLink.%s>" % self._name


def _arg(a):
    if isinstance(a, _Method):
        return {"__method__": a._name}
    if isinstance(a, (list, tuple)):
        return [_arg(x) for x in a]
    return a


class RemoteCostasLink:
    """the board's CostasLink, method for method: cl.detectors() runs there and returns its result here.
    A method takes net_timeout= (seconds) for a long one (survey, ber_run; 120 s by default), so the board's own
    timeout= arguments still reach it.  Values (ser, t_sample, clk_mhz ...)
    are read from the board each time."""

    def __init__(self, host, port=PORT, timeout=120.0):
        self.bus = NetBus(host, port, timeout)
        names = self.bus.request({"op": "names"})
        self._methods = set(names["methods"])
        self.driver = self.bus.ping().get("driver")
        self.driver_here = driver_id()
        if self.driver != self.driver_here:
            sys.stderr.write("netbus: the board's server runs driver %s, this side's costaslink.py is %s: its defaults "
                             "may differ (copy the driver over and restart the server)\n" % (self.driver, self.driver_here))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._methods:
            return _Method(self.bus, name)
        return self.bus.request({"op": "get", "name": name})

    def close(self):
        self.bus.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="on the board (as root): load the overlay and serve the driver")
    s.add_argument("--bit", default=os.path.join(HERE, "costaslink_top.bit"))
    s.add_argument("--no-download", action="store_true", help="the overlay is loaded already (a Jupyter cell)")
    s.add_argument("--sim", action="store_true", help="serve the RTL simulation instead (no board, no pynq)")
    s.add_argument("--bind", default="0.0.0.0")
    s.add_argument("--port", type=int, default=PORT)
    s.add_argument("--dashboard", type=int, default=None, metavar="PORT", help="also serve the status page (dashboard.py)")
    s.add_argument("--linkd", action="store_true", help="the link's automatic recovery (linkd.py) while no client drives")
    p = sub.add_parser("ping", help="on the PC: is the server there, and what does the board say")
    p.add_argument("host")
    p.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()
    if a.cmd == "serve":
        from costaslink import CostasLink
        if a.sim:
            from sim_pipe import PipeBus
            bus = PipeBus(ser=8)
        else:
            from costaslink import PynqBus
            bus = PynqBus(a.bit, download=not a.no_download)
        Server(CostasLink(bus)).serve(a.bind, a.port, dashboard=a.dashboard, linkd=a.linkd)
    else:
        with NetBus(a.host, a.port, timeout=10) as nb:
            print(json.dumps(nb.ping(), indent=1))
            print(json.dumps(nb.request({"op": "call", "name": "info"}), indent=1))


if __name__ == "__main__":
    main()
