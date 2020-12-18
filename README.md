# CS305_Project_RDT

## 如何测试 2020.12.18 更新
1. `python network.py`
2. `python testserver.py`
3. `python testclient.py`

* 如果正常三次握手, client 会打印 `Connect OK`, server 会打印 `Accept OK`
* client 会提示你 input data，输入发送的内容
* 发送 `exit` 来关闭和 server 之间的连接，这时候 server 不会关闭，处于等待 `syn` 的状态，可以再开别的 client 连他
* 发送 `quit` 直接关掉 server
