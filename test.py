import struct

a=bytearray(struct.pack("!???IIIH", True, False, True, 4294967295, 4294967295, 4294967295, 6667))
s="test message".encode()
a.extend(s)
a=bytes(a)
print(a)

# i=iter(a)
# for x, y in zip(i, i):
#     print(x, y)

b=struct.unpack("!???IIIH", a[:17])
print(b)

print(type(b[6]))
msg=a[17:].decode()
print(msg)

