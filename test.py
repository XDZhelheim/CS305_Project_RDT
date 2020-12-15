import struct

a=bytearray(struct.pack("!???IIIH", True, False, True, 4294967295, 4294967295, 4294967295, 6667))
s="test message".encode()
a.extend(s)
a=bytes(a)
print(a)
b=struct.unpack("!???IIIH", a[:17])
print(b)
msg=a[17:].decode()
print(msg)
i=4294967295
print(type(i))