"""HPL2 offline packet planner. No HID/serial APIs: unsafe on stock firmware.

Application acceptance cannot be inferred from the USB bridge's transport ACK.
Live transport remains disabled until firmware identity and recovery are verified.
"""
import binascii
import struct

ACQUIRE,HEARTBEAT,BEGIN,DATA,RELEASE=range(1,6)


def payload(op,sid,frame=0,index=0,data=b''):
    if op not in range(1,6) or not 0<sid<=0xffffffff:raise ValueError('Invalid session')
    if not 0<=frame<=65535 or not 0<=index<=255 or len(data)>37:raise ValueError('Invalid fragment')
    if op!=DATA and data:raise ValueError('Unexpected control data')
    return b'HPL2'+bytes([op])+struct.pack('>IHB',sid,frame,index)+bytes([len(data)])+data


def uart_packet(body,prefix=b'\0\0'):
    data=prefix+b'\xff\xff'+body
    return b'BLT+DIY+DAT#'+len(data).to_bytes(2,'big')+data+b'\r\n'


def usb_payload(body):
    """Payload for existing command 0x17 DATA. Does not send it."""
    return b'\0\x02\xff\xff'+body


class SessionPlan:
    """Pure packet/lifecycle planner, driven by a caller's monotonic seconds."""
    def __init__(self,sid):
        payload(ACQUIRE,sid)
        self.sid=sid;self.running=False;self.closed=False;self.frame=0;self.next_heartbeat=0

    def start(self,now):
        if self.closed:raise RuntimeError('A released session ID must not be reused')
        self.running=True;self.next_heartbeat=now+.5
        return payload(ACQUIRE,self.sid)

    def heartbeat(self,now):
        if not self.running or now<self.next_heartbeat:return None
        self.next_heartbeat=now+.5
        return payload(HEARTBEAT,self.sid)

    def pixels(self,pixels):
        if not self.running:raise RuntimeError('No active plan')
        if len(pixels)!=1024:raise ValueError('Expected 1024 pixels bytes')
        if self.frame==65535:raise RuntimeError('Use a fresh session before frame ID wraps')
        self.frame+=1
        data=pixels+binascii.crc_hqx(pixels,0).to_bytes(2,'big')
        return [payload(BEGIN,self.sid,self.frame)]+[
            payload(DATA,self.sid,self.frame,i,data[off:off+37])
            for i,off in enumerate(range(0,len(data),37))]

    def stop(self):
        if not self.running:return None
        self.running=False;self.closed=True
        return payload(RELEASE,self.sid)


class OfflineSessionDriver:
    """Injectable lifecycle driver for the emulator; not a live HID backend.

    An eventual device backend must verify firmware identity and application
    acceptance, pace/retry packets, and close the handle separately. No transport
    acknowledgement is treated here as application acceptance.
    """
    def __init__(self,sid,emit):
        self.plan=SessionPlan(sid);self.emit=emit;self.last_pixels=None

    def start(self,now):self.emit(self.plan.start(now))

    def tick(self,now,pixels=None):
        heartbeat=self.plan.heartbeat(now)
        if heartbeat is not None:self.emit(heartbeat)
        if pixels is not None and pixels!=self.last_pixels:
            for packet in self.plan.pixels(pixels):self.emit(packet)
            self.last_pixels=bytes(pixels)

    def close(self):
        packet=self.plan.stop()
        if packet is not None:self.emit(packet)
