import random
import threading
import time
from socket import inet_aton, inet_ntoa
from socketserver import ThreadingUDPServer

lock = threading.Lock()


def bytes_to_addr(bytes):
    return inet_ntoa(bytes[:4]), int.from_bytes(bytes[4:8], 'big')


def addr_to_bytes(addr):
    return inet_aton(addr[0]) + addr[1].to_bytes(4, 'big')


class Server(ThreadingUDPServer):
    def __init__(self, addr, rate=None, delay=None):
        super().__init__(addr, None)
        self.rate = rate
        self.buffer = 0
        self.delay = delay

    def verify_request(self, request, client_address):
        """
        request is a tuple (data, socket)
        data is the received bytes object
        socket is new socket created automatically to handle the request

        if this function returns False， the request will not be processed, i.e. is discarded.
        details: https://docs.python.org/3/library/socketserver.html
        """
        if self.buffer < 100000:  # some finite buffer size (in bytes)
            self.buffer += len(request[0])
            return True
        else:
            return False

    def finish_request(self, request, client_address):
        data, socket = request
        loss_rate = 0.1
        corrupt_rate = 0.00001

        with lock:
            if self.rate:
                time.sleep(len(data) / self.rate)
            self.buffer -= len(data)
            if random.random() < loss_rate:
                return

            select_num = 10
            if random.random() < corrupt_rate:
                data = bytearray(data)
                for _ in range(select_num):
                    index = random.randint(8, len(data) - 1)
                    temp = data.copy()
                    data = data[:index]
                    data.extend(random.randint(0, 255).to_bytes(1, 'big'))
                    data.extend(temp[index + 1:])
                data = bytes(data)

        """ 
        this part is not blocking and is executed by multiple threads in parallel
        you can add random delay here, this would change the order of arrival at the receiver side.
        
        for example:
        time.sleep(random.random())
        """

        to = bytes_to_addr(data[:8])
        print(client_address, to)  # observe tht traffic
        socket.sendto(addr_to_bytes(client_address) + data[8:], to)


server_address = ('127.0.0.1', 12345)

if __name__ == '__main__':
    with Server(server_address) as server:
        server.serve_forever()
