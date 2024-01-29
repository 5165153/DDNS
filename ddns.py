#replace here要替换成自己的参数！！！
#replace here要替换成自己的参数！！！
#replace here要替换成自己的参数！！！
#重要的事情说三遍！！！

#安装以下sdk
#pip install aliyun-python-sdk-core
#pip install aliyun-python-sdk-alidns

import telnetlib
import re
from time import sleep
import logging
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from datetime import datetime

#防火墙，路由器
HUAWEI_FIREWALL_IP = 'replace here'  #防火墙ip
TELNET_PORT = 23  #telnet端口
USERNAME = 'replace here'  #用户名
PASSWORD = 'replace here'  #密码
INTERFACE = 'replace here'  #拨号接口(华为设备是用dialer虚拟拨号接口不是物理接口！！！)
Time = 30 #ip查询间隔时间

# 阿里云 API 认证信息
ACCESS_KEY = 'replace here'
AccessKey_Secret = 'replace here'
DOMAIN = 'replace here'
RECORD_ID = 'replace here'
Record_name='replace here'

#Telnet登录
def get_pppoe_ip():
    try:
        #建立Telnet连接
        telnet = telnetlib.Telnet(HUAWEI_FIREWALL_IP, TELNET_PORT, timeout=10)

        #登录
        telnet.read_until(b"Username:")
        telnet.write(USERNAME.encode('ascii') + b"\n")
        telnet.read_until(b"Password:")
        telnet.write(PASSWORD.encode('ascii') + b"\n")
        sleep(2)

        #ip_get指令
        telnet.write(b"display ip interface brief\n")
        sleep(2)
        output = telnet.read_very_eager().decode('ascii')

        #从返回值中获取ip
        ip_address_pattern = rf'{INTERFACE}\s+(\S+)/\d+\s+up\s+up\(s\)'
        ip_address_match = re.search(ip_address_pattern, output)
        if ip_address_match:
            return ip_address_match.group(1)
        else:
            return "IP not found"

    except Exception as e:
        return f"Error: {str(e)}"
    
# 配置日志
logging.basicConfig(
    filename='ddns_update.log',
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',  # 添加时间戳
    datefmt='%Y-%m-%d %H:%M:%S'  # 定义时间戳的格式
)

# 更新阿里云 DNS 记录
def update_dns_record(ip, record_name):
    client = AcsClient(ACCESS_KEY, AccessKey_Secret, 'cn-hangzhou')
    request = CommonRequest()
    request.set_accept_format('json')
    request.set_domain('alidns.aliyuncs.com')
    request.set_method('POST')
    request.set_version('2015-01-09')
    request.set_action_name('UpdateDomainRecord')
    request.add_query_param('RecordId', RECORD_ID)
    request.add_query_param('RR', record_name)
    request.add_query_param('Type', 'A')
    request.add_query_param('Value', ip)

    response = client.do_action_with_exception(request)
    return response

def get_current_time_formatted():
    # 获取当前时间
    current_time = datetime.now()
    # 格式化时间为 [YYYY-MM-DD HH:MM:SS]
    formatted_time = current_time.strftime("[%Y-%m-%d %H:%M:%S]")
    return formatted_time

current_time = get_current_time_formatted()
# 主程序
def main():
    try:
        logging.info(f"使用 IP 地址: {pppoe_ip}")
        print(f"{current_time} 使用常量 IP 地址: {pppoe_ip}")
        update_dns_record(pppoe_ip, Record_name)  # 更新 A 记录
        logging.info(f"成功更新 DNS 记录: {DOMAIN} ----> {pppoe_ip}")
        print(f"{current_time} 成功更新 DNS 记录: {DOMAIN} ----> {pppoe_ip}")
    except Exception as e:
        logging.error(f"更新失败: {e}")
        print(f"{current_time} 更新失败! 请查看log")
while True:
     
     #赋值(与输出)
     pppoe_ip_last = pppoe_ip
     pppoe_ip = get_pppoe_ip()

     if pppoe_ip != pppoe_ip_last: #判断ip变化
         current_time = get_current_time_formatted()
         print(f'{current_time} 目前的ip是{pppoe_ip}与先前的{pppoe_ip_last}不同,DDNS开始更新')
         if __name__ == "__main__":
             main() #DDNS与log
     else:
         print(f'{current_time} 当前的ip是{pppoe_ip}与先前的ip相同')
     sleep(Time)