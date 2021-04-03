# CS305_Project_RDT

## 如何测试 2020.12.26 更新

1. `python network.py`
2. `python testserver.py`
3. `python testclient.py`

* 如果正常三次握手, client 会打印 `Connect OK`, server 会打印 `Accept OK`
* client 会提示你 input data，输入发送的内容
* 发送 `alice` 来发送 `alice.txt`
* 发送 `exit` 来关闭和 server 之间的连接，这时候 server 不会关闭，处于等待 `syn` 的状态，可以再开别的 client 连他
* 发送 `quit` 直接关掉 server
  
---

## 建立连接 (握手) 的过程:

1. server 其实也是一个 socket，比如他运行在 1234 端口上，他的任务只是监听有没有人想连他
2. client 向 server (port=1234) 发 syn
3. server 收到 syn 了，他会新建一个叫 conn 的 socket，把他许配给这个 client，这个 conn 的端口号由系统自动分配
4. conn 向刚才那个 client 发 synack (发的时候，系统底层会自动分配给 conn 一个端口)，从此以后，server 和这个 client 之间的所有收发全部由 conn 接手
   注: 现在改成 conn 手动 bind 了
5. client 收到了 synack，他发现是从一个新 port 发过来的，于是他知道对面的 server 给他分配了一个 conn，他把 conn 的地址记下来，以后有什么数据就发往 conn 的地址
6. client 向 conn 发 ack
7. conn 收到 ack，三次握手完成

所以整体结构是这样的，比如我有三个 client 要连 server

```bash
        ----server------
        /    |     \    \
      conn1 conn2 conn3 ...
        |    |      |    |
      clie1 clie2 clie3 ...
```

所以当 client 发完数据的时候，他 close() 只是关掉了和 conn 之间的连接，不会影响 server
还有，server 可以单独 close()，同样不会影响各个已经存在的 conn，只是不能再接受新 client 了

现在不要第三次的 ack 了，TCP 的第三次 ack 就是带数据的，相当于收完 synack 就发数据了，目前版本是两次握手

---

## 选择重传 SR

本来想按 TCP 那样每个包有个 `seq=xxx, ack=xxx`，但是 SR 好像没必要
发送的时候先把 payload 分包，放在一个列表 `all_segments[]` 里，然后按 SR 的流程开始走
这时候，segment 里面 `seq_num` 字段就是这个 segment 在 `all_segments[]` 里的下标，然后如果对面正常收到，对面发过来的包的 `ack_num=这个包的seq_num`，
这样就可以很方便的用下标在发送窗口和接收窗口里面标记哪个包正常传输了
现在已经没有什么 `ack=seq+length` 了，那个是 TCP 的玩法

---

## 计时器 Timer

专门用来计时的一个类，实际上是倒计时，如果 timeout 会引起 `TimeoutException`。

对于 SR, 每个包需要分配一个 timer，所以每个 timer 需要一个线程。哪个线程超时就重发哪个对应的包，这个对应关系用数组下标实现一一对应。

---

## 拥塞控制

* 正常收到 ack
  * `send_window_size<SSTHRES`: 慢启动阶段
    每 RTT `send_window_size*=2`
    反映到代码里是每次收到 `ack` 后 `send_window_size+=1`，这是因为发送的时候是流水线发送的，一次发好几个，具体对应关系可以看课件
  * `send_window_size>=SSTHRES`: 拥塞避免阶段
    每 RTT `send_window_size+=1`
    反映到代码里是每次收到 `ack` 后 $send\ window\ size+=\frac {1}{\lfloor send\ window\ size\rfloor}$
  * timeout 的阈值 `-=0.1`
* 有 timer 超时
  * 重发这个包
  * `SSTHRES=send_window_size/2`
  * `send_window_size=1`
  * timeout 的阈值 `+=0.2`

---

目前还有可能发生的问题

server 在 accept 最后等的 1s 有可能不够，如果网络十分非常极其拥塞
以及 `fin ack` 也是，有可能会造成 client 无法退出发送状态

## 我写的都是什么垃圾玩意抓紧删了吧
