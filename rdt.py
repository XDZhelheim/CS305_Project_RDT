from USocket import UnreliableSocket
import threading
import time
import struct

DEBUG=True

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
        self._send_to_addr = None
        self._recv_from_addr = None
        DEBUG=debug

        self.next_seq_num=None
        self.next_ack_num=None

    # connect+accept 是三次握手
    def accept(self)->('RDTSocket', (str, int)):
        """
        Accept a connection. The socket must be bound to an address and listening for 
        connections. The return value is a pair (conn, address) where conn is a new 
        socket object usable to send and receive data on the connection, and address 
        is the address bound to the socket on the other end of the connection.

        This function should be blocking. 

        recieve syn, send synack, recieve ack
        """

        conn, addr=RDTSocket(self._rate), None

        while True:
            # recieve syn
            data, addr=self.recvfrom(4096)
            segment=Segment.decode(data)

            # then send synack
            if segment.is_syn_handshake():
                conn.sendto(Segment.synack_handshake().encode(), addr)

                # recieve ack
                data, addr2=conn.recvfrom(4096)
                segment=Segment.decode(data)
                if addr==addr2 and segment.is_ack_handshake():
                    conn.set_recv_from_addr(addr) # 连上了，以后就收 addr 发的消息

                    conn.next_seq_num=0
                    conn.next_ack_num=0

                    if DEBUG:
                        print("Accept OK")

                    return conn, addr
                else:
                    continue
            else:
                time.sleep(0.01)
                continue

        return conn, addr

    def connect(self, addr:(str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.

        send syn, recieve synack, send ack
        """

        while True:
            # send syn
            self.sendto(Segment.syn_handshake().encode(), addr)

            # recieve synack
            data, addr2=self.recvfrom(4096)
            segment=Segment.decode(data)

            # send ack
            if segment.is_synack_handshake():
                self.sendto(Segment.ack_handshake().encode(), addr2)
                self.set_send_to_addr(addr2) # 连上了，以后就给 addr 发消息

                self.next_seq_num=0
                self.next_ack_num=0

                break
            else:
                time.sleep(0.01) # 否则会在收到 synack 之前疯狂发 syn 过去
                continue

        if DEBUG:
            print("Connect OK")

    def recv(self, bufsize) -> bytes:
        """
        Receive data from the socket. 
        The return value is a bytes object representing the data received. 
        The maximum amount of data to be received at once is specified by bufsize. 
        
        Note that ONLY data send by the peer should be accepted.
        In other words, if someone else sends data to you from another address,
        it MUST NOT affect the data returned by this function.
        """
        assert self._recv_from_addr, "Connection not established yet. Use recvfrom instead."

        # TODO: 接收窗口
        '''
        下一步想法:
        while True:
            如果不是对方发的: continue
            收消息
            如果是 fin: 回复 ack_handshake 然后 break
            检查有没有问题，有问题发最后的 ack_num 回去
            没问题，在接收窗口标记这个包正确收到了
        拼成整体，return
        '''

        # 只收来自 _recv_from_addr 的消息
        while True:
            data, addr=self.recvfrom(bufsize)
            if addr==self._recv_from_addr:
                break

        segment_recieved=Segment.decode(data)

        # checksum 不对，说明包有错，发最后一个 ack_num 提示对方重传
        if Segment.calculate_checksum(segment_recieved)!=segment_recieved.checksum:
            self.sendto(Segment(seq_num=self.next_seq_num, ack_num=self.next_ack_num).encode(), self._send_to_addr)
            return None

        # seq_num 和 next_ack_num 不一样，说明收到的不是现在想要的包
        if segment_recieved.seq_num!=self.next_ack_num:
            self.sendto(Segment(seq_num=self.next_seq_num, ack_num=self.next_ack_num).encode(), self._send_to_addr)
            return None

        # 正确接收，更新 next_ack_num
        self.next_ack_num=segment_recieved.seq_num+segment_recieved.length
        # TODO: 把 ack_num 之前的包标记为已经正确传输完毕

        # # 是 fin, 回 ack, 然后发 fin, 等 ack
        # if segment_recieved.is_fin_handshake():
        #     self.sendto(Segment.ack_handshake(seq_num=self.next_seq_num, ack_num=self.next_ack_num), self._send_to_addr)
        #     self.sendto(Segment.fin_handshake(seq_num=self.next_seq_num, ack_num=self.next_ack_num), self._send_to_addr)
        #     while True:
        #         data, addr=self.recvfrom(4096)
        #         if addr==self._recv_from_addr:
        #             segment=Segment.decode(data)
        #             if segment.is_ack_handshake():
        #                 self._recv_from_addr=None
        #                 return None

        return segment_recieved.payload

    def send(self, payload:bytes):
        """
        Send data to the socket. 
        The socket must be connected to a remote socket, i.e. self._send_to_addr must not be none.
        """
        assert self._send_to_addr, "Connection not established yet. Use sendto instead."

        # TODO: 分段发送，计时器，发送窗口

        segment_to_send=Segment(seq_num=self.next_seq_num, ack_num=self.next_ack_num, length=len(payload), payload=payload)

        self.sendto(segment_to_send.encode(), self._send_to_addr)

        # 发送之后更新 next_seq_num
        self.next_seq_num=segment_to_send.seq_num+segment_to_send.length

    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        # # 四次握手 (发送端行为)
        # self.sendto(Segment.fin_handshake().encode(), self._send_to_addr)
        # while True:
        #     data, addr=self.recvfrom(4096)
        #     if addr==self._send_to_addr:
        #         segment=Segment.decode(data)
        #         if segment.is_ack_handshake():
        #             break
        # while True:
        #     data, addr=self.recvfrom(4096)
        #     if addr==self._send_to_addr:
        #         segment=Segment.decode(data)
        #         if segment.is_fin_handshake():
        #             self.sendto(Segment.ack_handshake().encode(), self._send_to_addr)
        #             break
                    
        super().close()
        
    def set_send_to_addr(self, _send_to_addr):
        self._send_to_addr = _send_to_addr
    
    def set_recv_from_addr(self, _recv_from_addr):
        self._recv_from_addr = _recv_from_addr

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

    def __init__(self, seq_num:int, ack_num:int, length:int=0, payload:bytes=None, checksum=None, syn:bool=False, fin:bool=False, ack:bool=False):
        self.syn=syn
        self.fin=fin
        self.ack=ack
        self.seq_num=seq_num%(Segment.MAX_NUM+1)
        self.ack_num=ack_num%(Segment.MAX_NUM+1)
        self.length=length
        self.checksum=checksum
        self.payload=payload

    def __str__(self):
        return ("----------------------------------------------\n"+
               "syn="+str(self.syn)+", "+"fin="+str(self.fin)+", "+"ack="+str(self.ack)+"\n"+
               "seq_num="+str(self.seq_num)+", "+"ack_num="+str(self.ack_num)+"\n"+
               "length="+str(self.length)+"\n"+"checksum="+str(self.checksum)+"\n"+
               "payload="+(self.payload.decode() if self.payload else "None")+"\n"+
               "---------------------------------------------------------------\n")

    def encode(self) -> bytes:
        '''
        将报文编码成字节流

        ! 表示网络传输
        ? 表示 bool        (1 byte)
        I 表示 无符号int    (4 byte)
        H 表示 无符号short  (2 byte)
        B 表示 无符号char   (1 byte)
        '''
        self.checksum=Segment.calculate_checksum(self)

        data=bytearray(struct.pack("!???IIIH", self.syn, self.fin, self.ack, self.seq_num, self.ack_num, self.length, self.checksum))
        # 现在 header 封装完毕，header 长度为 17 byte (1+1+1+4+4+4+2)
        # XXX: 前三个 bit 其实用一个 byte 表示就够了, header 长度减小到 15 byte

        if self.payload:
            data.extend(self.payload) # 在后面加上数据

        if DEBUG:
            print("--- send segment "+str(self))

        return bytes(data)

    @staticmethod
    def decode(data:bytes) -> "Segment":
        '''
        将收到的字节流解码为报文
        '''
        syn, fin, ack, seq_num, ack_num, length, checksum=struct.unpack("!???IIIH", data[:17])
        # 注意 python 没有 short 类型, checksum 是个 int
        payload=data[17:] # 注意如果 data 里没有数据的话, 这里 payload=b'' 空字符串
        segment=Segment(seq_num, ack_num, length, payload, checksum, syn, fin, ack)

        if DEBUG:
            print("--- recv segment "+str(segment))

        return segment
    
    @staticmethod
    def calculate_checksum(segment:"Segment") -> int:
        '''
        用除了 checksum 之外的所有字段算 checksum
        '''
        temp=bytearray(struct.pack("!???III", segment.syn, segment.fin, segment.ack, segment.seq_num, segment.ack_num, segment.length))
        if segment.payload:
            temp.extend(segment.payload)
        i=iter(temp)
        bytes_sum=sum(((a<<8)+b for a, b in zip(i, i)))  # for a, b: (s[0], s[1]), (s[2], s[3]), ...
        if len(temp)%2==1:  # pad zeros to form a 16-bit word for checksum
            bytes_sum+=temp[-1] << 8
        # add the overflow 1 at the end (adding twice is sufficient)
        bytes_sum=(bytes_sum & 0xFFFF)+(bytes_sum>>16)
        bytes_sum=(bytes_sum & 0xFFFF)+(bytes_sum>>16)
        return ~bytes_sum & 0xFFFF

    # seq_num=ack_num=-1 表示这是握手报文段
    @staticmethod
    def syn_handshake(seq_num=-1, ack_num=-1):
        return Segment(syn=True, fin=False, ack=False, seq_num=seq_num, ack_num=ack_num)

    @staticmethod
    def synack_handshake(seq_num=-1, ack_num=-1):
        return Segment(syn=True, fin=False, ack=True, seq_num=seq_num, ack_num=ack_num)
    
    @staticmethod
    def ack_handshake(seq_num=-1, ack_num=-1):
        return Segment(syn=False, fin=False, ack=True, seq_num=seq_num, ack_num=ack_num)

    @staticmethod
    def fin_handshake(seq_num=-1, ack_num=-1):
        return Segment(syn=False, fin=True, ack=False, seq_num=seq_num, ack_num=ack_num)

    def is_syn_handshake(self) -> bool:
        return self.syn and not self.fin and not self.ack
    
    def is_synack_handshake(self) -> bool:
        return self.syn and not self.fin and self.ack

    def is_ack_handshake(self) -> bool:
        return not self.syn and not self.fin and self.ack

    def is_fin_handshake(self) -> bool:
        return not self.syn and self.fin and not self.ack
