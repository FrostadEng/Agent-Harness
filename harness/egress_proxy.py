"""Minimal hostname-allowlisting HTTP CONNECT proxy for Codex control-plane egress."""
import asyncio,os,sys
ALLOWED=tuple(x.strip().lower() for x in os.environ.get("CODEX_CONTROL_PLANE_HOSTS","").split(",") if x.strip())
def permitted(host): return any(host==d or host.endswith("."+d) for d in ALLOWED)
async def relay(reader,writer):
    try:
        line=await reader.readline(); parts=line.decode("latin1").split()
        while await reader.readline() not in (b"\r\n",b"\n",b""): pass
        if len(parts)!=3 or parts[0]!="CONNECT": raise ValueError
        host,port=parts[1].rsplit(":",1)
        if not permitted(host.lower()):
            print(f"DENY control-plane host {host}",file=sys.stderr,flush=True)
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n"); await writer.drain(); return
        rr,rw=await asyncio.open_connection(host,int(port)); writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n"); await writer.drain()
        async def copy(r,w):
            try:
                while data:=await r.read(65536): w.write(data); await w.drain()
            finally: w.close()
        await asyncio.gather(copy(reader,rw),copy(rr,writer))
    except Exception:
        try: writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n"); await writer.drain()
        except Exception: pass
    finally: writer.close()
async def main():
    server=await asyncio.start_server(relay,"0.0.0.0",8080)
    async with server: await server.serve_forever()
def serve(): asyncio.run(main())
