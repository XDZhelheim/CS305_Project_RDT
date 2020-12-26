import struct
from rdt import Segment

a = bytearray(struct.pack("!???IIIH", True, False, True, 4294967295, 4294967295, 4294967295, 6667))
s = "test message".encode()
a.extend(s)
a = bytes(a)
print(a)

# i=iter(a)
# for x, y in zip(i, i):
#     print(x, y)

a = b'\x01\x00\x01\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\x1a\x0btest message'
b = struct.unpack("!???IIIH", a[:17])
print(b)

# print(type(b[6]))
msg = a[17:].decode()
print(msg)

c=Segment(seq_num=1234, length=4, payload=b'4567').encode()
print(c)
print(Segment.check_checksum(c))
