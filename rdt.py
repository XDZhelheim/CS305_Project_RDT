from USocket import UnreliableSocket
import threading
import time
import struct

class RDTSocket(UnreliableSocket):
    """
    The functions with which you are to build your RDT.
    -   recvfrom(bufsize)->bytes, addr
    -   sendto(bytes, address)
    -   bind(address)

    You can set the mode of the socket.
    -   settimeout(timeout)
    -   setblocking(flag)
    By default, a socket is created in the blocking mode. 
    https://docs.python.org/3/library/socket.html#socket-timeouts

    """
    def __init__(self, rate=None, debug=True):
        super().__init__(rate=rate)
        self._rate = rate
        self._send_to = None
        self._recv_from = None
        self.debug = debug

    # connect+accept 是三次握手

    def accept(self)->(RDTSocket, (str, int)):
        """
        Accept a connection. The socket must be bound to an address and listening for 
        connections. The return value is a pair (conn, address) where conn is a new 
        socket object usable to send and receive data on the connection, and address 
        is the address bound to the socket on the other end of the connection.

        This function should be blocking. 
        """
        conn, addr = RDTSocket(self._rate), None

        # recieve syn, send synack, recieve ack

        while True:
            data, addr=self.recvfrom(4096)


        return conn, addr

    def connect(self, address:(str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.
        """

        # send syn, recieve synack, send ack

    def recv(self, bufsize:int)->bytes:  # bufsize参数是bytes
        """
        Receive data from the socket. 
        The return value is a bytes object representing the data received. 
        The maximum amount of data to be received at once is specified by bufsize. 
        
        Note that ONLY data send by the peer should be accepted.
        In other words, if someone else sends data to you from another address,
        it MUST NOT affect the data returned by this function.
        """
        data = None
        assert self._recv_from, "Connection not established yet. Use recvfrom instead."
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################
        
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################
        return data

    def send(self, bytes:bytes):
        """
        Send data to the socket. 
        The socket must be connected to a remote socket, i.e. self._send_to must not be none.
        """
        assert self._send_to, "Connection not established yet. Use sendto instead."
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################
        raise NotImplementedError()
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################

    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        #############################################################################
        # TODO: YOUR CODE HERE                                                      #
        #############################################################################
        
        #############################################################################
        #                             END OF YOUR CODE                              #
        #############################################################################
        super().close()
        
    def set_send_to(self, send_to):
        self._send_to = send_to
    
    def set_recv_from(self, recv_from):
        self._recv_from = recv_from

class Segment:
    '''
    field       length          range               type
    --------------------------------------------------------------
    syn:        1 bit           0 ~ 1               bool
    fin:        1 bit           0 ~ 1               bool
    ack:        1 bit           0 ~ 1               bool
    seq_num:    4 byte=32 bit   0 ~ 4294967295      unsigned int
    ack_num:    4 byte=32 bit   0 ~ 4294967295      unsigned int
    length:     4 byte=32 bit   0 ~ 4294967295      unsigned int
    checksum:   2 byte=16 bit   0 ~ 65535           unsigned short
    payload:    0 ~ length byte -                   bytes
    '''

    MAX_NUM=4294967295 # 2^32-1 (32位无符号)
    # python3 的 int 没有范围限制, 不会 overflow 除非大到电脑内存满了

    def __init__(self, syn:bool, fin:bool, ack:bool, seq_num:int, ack_num:int, length:int, payload:bytes, checksum=None):
        self.syn=syn
        self.fin=fin
        self.ack=ack
        self.seq_num=seq_num%Segment.MAX_NUM
        self.ack_num=ack_num%Segment.MAX_NUM
        self.length=length
        self.checksum=checksum
        self.payload=payload

    def encode(self) -> bytes:
        '''
        ! 表示网络传输
        ? 表示 bool        (1 bit)
        I 表示 无符号int    (4 byte)
        H 表示 无符号short  (2 byte)
        '''
        data=bytearray(struct.pack("!???III", self.syn, self.fin, self.ack, self.seq_num, self.ack_num, self.length))

        self.checksum=Segment.calculate_checksum(data)
        data.extend(self.checksum)
        # 现在 header 封装完毕，header 长度为 17 byte (1+1+1+4+4+4+2)

        if self.payload:
            data.extend(self.payload) # 在后面加上数据

        return bytes(data)

    @staticmethod
    def decode(data:bytes) -> Segment:
        syn, fin, ack, seq_num, ack_num, length, checksum=struct.unpack("!???IIIH", data[:17])
        payload=data[17:]
        return Segment(syn, fin, ack, seq_num, ack_num, length, payload, checksum=checksum)
    
    @staticmethod
    def calculate_checksum(bytearr) -> bytes:
        pass

    @staticmethod
    def syn_handshake() -> Segment:
        return Segment(syn=1, fin=0, ack=0, seq_num=0, ack_num=0, length=0, payload=None)

    @staticmethod
    def synack_handshake() -> Segment:
        return Segment(syn=1, fin=0, ack=1, seq_num=0, ack_num=1, length=0, payload=None)
    
    @staticmethod
    def ack_handshake() -> Segment:
        return Segment(syn=0, fin=0, ack=1, seq_num=1, ack_num=1, length=0, payload=None)

    def is_syn_handshake(self) -> bool:
        return self.syn==1 and self.fin==0 and self.ack==0 and self.length==0
    
    def is_synack_handshake(self) -> bool:
        return self.syn==1 and self.fin==0 and self.ack==1 and self.length==0

    def is_ack_handshake(self) -> bool:
        return self.syn==0 and self.fin==0 and self.ack==1 and self.length==0
