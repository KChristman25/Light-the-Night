#!/usr/bin/env python3
import asyncio, time, json, hashlib, contextlib, signal
from typing import Dict, Any, Optional, List
import aiohttp
import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = "light-the-night-2025"
SERVICE_ACCOUNT = "/home/pi/webswitch/serviceAccount.json"
HEARTBEAT_SEC = 10
BROADCAST_WINDOW_SEC = 3600

cred = credentials.Certificate(SERVICE_ACCOUNT)
firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
db = firestore.client()

def hash_str(s): return hashlib.sha1(s.encode()).hexdigest()[:10]
def now_ms(): return int(time.time() * 1000)

class Bus:
    def __init__(self): self.waiters = {}; self.last = 0
    def emit(self,name,payload):
        if name in self.waiters:
            for f in self.waiters[name]:
                if not f.done(): f.set_result(payload)
            self.waiters[name].clear()
    async def wait(self,name,timeout=None):
        fut = asyncio.get_event_loop().create_future()
        self.waiters.setdefault(name,[]).append(fut)
        try: return await asyncio.wait_for(fut,timeout)
        except asyncio.TimeoutError: return None
BUS = Bus()

class HTTP:
    async def __aenter__(self): self.sess=aiohttp.ClientSession();return self
    async def __aexit__(self,*a): await self.sess.close()
    async def get(self,url):
        try:
            async with self.sess.get(url) as r:
                print("[HTTP]",r.status,url)
        except Exception as e: print("[HTTP ERR]",url,e)

class Runner:
    def __init__(self,name,ref): self.name=name;self.ref=ref;self.enabled=False;self.prog=None;self.unsub=None;self.stop=False
    async def start(self):
        def cb(docs,_,__):
            for doc in docs:
                data=doc.to_dict() or {}
                self.enabled=data.get("enabled",False)
                self.prog=data.get("program")
                print(f"[{self.name}] update enabled={self.enabled}")
        self.unsub=self.ref.on_snapshot(cb)
        asyncio.create_task(self.loop())
    async def loop(self):
        async with HTTP() as http:
            while not self.stop:
                if not self.enabled or not self.prog: await asyncio.sleep(1); continue
                try: await self.run_prog(http)
                except Exception as e: print(f"[{self.name}] ERR",e); await asyncio.sleep(1)
    async def run_prog(self,http):
        p=self.prog; repeat=p.get("repeat","once")
        loops=1 if repeat=="once" else (float("inf") if repeat=="forever" else int(repeat))
        for _ in range(int(loops)):
            if self.stop: break
            for s in p.get("steps",[]):
                if self.stop: break
                await self.step(http,s)
    async def step(self,http,s):
        c=s.get("cmd")
        if c=="http": await http.get(s.get("url"))
        elif c=="delay": await asyncio.sleep(s.get("ms",0)/1000)
        elif c=="broadcast":
            d={"name":s.get("name"),"payload":s.get("payload",{}),"from":self.name,"createdAt":firestore.SERVER_TIMESTAMP}
            await db.collection("broadcasts").add(d); BUS.emit(s.get("name"),d)
        elif c=="waitBroadcast":
            print(f"[{self.name}] waiting for {s.get('name')}")
            await BUS.wait(s.get("name"),(s.get("timeoutMs") or 0)/1000 or None)
        elif c=="log": print(f"[{self.name}] LOG:",s.get("msg"))
        elif c=="sequence":
            for sub in s.get("steps",[]): await self.step(http,sub)

async def broadcast_listener():
    def cb(docs,chg,_):
        for ch in chg:
            if ch.type.name!="ADDED": continue
            d=ch.document.to_dict() or {}
            BUS.emit(d.get("name"),d)
            print("[BUS]",d.get("name"),d.get("payload"))
    return db.collection("broadcasts").order_by("createdAt",direction=firestore.Query.DESCENDING).limit(40).on_snapshot(cb)

RUNNERS={}
async def main():
    unsub_b=broadcast_listener()
    def prog_cb(col,chg,_):
        for c in chg:
            n=c.document.id
            if c.type.name=="ADDED" and n not in RUNNERS:
                r=Runner(n,c.document.reference)
                RUNNERS[n]=r; asyncio.create_task(r.start())
    unsub_p=db.collection("programs").on_snapshot(prog_cb)
    stop=asyncio.Event()
    def sig(*a): stop.set()
    signal.signal(signal.SIGINT,sig); signal.signal(signal.SIGTERM,sig)
    await stop.wait()
    unsub_p(); unsub_b()
asyncio.run(main())
