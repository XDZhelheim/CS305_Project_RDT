"""
Reliable Data Transfer Socket
Author: 11812804 董正
        11811305 崔俞崧
        11813225 王宇辰
GitHub: https://github.com/XDZhelheim/CS305_Project_RDT
"""

from USocket import UnreliableSocket
import threading
import time
import struct
import math
from fractions import Fraction

DEBUG = True

# ---这些是 send() 多线程用的 global 变量----------------------------------
all_segments = []
send_window_size = 1
send_base = 0
next_seq_num = 0
temp = 0
num_of_segments = 0
flags = []
timers = []


# ----------------------------------------------------------------------

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
        self._connect_addr = None
        DEBUG = debug

    '''
    connect+accept 是握手

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

        现在不要第三次的 ack 了，TCP 的第三次 ack 就是带数据的，相当于收完 synack 就发数据了，目前版本是两次握手
    '''

    def accept(self) -> ('RDTSocket', (str, int)):
        """
        Accept a connection. The socket must be bound to an address and listening for 
        connections. The return value is a pair (conn, address) where conn is a new 
        socket object usable to send and receive data on the connection, and address 
        is the address bound to the socket on the other end of the connection.
        This function should be blocking. 
        receive syn, send synack, receive ack
        """

        conn, addr = RDTSocket(self._rate), None
        conn.bind(('127.0.0.1', 0))  # 0 表示随机分配端口

        data, addr = None, None
        flag = False  # 要从第一次收到包开始计时，用来标记是否收到第一个包。如果一上来就开始计时那运行到 end_time 那一行之后肯定就超时退出了
        while True:
            # 发回去的 synack 可能丢包，这时候 client 会继续发 syn 过来，所以需要一段时间继续监听

            if data and addr:
                self.setblocking(False)
                if flag:
                    start_time = time.time()  # 每次收到 syn 就会重新计时，所以我是收到 syn 之后，如果 1s 内没有再次收到新 syn 就 break
                    flag = False
                end_time = time.time()
                if end_time - start_time > 1:  # 等待这个时间之后就结束
                    self.setblocking(True)
                    break

            # receive syn
            try:
                data, addr = self.recvfrom(4096)
            except BlockingIOError:
                continue

            if not flag:
                flag = True

            if not Segment.check_checksum(data):
                if DEBUG:
                    print("Received corrupted data")
                continue
            segment = Segment.decode(data)

            # then send synack
            if segment.is_syn_handshake():
                conn.sendto(Segment.synack_handshake().encode(), addr)
                conn.set_connect_addr(addr)  # 连上了，以后就收 addr 发的消息

        if DEBUG:
            print("Accept OK")

        return conn, addr

    flag = False  # 这个 flag 只在 connect() 和 recv_synack_handshake() 和最后的 fin 里用
    def connect(self, addr: (str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.
        send syn, receive synack, send ack
        """
        self.flag = False
        self.bind(('127.0.0.1', 0))

        threading.Thread(target=self.recv_synack_handshake).start()

        while True:
            # send syn
            self.sendto(Segment.syn_handshake().encode(), addr)

            if self.flag:
                break

            time.sleep(0.1)

        if DEBUG:
            print("Connect OK")

    def recv_synack_handshake(self):
        # receive synack
        while True:
            data, addr2 = self.recvfrom(4096)  # 这里收到的 synack 是 conn 发过来的，所以 addr2 一定 != addr
            if not Segment.check_checksum(data):
                if DEBUG:
                    print("Received corrupted data")
                continue
            segment = Segment.decode(data)
            if segment.is_synack_handshake():
                self.set_connect_addr(addr2)
                self.flag = True
                break

    '''
    选择重传 SR

    本来想按 TCP 那样每个包有个 seq=xxx, ack=xxx，但是 SR 好像没必要
    发送的时候先把 payload 分包，放在一个列表 all_segments[] 里，然后按 SR 的流程开始走
    这时候，segment 里面 seq_num 字段就是这个 segment 在 all_segments[] 里的下标，然后如果对面正常收到，对面发过来的包的 ack_num=这个包的seq_num，
    这样就可以很方便的用下标在发送窗口和接收窗口里面标记哪个包正常传输了
    现在已经没有什么 ack=seq+length 了，那个是 TCP 的玩法
    '''

    TIMEOUT_VALUE = 0.1  # 0.1s 认为超时
    SSTHRESH = 8  # 慢启动阈值
    threadLock = threading.Lock()

    def send(self, data: bytes):
        """
        Send data to the socket. 
        The socket must be connected to a remote socket, i.e. self._send_to_addr must not be none.
        """
        assert self._connect_addr, "Connection not established yet. Use sendto instead."

        global all_segments, send_window_size, send_base, next_seq_num, temp, num_of_segments, flags, timers

        # 初始化发送窗口
        all_segments = []
        send_window_size = 1
        send_base = 0
        next_seq_num = 0
        temp = 0  # 这个变量只在拥塞控制的时候用

        # 分段
        num_of_segments = math.ceil(len(data) / Segment.MAX_PAYLOAD_SIZE)  # num_of_segments 等于 len(all_segments)
        for i in range(num_of_segments):
            j = i * Segment.MAX_PAYLOAD_SIZE
            payload = data[j:j + Segment.MAX_PAYLOAD_SIZE]  # 上限超长的话 python 会自动取到最后一位就停，不会报 IndexOutOfBound
            segment = Segment(seq_num=i, length=len(payload), payload=payload)
            all_segments.append(segment)
        # flags 数组用来标记包的状态: 0-还没发，1-已经收到 ack 可以不用管了，2-发了，还在等 ack
        flags = [0] * num_of_segments  # 初始化为全 0
        timers = [Timer() for i in range(num_of_segments)]  # 每个 segment 给一个 timer

        threading.Thread(target=self.recv_ack).start() # 开一个线程收 ack

        # SR
        while True:
            # try:
            if next_seq_num < num_of_segments and flags[next_seq_num] == 0 and next_seq_num < send_base + send_window_size:
                self.sendto(all_segments[next_seq_num].encode(), self._connect_addr)
                threading.Thread(target=self.start_timer).start() # 发包之后启动这个包的 timer
                flags[next_seq_num] = 2
                next_seq_num += 1

            if send_base >= num_of_segments:
                break

        self.send_fin_handshake() # 发 fin，结束发送

    def recv_ack(self):
        global all_segments, send_window_size, send_base, next_seq_num, temp, num_of_segments, flags, timers

        while True:
            data, addr = self.recvfrom(4096)

            if not Segment.check_checksum(data):  # 如果收到的包是有错的，直接丢掉不管，反正对面已经正确接收了，大不了超时重发让对面再 ack 一次
                if DEBUG:
                    print("Received corrupted data")
                continue

            segment_received = Segment.decode(data)
            if not segment_received.is_ack():
                continue  # 收到的不是 ack，丢掉不管
            elif flags[segment_received.ack_num] == 1:
                continue  # 收到的 ack 是已经 ack 过的，丢掉不管
            elif flags[segment_received.ack_num] == 0:
                continue  # 对面nt吗 ack 了一个老子还没发的包，丢掉不管，虽然我觉得这种情况不会发生，但还是写一下吧

            # 以下为正常接收 ack 之后
            flags[segment_received.ack_num] = 1
            timers[segment_received.ack_num].closed = True  # 关闭 timer

            # 发送窗口变大: 慢启动+拥塞避免
            if send_window_size < self.SSTHRESH:
                self.threadLock.acquire()
                send_window_size += 1  # 指数增长阶段: 每 RTT 窗口大小*2，所以每次收到 1 个 ack，窗口大小+1
                self.threadLock.release()
            else:
                temp += Fraction(1, send_window_size)
                if temp == 1:
                    send_window_size += 1
                    temp = 0

            while send_base < num_of_segments and flags[send_base] == 1:
                send_base += 1  # 窗口一直滑到第一个没收到 ack 的包的位置
            if send_base >= num_of_segments:
                break  # send_base 已经滑出 all_segments 了，证明所有包都正确传输完毕了，可以结束了

    def start_timer(self):
        global all_segments, send_window_size, send_base, next_seq_num, temp, num_of_segments, flags, timers

        if next_seq_num >= num_of_segments:
            return

        timer_index = next_seq_num # timer 的下标

        while True:
            if timers[timer_index].closed:
                if DEBUG:
                    print("Timer " + str(timer_index) + " closed")
                break
            try:
                timers[timer_index].start(self.TIMEOUT_VALUE)
                if DEBUG:
                    print("Timer " + str(timer_index) + " started")
            except TimeoutException:
                resend_index = timer_index  # 这个下标就是我要重传的包的下标
                if DEBUG:
                    print("Segment " + str(resend_index) + " timeout")
                self.sendto(all_segments[resend_index].encode(), self._connect_addr)  # 重发这个包
                # 拥塞控制，发送窗口大小=1，重设阈值
                self.SSTHRESH = send_window_size / 2
                self.threadLock.acquire()
                send_window_size = 1
                self.threadLock.release()

    def send_fin_handshake(self):
        self.flag = False
        threading.Thread(target=self.recv_ack_handshake_after_send_fin_handshake).start()

        while True:
            # send fin
            self.sendto(Segment.fin_handshake().encode(), self._connect_addr)

            if self.flag:
                break

            time.sleep(0.1)

        if DEBUG:
            print("Send OK")

    def recv_ack_handshake_after_send_fin_handshake(self):
        # receive ack
        while True:
            data, addr = self.recvfrom(4096)
            if addr != self._connect_addr:
                if DEBUG:
                    print("A stranger is sending data to me")
                continue
            if not Segment.check_checksum(data):
                if DEBUG:
                    print("Received corrupted data")
                continue
            segment = Segment.decode(data)
            if segment.is_ack_handshake():
                self.flag = True
                break

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
        recv_window_size = 8  # 这个 size 好像没啥用
        recv_base = 0

        # 不知道对面一共要发几个包，接收窗口只能设成最大长度了
        max_num_of_received_segments = math.ceil(bufsize / Segment.MAX_PAYLOAD_SIZE)  # ceil 还是 floor?
        recv_window = [None] * max_num_of_received_segments

        # 接收窗口收到了连续的包之后，就 extend 到 all_payloads，最后接收完了之后 return bytes(all_received_payloads)，这就是发送方发的所有有效载荷
        all_received_payloads = bytearray()

        while True:
            # 只收来自 _connect_addr 的消息  
            data, addr = self.recvfrom(bufsize)
            if addr != self._connect_addr:
                if DEBUG:
                    print("A stranger is sending data to me")
                continue

            if not Segment.check_checksum(data):  # 收到坏包，直接丢弃，等对面超时重发
                if DEBUG:
                    print("Received corrupted data")
                continue

            segment_received = Segment.decode(data)

            if segment_received.is_fin_handshake():
                self.send_ack_handshake()  # 收到 fin，回 ack, 一段时间后停止接收
                break
            elif segment_received.seq_num < recv_base:
                self.sendto(Segment(ack_num=segment_received.seq_num).encode(), self._connect_addr)  # 收到了已经交付的包，回个 ack
                continue
            elif segment_received.seq_num >= recv_base + recv_window_size:
                continue  # 超出接收窗口了，丢弃

            # 以下为正确接收
            self.sendto(Segment(ack_num=segment_received.seq_num).encode(), self._connect_addr)

            if segment_received.seq_num >= len(recv_window) - 1:
                temp = [None] * math.ceil(bufsize / Segment.MAX_PAYLOAD_SIZE)
                recv_window += temp
                max_num_of_received_segments += math.ceil(bufsize / Segment.MAX_PAYLOAD_SIZE)

            recv_window[segment_received.seq_num] = segment_received
            while recv_base < max_num_of_received_segments and recv_window[recv_base]: # 交付数据，滑动窗口
                all_received_payloads.extend(recv_window[recv_base].payload)
                recv_base += 1

        return bytes(all_received_payloads)

    def send_ack_handshake(self):
        self.setblocking(False)
        flag = True
        while True:
            if flag:
                start_time = time.time()
                flag = False
            end_time = time.time()
            if end_time - start_time > 1:  # 等待这个时间之后就结束
                self.setblocking(True)
                break

            # receive fin
            try:
                data, addr = self.recvfrom(4096)
            except BlockingIOError:
                continue

            if not flag:
                flag = True

            if addr != self._connect_addr:
                if DEBUG:
                    print("A stranger is sending data to me")
                continue

            if not Segment.check_checksum(data):
                if DEBUG:
                    print("Received corrupted data")
                continue

            segment = Segment.decode(data)

            # then send ack
            if segment.is_fin_handshake():
                self.sendto(Segment.ack_handshake().encode(), self._connect_addr)

        if DEBUG:
            print("Receive OK")

    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        super().close()

    def set_connect_addr(self, addr):
        self._connect_addr = addr


class Segment:
    """
    field       length          range               type
    --------------------------------------------------------------
    checksum   2 byte=16 bit   0 ~ 65535           unsigned short
    syn        1 byte          0 ~ 1               bool
    fin        1 byte          0 ~ 1               bool
    ack        1 byte          0 ~ 1               bool
    seq_num    4 byte=32 bit   0 ~ 4294967295      unsigned int
    ack_num    4 byte=32 bit   0 ~ 4294967295      unsigned int
    length     4 byte=32 bit   0 ~ 4294967295      unsigned int
    payload    0 ~ length byte -                   bytes
    """

    MAX_NUM = 4294967295  # 2^32-1 (32位无符号)
    # python3 的 int 没有范围限制, 不会 overflow 除非大到电脑内存满了

    MAX_PAYLOAD_SIZE = 2000  # 最长 payload 长度，在 send() 里分段的时候用，拥塞的时候可以减小
    MAX_SEGMENT_SIZE = MAX_PAYLOAD_SIZE + 17

    def __init__(self, syn: bool = False, fin: bool = False, ack: bool = False, seq_num: int = -1, ack_num: int = -1,
                 length: int = 0, checksum=None, payload: bytes = None):
        self.syn = syn
        self.fin = fin
        self.ack = ack
        self.seq_num = seq_num % (Segment.MAX_NUM + 1)
        self.ack_num = ack_num % (Segment.MAX_NUM + 1)
        self.length = length
        self.checksum = checksum
        self.payload = payload

    def __str__(self):
        return ("----------------------------------------------\n" +
                "syn=" + str(self.syn) + ", " + "fin=" + str(self.fin) + ", " + "ack=" + str(self.ack) + "\n" +
                "seq_num=" + str(self.seq_num) + ", " + "ack_num=" + str(self.ack_num) + "\n" +
                "length=" + str(self.length) + "\n" + "checksum=" + str(self.checksum) + "\n" +
                "payload=" + (self.payload.decode() if self.payload else "None") + "\n" +
                "---------------------------------------------------------------\n")

    def encode(self) -> bytes:
        """
        将报文编码成字节流

        ! 表示网络传输
        ? 表示 bool        (1 byte)
        I 表示 无符号int    (4 byte)
        H 表示 无符号short  (2 byte)
        B 表示 无符号char   (1 byte)
        """
        self.checksum = Segment.calculate_checksum(self)

        # checksum 要放第一位，否则检查 checksum 的时候会错开 1 位，因为 header 的总长度是奇数
        data = bytearray(
            struct.pack("!H???III", self.checksum, self.syn, self.fin, self.ack, self.seq_num, self.ack_num,
                        self.length))
        # 现在 header 封装完毕，header 长度为 17 byte (2+1+1+1+4+4+4)
        # XXX: 三个 bit 其实用一个 byte 表示就够了, header 长度减小到 15 byte

        if self.payload:
            data.extend(self.payload)  # 在后面加上数据

        if DEBUG:
            print("--- send segment " + str(self))

        return bytes(data)

    @staticmethod
    def decode(data: bytes) -> "Segment":
        """
        将收到的字节流解码为报文
        """
        checksum, syn, fin, ack, seq_num, ack_num, length = struct.unpack("!H???III", data[:17])
        # 注意 python 没有 short 类型, checksum 是个 int
        payload = data[17:]  # 注意如果 data 里没有数据的话, 这里 payload=b'' 空字符串
        segment = Segment(syn, fin, ack, seq_num, ack_num, length, checksum, payload)

        if DEBUG:
            print("--- recv segment " + str(segment))

        return segment

    @staticmethod
    def calculate_checksum(segment: "Segment") -> int:
        """
        用除了 checksum 之外的所有字段算 checksum
        """
        temp = bytearray(struct.pack("!???III", segment.syn, segment.fin, segment.ack, segment.seq_num, segment.ack_num,
                                     segment.length))
        if segment.payload:
            temp.extend(segment.payload)
        i = iter(temp)
        bytes_sum = sum((a << 8) + b for a, b in zip(i, i))  # for a, b: (s[0], s[1]), (s[2], s[3]), ...
        if len(temp) % 2 == 1:  # pad zeros to form a 16-bit word for checksum
            bytes_sum += temp[-1] << 8
        # add the overflow 1 at the end (adding twice is sufficient)
        bytes_sum = (bytes_sum & 0xFFFF) + (bytes_sum >> 16)
        bytes_sum = (bytes_sum & 0xFFFF) + (bytes_sum >> 16)
        return ~bytes_sum & 0xFFFF

    @staticmethod
    def check_checksum(data: bytes) -> bool:
        i = iter(data)
        bytes_sum = sum((a << 8) + b for a, b in zip(i, i))
        if len(data) % 2 == 1:
            bytes_sum += data[-1] << 8
        bytes_sum = (bytes_sum & 0xFFFF) + (bytes_sum >> 16)
        bytes_sum = (bytes_sum & 0xFFFF) + (bytes_sum >> 16)
        return bytes_sum & 0xFFFF == 0xFFFF

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
        return not self.syn and not self.fin and not self.ack and self.seq_num == self.MAX_NUM and self.length == 0


class Timer:
    def __init__(self):
        self.closed = False

    def start(self, timeout_value):
        start = time.time()
        while True:
            if self.closed:
                break
            end = time.time()
            if end - start > timeout_value:
                raise TimeoutException()


class TimeoutException(Exception):
    def __init__(self):
        super().__init__()
