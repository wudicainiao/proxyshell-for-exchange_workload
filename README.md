# proxyshell-for-exchange_workload
based on https://github.com/dmaasland/proxyshell-poc

该工具用于处理exchange负载均衡目标ps执行不稳定的情况

需一个存在邮箱，脚本未加入通杀获取ps端点的代码，所以默认会强制修改sid为500

使用：

python38 -m pip install colorama

python38 proxyshell.py -u https://xxxx.xx/ -e xxxx@xxxx.xx
