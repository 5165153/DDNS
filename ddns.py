#安装以下sdk
#pip install aliyun-python-sdk-core
#pip install aliyun-python-sdk-alidns

import telnetlib
import re
import logging
from time import sleep
from datetime import datetime
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
import configparser
import os
import traceback

#sleep(100) # 不要让用户觉得启动的太快

# 创建一个示例配置文件的函数
def create_sample_config_file(path):
    config = configparser.ConfigParser()
    config['DEVICE1'] = {
        'DEVICE_IP': '0.0.0.0',
        'TELNET_PORT': '23',
        'USERNAME': 'username',
        'PASSWORD': 'password',
        'INTERFACE': 'Dialer0',
        'Time': '30',
        'ACCESS_KEY': 'access_key',
        'AccessKey_Secret': 'accesskey_secret',
        'DOMAIN': 'example.com',
        'RECORD_ID': 'record_id',
        'Record_name': 'www',
        'Retry_Interval': '5'
    }
    with open(path, 'w') as configfile:
        config.write(configfile)

# 配置文件设置
script_dir = os.path.dirname(os.path.realpath(__file__))
config_file_path = os.path.join(script_dir, 'config.ini')

# 检查配置文件是否存在
if not os.path.exists(config_file_path):
    create_sample_config_file(config_file_path)
    logging.error(f"未找到配置文件。已创建一个示例配置文件位于 {config_file_path}。请根据你的设置更改它。")
    exit(1)

config = configparser.ConfigParser()
config.read(config_file_path)

# 日志配置
logging.basicConfig(
    filename='ddns_update.log',
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 获取带重试机制的PPPoE IP地址的函数
def get_pppoe_ip(device_config):
    #print("Debug: get_pppoe_ip called with device_config:", device_config)

    max_retries = 5
    retry_interval = int(device_config['retry_interval'])
    #print("Debug: retry_interval set to", retry_interval)

    for attempt in range(max_retries):
        try:
            device_ip = device_config['device_ip']
            #print("Debug: device_ip set to", device_ip)
            with telnetlib.Telnet(device_config['device_ip'], int(device_config['telnet_port']), timeout=10) as telnet:
                # Telnet操作代码
                telnet.read_until(b"Username:")
                telnet.write(device_config['username'].encode('ascii') + b"\n")
                telnet.read_until(b"Password:")
                telnet.write(device_config['password'].encode('ascii') + b"\n")
                sleep(2)
                telnet.write(b"display ip interface brief\n")
                sleep(2)
                output = telnet.read_very_eager().decode('ascii')

                ip_address_pattern = rf'{device_config["interface"]}\s+(\S+)/\d+\s+up\s+up\(s\)'
                ip_address_match = re.search(ip_address_pattern, output)
                if ip_address_match:
                    return ip_address_match.group(1)
            return "IP未找到"
        except Exception as e:
            #print("Error: Configuration key not found:", e)
            logging.error(f"在 get_pppoe_ip 中尝试 {attempt + 1} 失败: {str(e)}")
            sleep(retry_interval)
    return None

# 带重试机制的更新Aliyun DNS记录的函数
def update_dns_record(ip, device_config):
    max_retries = 5
    retry_interval = int(device_config['retry_interval'])
    for attempt in range(max_retries):
        try:
            client = AcsClient(device_config['access_key'], device_config['accesskey_secret'], 'cn-hangzhou')
            request = CommonRequest()
            request.set_accept_format('json')
            request.set_domain('alidns.aliyuncs.com')
            request.set_method('POST')
            request.set_version('2015-01-09')
            request.set_action_name('UpdateDomainRecord')
            request.add_query_param('RecordId', device_config['record_id'])
            request.add_query_param('RR', device_config['record_name'])
            request.add_query_param('Type', 'A')
            request.add_query_param('Value', ip)

            response = client.do_action_with_exception(request)
            return response
        except Exception as e:
            logging.error(f"在 update_dns_record 中尝试 {attempt + 1} 次失败: {str(e)}")
            sleep(retry_interval)
    return None

# 获取当前格式化时间的函数
def get_current_formatted_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 单个设备的主要函数
def main(device_config, last_ip):
    #print("当前设备配置:", device_config)  # 检查配置内容
    try:
        current_time = get_current_formatted_time()
        current_ip = get_pppoe_ip(device_config)
        if current_ip and current_ip != "IP未找到" and current_ip != last_ip:
            # IP地址发生了变化，执行DDNS更新
            response = update_dns_record(current_ip, device_config)
            if response:
                logging.info(f"已更新DNS记录,将 {device_config['record_name']} 更新为IP {current_ip}")
                print(f"[{current_time}] 已更新DNS记录,将 {device_config['record_name']} 更新为IP {current_ip}")
            else:
                logging.error("更新DNS记录失败。")
                print(f"[{current_time}] 更新DNS记录失败。")
            last_ip = current_ip  # 更新last_ip
        elif current_ip and current_ip != "IP未找到":
            # IP地址未发生变化，记录日志
            logging.info(f"{device_config['record_name']} 的IP地址未发生变化")
        else:
            # 无法获取IP地址
            logging.error("无法获取当前IP。")
    except Exception as e:
        current_time = get_current_formatted_time()
        error_message = f"[{current_time}] 在 main 中发生错误: {str(e)}"
        logging.error(error_message)
        print(error_message)
        traceback.print_exc()
    return last_ip  # 返回更新后的last_ip

# 循环运行每个设备的主要函数
if __name__ == "__main__":
    last_ip = {}  # 初始化last_ip字典
    device_processed = {}  # 初始化设备处理标记字典

    while True:
        for section in config.sections():
            device_config = dict(config.items(section))
            current_time = get_current_formatted_time()
            print(f"[{current_time}] 正在运行 {section}...")

            # 检查设备是否已处理过
            if device_processed.get(section, False):
                # 如已处理过进行延迟
                sleep(int(device_config['time']))

            try:
                # 处理设备
                last_ip[section] = main(device_config, last_ip.get(section))
            except Exception as e:
                error_message = f"[{current_time}] 处理 {section} 时发生错误: {e}"
                print(error_message)
                logging.error(error_message)

            # 标记设备已处理
            device_processed[section] = True