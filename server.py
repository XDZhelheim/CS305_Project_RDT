from rdt import socket

SERVER_ADDRESS=""
SERVER_PORT=1234

if __name__ == "__main__":
    server=socket()
    server.bind((SERVER_ADDRESS, SERVER_PORT))
    while True:
        conn, client= server.accept()
        while True:
            data=conn.recv(2048)
            if not data:
                break
            conn.send(data)
            conn.close()