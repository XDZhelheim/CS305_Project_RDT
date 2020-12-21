from USocket import UnreliableSocket
import threading
import time
import struct
import math

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
        self._rate= rate
        self._connect_addr=None
        DEBUG=debug

        # self.next_seq_num=None
        # self.next_ack_num=None

    '''
    connect+accept 是三次握手

    建立连接的过程:
        1. server 其实也是一个 socket，比如他运行在 1234 端口上，他的任务只是监听有没有人想连他
        2. client 向 server (port=1234) 发 syn
        3. server 收到 syn 了，他会新建一个叫 conn 的 socket，把他许配给这个 client，这个 conn 的端口号由系统自动分配
        4. conn 向刚才那个 client 发 synack (发的时候，系统底层会自动分配给 conn 一个端口)，从此以后，server 和这个 client 之间的所有收发全部由 conn 接手
        5. client 收到了 synack，他发现是从一个新 port 发过来的，于是他知道对面的 server 给他分配了一个 conn，他把 conn 的地址记下来，以后有什么数据就发往 conn 的地址
        6. client 向 conn 发 ack
        7. conn 收到 ack，三次握手完成

        所以整体结构是这样的，比如我有三个 client 要连 server
                  ----server------
                  /    |     \    \
                conn1 conn2 conn3 ...
                  |    |      |    |
                clie1 clie2 clie3 ...

        所以当 client 发完数据的时候，他 close() 只是关掉了和 conn 之间的连接，不会影响 server
        还有，server 可以单独 close()，同样不会影响各个已经存在的 conn，只是不能再接受新 client 了
    '''
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
                data, addr2=conn.recvfrom(4096) # recvfrom 是阻塞的，会一直在这等着直到收到消息
                segment=Segment.decode(data)
                if addr==addr2 and segment.is_ack_handshake():
                    conn.set_connect_addr(addr) # 连上了，以后就收 addr 发的消息

                    if DEBUG:
                        print("Accept OK")

                    return conn, addr
            #     else:
            #         continue
            # else:
            #     time.sleep(0.01)
            #     continue

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
            data, addr2=self.recvfrom(4096) # 这里收到的 synack 是 conn 发过来的，所以 addr2 一定 != addr
            segment=Segment.decode(data)

            # send ack
            if segment.is_synack_handshake():
                self.sendto(Segment.ack_handshake().encode(), addr2)
                self.set_connect_addr(addr2) # 连上了，以后就给 conn 发消息，addr2 就是 conn 的地址

                break
            # else:
            #     time.sleep(0.01)
            #     continue

        if DEBUG:
            print("Connect OK")

    '''
    选择重传 SR

    本来想按 TCP 那样每个包有个 seq=xxx, ack=xxx，但是 SR 好像没必要
    发送的时候先把 payload 分包，放在一个列表 all_segments[] 里，然后按 SR 的流程开始走
    这时候，segment 里面 seq_num 字段就是这个 segment 在 all_segments[] 里的下标，然后如果对面正常收到，对面发过来的包的 ack_num=这个包的seq_num，
    这样就可以很方便的用下标在发送窗口和接收窗口里面标记哪个包正常传输了
    现在已经没有什么 ack=seq+length 了，那个是 TCP 的玩法
    '''

    TIMEOUT_VALUE=0.01 # 0.01s 认为超时

    def send(self, data:bytes):
        """
        Send data to the socket. 
        The socket must be connected to a remote socket, i.e. self._send_to_addr must not be none.
        """
        assert self._connect_addr, "Connection not established yet. Use sendto instead."

        # TODO: 多线程: 三个线程：发包，收 ack，timers

        # 初始化发送窗口
        all_segments=[]
        send_window_size=8
        send_base=0
        next_seq_num=0

        # 分段
        num_of_segments=math.ceil(len(data)/Segment.MAX_PAYLOAD_SIZE) # num_of_segments 等于 len(all_segments)
        for i in range(num_of_segments):
            j=i*Segment.MAX_PAYLOAD_SIZE
            payload=data[j:j+Segment.MAX_PAYLOAD_SIZE] # 上限超长的话 python 会自动取到最后一位就停，不会报 IndexOutOfBound
            segment=Segment(seq_num=i, length=len(payload), payload=payload)
            all_segments.append(segment)
        # flags 数组用来标记包的状态: 0-还没发，1-已经收到 ack 可以不用管了，2-发了，还在等 ack
        flags=[0]*num_of_segments # 初始化为全 0
        timers=[Timer(i) for i in range(num_of_segments)] # 每个 segment 给一个 timer，timer 的 timer_id 等于他的下标

        # SR
        # self.setblocking(False) # 取消阻塞，否则发完第一个包会一直处于等待 ack 的状态
        while True:
            try:
                if next_seq_num<num_of_segments and flags[next_seq_num]==0 and next_seq_num<send_base+send_window_size:
                    self.sendto(all_segments[next_seq_num].encode(), self._connect_addr)
                    # timers[next_seq_num].start(self.TIMEOUT_VALUE) # 启动这个包的 timer，这里也要多线程，要不然不会往下执行
                    flags[next_seq_num]=2
                    next_seq_num+=1

                data, addr=self.recvfrom(4096) # BlockingIOError: [WinError 10035] 无法立即完成一个非阻止性套接字操作

                segment_recieved=Segment.decode(data)
                if segment_recieved.checksum!=Segment.calculate_checksum(segment_recieved):
                    continue # 如果收到的包是有错的，直接丢掉不管，反正对面已经正确接收了，大不了超时重发让对面再 ack 一次
                elif not segment_recieved.is_ack():
                    continue # 收到的不是 ack，丢掉不管
                elif flags[segment_recieved.ack_num]==1:
                    continue # 收到的 ack 是已经 ack 过的，丢掉不管
                elif flags[segment_recieved.ack_num]==0:
                    continue # 对面nt吗 ack 了一个老子还没发的包，丢掉不管，虽然我觉得这种情况不会发生，但还是写一下吧

                # 以下为正常接收 ack 之后
                flags[segment_recieved.ack_num]=1
                timers[segment_recieved.ack_num].closed=True # 关闭 timer
                while send_base<num_of_segments and flags[send_base]==1:
                    send_base+=1 # 窗口一直滑到第一个没收到 ack 的包的位置
                if send_base>=num_of_segments:
                    break # send_base 已经滑出 all_segments 了，证明所有包都正确传输完毕了，可以结束了

            except TimeoutException as e: # 捕获到有包超时
                # 这里 e.timer_id 对应的就是检测到超时的 timer 的 id，对应的就是 timers 里的下标，对应的就是 all_segments 里的下标
                resend_index=e.timer_id # 这个下标就是我要重传的包的下标
                self.sendto(all_segments[resend_index].encode(), self._connect_addr) # 重发这个包
                timers[resend_index].start(self.TIMEOUT_VALUE) # 重启这个包的 timer
        
        # 发个 fin 告诉你我发完了，你那边可以停止接收了
        start=time.time()
        while True:
            end=time.time()
            if end-start>0.1:
                break # 对面发回来的 ack 可能丢失，我一共就等 0.1s，反正数据都正确传好了，最多 0.1s 我就结束
            self.sendto(Segment.fin_handshake().encode(), self._connect_addr)
            data, addr=None, None
            data, addr=self.recvfrom(4096)
            if addr!=self._connect_addr:
                continue
            if data:
                break # 也别管收到的 ack 有没有错了，收到东西就证明对面收到我的 fin 了，停止发送
            
    def recv(self, bufsize) -> bytes:
        """
        Receive data from the socket. 
        The return value is a bytes object representing the data received. 
        The maximum amount of data to be received at once is specified by bufsize. 
        
        Note that ONLY data send by the peer should be accepted.
        In other words, if someone else sends data to you from another address,
        it MUST NOT affect the data returned by this function.
        """
        assert self._connect_addr, "Connection not established yet. Use recvfrom instead."

        # 初始化接收窗口
        recv_window_size=8
        recv_base=0

        # 不知道对面一共要发几个包，接收窗口只能设成最大长度了
        max_num_of_recieved_segments=math.floor(bufsize/Segment.MAX_SEGMENT_SIZE)
        recv_window=[None]*max_num_of_recieved_segments

        # 接收窗口收到了连续的包之后，就 extend 到 all_payloads，最后接收完了之后 return bytes(all_recieved_payloads)，这就是发送方发的所有有效载荷
        all_recieved_payloads=bytearray()

        while True:
            # 只收来自 _connect_addr 的消息  
            data, addr=self.recvfrom(bufsize)
            if addr!=self._connect_addr:
                continue

            segment_recieved=Segment.decode(data)

            if segment_recieved.checksum!=Segment.calculate_checksum(segment_recieved):
                continue # 收到坏包，直接丢弃，等对面超时重发
            elif segment_recieved.is_fin_handshake():
                self.sendto(Segment.ack_handshake().encode(), self._connect_addr) # 收到 fin，停止接收
                break
            elif segment_recieved.seq_num<recv_base:
                self.sendto(Segment(ack_num=segment_recieved.seq_num).encode(), self._connect_addr) # 收到了已经交付的包，回个 ack
                continue
            elif segment_recieved.seq_num>=recv_base+recv_window_size:
                continue # 超出接收窗口了，丢弃

            # 以下为正确接收
            self.sendto(Segment(ack_num=segment_recieved.seq_num).encode(), self._connect_addr)
            recv_window[segment_recieved.seq_num]=segment_recieved
            while recv_base<max_num_of_recieved_segments and recv_window[recv_base]:
                all_recieved_payloads.extend(recv_window[recv_base].payload)
                recv_base+=1

        return bytes(all_recieved_payloads)

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
        
    def set_connect_addr(self, addr):
        self._connect_addr=addr
    
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

    MAX_PAYLOAD_SIZE=1007 # 1007+17=1KB，最长 payload 长度，在 send() 里分段的时候用，拥塞的时候可以减小
    MAX_SEGMENT_SIZE=MAX_PAYLOAD_SIZE+17

    def __init__(self, syn:bool=False, fin:bool=False, ack:bool=False, seq_num:int=-1, ack_num:int=-1, length:int=0, checksum=None, payload:bytes=None):
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
        segment=Segment(syn, fin, ack, seq_num, ack_num, length, checksum, payload)

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
    # 编码的时候 -1 会编码成 4294967295
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

    def is_ack(self) -> bool:
        return not self.syn and not self.fin and not self.ack and self.seq_num==self.MAX_NUM and self.length==0

class Timer:
    def __init__(self, timer_id):
        self.timer_id=timer_id
        self.closed=False
    
    def start(self, timeout_value):
        start=time.time()
        while True:
            if (self.closed):
                break
            end=time.time()
            if (end-start>timeout_value):
                raise TimeoutException(self.timer_id)

class TimeoutException(Exception):
    def __init__(self, timer_id):
        super().__init__()
        self.timer_id=timer_id