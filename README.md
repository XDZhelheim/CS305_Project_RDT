# CS305_Project_RDT

## 如何测试 2020.12.18 更新

1. `python network.py`
2. `python testserver.py`
3. `python testclient.py`

* 如果正常三次握手, client 会打印 `Connect OK`, server 会打印 `Accept OK`
* client 会提示你 input data，输入发送的内容
* 发送 `exit` 来关闭和 server 之间的连接，这时候 server 不会关闭，处于等待 `syn` 的状态，可以再开别的 client 连他
* 发送 `quit` 直接关掉 server
  
---

## 建立连接 (三次握手) 的过程:

1. server 其实也是一个 socket，比如他运行在 1234 端口上，他的任务只是监听有没有人想连他
2. client 向 server (port=1234) 发 syn
3. server 收到 syn 了，他会新建一个叫 conn 的 socket，把他许配给这个 client，这个 conn 的端口号由系统自动分配
4. conn 向刚才那个 client 发 synack (发的时候，系统底层会自动分配给 conn 一个端口)，从此以后，server 和这个 client 之间的所有收发全部由 conn 接手
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