from rdt import RDTSocket

if __name__ == "__main__":
    try:
        server=RDTSocket()
        server.bind(("127.0.0.1", 1234))
        # 这个叫 server 的 socket 只用来监听连接请求，有一个 client 想连接，server 就给这个 clinet 分配一个专属的 conn，在 conn 上收发数据
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
