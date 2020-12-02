from udp import UDPsocket

class socket(UDPsocket):
    def __init__(self):
        super(socket, self).__init__()

    # send syn; receive syn, ack; send ack
    def connect(self):
        pass

    # receive syn; send syn, ack; receive ack
    def accept(self):
        pass

    # send fin; recieve ack; recieve fin; send ack
    def close(self):
        pass

    def recv(self):
        pass
    
    def send(self):
        pass
