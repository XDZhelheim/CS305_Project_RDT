from rdt import RDTSocket

if __name__ == "__main__":
    try:
        server=RDTSocket()
        server.bind(("127.0.0.1", 1234))
        while True:
            conn, addr=server.accept()
            while True:
                data=conn.recv(4096)
                if data:
                    print("recieved payload: "+data.decode())
                    if data==b"exit":
                        break
                    elif data==b"quit":
                        print("Server Closed")
                        exit()
                else:
                    break
            conn.close()
            print("Server Connection Lost")
    except KeyboardInterrupt:
        exit()
