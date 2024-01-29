# 安装以下sdk
# pip install aliyun-python-sdk-core
# pip install aliyun-python-sdk-alidns

import telnetlib
import re
import logging
from time import sleep
from datetime import datetime
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordInfoRequest import DescribeDomainRecordInfoRequest
import configparser
import os
import traceback
import json

# 获取当前格式化时间的函数
def get_current_formatted_time():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 带时间戳的消息打印函数
def print_timestamped_message(message):
    current_time = get_current_formatted_time()
    print(f"[{current_time}] {message}")

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
        'Retry_Interval': '5',
        'Mismatch_Threshold': '3'
    }
    with open(path, 'w') as configfile:
        config.write(configfile)

# 配置文件设置
script_dir = os.path.dirname(os.path.realpath(__file__))
config_file_path = os.path.join(script_dir, 'config.ini')

# 检查配置文件是否存在
if not os.path.exists(config_file_path):
    create_sample_config_file(config_file_path)
    print_timestamped_message(f"未找到配置文件,已创建一个示例配置文件位于 {config_file_path},请根据你的设置更改它")
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
    max_retries = 5
    retry_interval = int(device_config['retry_interval'])

    for attempt in range(max_retries):
        try:
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

#  带重试机制的获取Aliyun DNS记录对应的IP
def get_current_dns_ip(access_key, accesskey_secret, record_id, retry_interval):
    client = AcsClient(access_key, accesskey_secret, 'cn-hangzhou')
    request = DescribeDomainRecordInfoRequest()
    request.set_accept_format('json')
    request.set_RecordId(record_id)

    attempt = 0
    max_retries = 5  # 根据需要调整最大重试次数

    while attempt < max_retries:
        try:
            response = client.do_action_with_exception(request)
            response_dict = json.loads(response)
            if 'Value' in response_dict:
                print_timestamped_message(f'查询DNS记录成功')
                logging.info(f'查询DNS记录成功,ip:{response_dict}')
                return response_dict['Value']  # 返回记录的IP
            else:
                print_timestamped_message("查询DNS记录成功,但未找到'Value'键,检查record_id是否正确")
                logging.error("查询DNS记录成功,但未找到'Value'键,检查record_id是否正确")
                return None
        except Exception as e:
            print_timestamped_message("查询DNS记录失败")
            logging.error(f"查询DNS记录失败: {str(e)}")
            attempt += 1
            if attempt < max_retries:
                sleep(retry_interval)  # 重试间隔

    logging.error(f"查询DNS记录失败: 达到最大重试次数 {max_retries}")
    return None

mismatch_count = {}

# 单个设备的主要函数
def main(device_config, section):
    global mismatch_counts
    mismatch_threshold = int(device_config.get('mismatch_threshold', 3))  # 默认值为3
    retry_interval = int(device_config.get('retry_interval', 5))  # 从配置读取重试间隔，默认为5秒

    # 初始化当前设备的不匹配计数
    if section not in mismatch_counts:
        mismatch_counts[section] = 0

    try:
        current_dns_ip = get_current_dns_ip(device_config['access_key'], device_config['accesskey_secret'], device_config['record_id'], retry_interval)
        current_pppoe_ip = get_pppoe_ip(device_config)

        if current_pppoe_ip and current_pppoe_ip != "IP未找到":
            if current_pppoe_ip != current_dns_ip:
                mismatch_counts[section] += 1  # 增加不匹配计数
                print_timestamped_message(f"{section} 不匹配次数: {mismatch_counts[section]}")
                if mismatch_counts[section] >= mismatch_threshold:
                    # 连续不匹配超过阈值，更新DNS记录
                    response = update_dns_record(current_pppoe_ip, device_config)
                    if response:
                        logging.info(f"{section} 由于连续不匹配, 已更新DNS记录, 将 {device_config['record_name']} 更新为IP {current_pppoe_ip}")
                        print_timestamped_message(f"{section} 由于连续不匹配, 已更新DNS记录, 将 {device_config['record_name']} 更新为IP {current_pppoe_ip}")
                        mismatch_counts[section] = 0  # 成功更新后重置不匹配计数
            else:
                # IP地址与DNS记录一致，重置不匹配计数器
                mismatch_counts[section] = 0
        else:
            # 无法获取PPPoE IP地址
            logging.error(f"{section} 无法获取当前PPPoE IP。")
    except Exception as e:
        error_message = f"{section} 在 main 中发生错误: {str(e)}"
        logging.error(error_message)
        print_timestamped_message(error_message)
        traceback.print_exc()

# 主循环
if __name__ == "__main__":
    device_processed = {}  # 初始化设备处理标记字典

    while True:
        for section in config.sections():
            device_config = dict(config.items(section))
            print_timestamped_message(f"正在运行 {section}...") # 表示目前代码运行正常

            # 检查设备是否已处理过
            if device_processed.get(section, False):
                # 如已处理过进行延迟
                sleep_time = int(device_config.get('time', 60))  # 使用设备配置中的时间，或默认为60秒
                print_timestamped_message(f"等待 {sleep_time} 秒后再次处理 {section}")
                sleep(sleep_time)

            try:
                main(device_config, section)
            except Exception as e:
                error_message = f"处理 {section} 时发生错误: {e}"
                print_timestamped_message(error_message)
                logging.error(error_message)

            # 标记设备已处理
            device_processed[section] = True