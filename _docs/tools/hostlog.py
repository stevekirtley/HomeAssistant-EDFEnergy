"""mitmproxy addon: append every upstream host to a file, flushed immediately."""
import datetime

LOGFILE = "/tmp/edf_hosts.log"


def server_connect(data):
    try:
        addr = data.server.address
        host = addr[0] if addr else "?"
        port = addr[1] if addr and len(addr) > 1 else "?"
        sni = getattr(data.server, "sni", None)
        line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {host}:{port}"
        if sni and sni != host:
            line += f" sni={sni}"
        with open(LOGFILE, "a") as fh:
            fh.write(line + "\n")
    except Exception as exc:  # never break the proxy
        with open(LOGFILE, "a") as fh:
            fh.write(f"ERR {exc!r}\n")
