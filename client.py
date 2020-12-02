from rdt import socket

SERVER_ADDRESS=""
SERVER_PORT=1234
BUFFER_SIZE=4096

msg=""

if __name__ == "__main__":
    client=socket()
    client.connect((SERVER_ADDRESS, SERVER_PORT))
    client.send(msg)
    data=client.recv(BUFFER_SIZE)
    client.close()