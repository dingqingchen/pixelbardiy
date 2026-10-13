"""Offline lossless encoding for ten verified 1024-byte stock backgrounds.

Token high bit: repeat next byte 1..128 times; otherwise copy 1..128 literals.
No device access, no firmware output. The original assets remain authoritative.
"""
def pack(data):
    result=bytearray(); i=0
    while i<len(data):
        run=1
        while i+run<len(data) and data[i+run]==data[i] and run<128:run+=1
        if run>=3:
            result.extend((0x80|(run-1),data[i])); i+=run
        else:
            start=i; i+=run
            while i<len(data) and i-start<128:
                run=1
                while i+run<len(data) and data[i+run]==data[i] and run<128:run+=1
                if run>=3:break
                i+=min(run,128-(i-start))
            result.append(i-start-1); result.extend(data[start:i])
    return bytes(result)


def unpack(data, expected=1024):
    out=bytearray();i=0
    while i<len(data):
        token=data[i];i+=1;count=(token&127)+1
        if len(out)+count>expected:raise ValueError('Output overflow')
        size=1 if token&128 else count
        if i+size>len(data):raise ValueError('Truncated token')
        out.extend(data[i:i+1]*count if token&128 else data[i:i+count]);i+=size
    if len(out)!=expected:raise ValueError('Wrong decoded size')
    return bytes(out)


if __name__=='__main__':
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'firmware-analysis/v137/mcu.bin'
    image=source.read_bytes(); sizes=[]
    for address in range(0x0800AF24,0x0800D724,1024):
        raw=image[address-0x08002000:address-0x08002000+1024]
        compressed=pack(raw);assert unpack(compressed)==raw;sizes.append(len(compressed))
    print({'original':10240,'compressed':sum(sizes),'sizes':sizes,'saved_before_decoder':10240-sum(sizes)})
