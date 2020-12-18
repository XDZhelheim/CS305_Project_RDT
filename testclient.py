from rdt import RDTSocket

if __name__ == "__main__":
    try:
        client=RDTSocket()
        client.connect(("127.0.0.1", 1234))
        while True:
            print("input data:")
            data=input()
            client.send(data.encode())
            if data=="exit" or data=="quit":
                break
        client.close()
        print("Client Closed")
    except KeyboardInterrupt:
        exit()